#!/usr/bin/env python3
"""Run a playbook: a sequence of agent invocations that code runs and code hands off.

Usage:
    run_playbook.py ../projects/smart-thermostat/playbooks/schematic-change-and-check.yaml   # run its evals
    run_playbook.py PLAYBOOK --run request="Add ..." file=fixtures/eda/x.kicad_sch            # one run, no judge
    run_playbook.py PLAYBOOK --dry-run                                                        # print, run nothing

Options:
    --judge-model MODEL   Model that decides pass/fail of an eval (default claude-sonnet-5-5).
    --budget USD          Max spend per step (default 1.00). The judge gets 0.20.
    --max-turns N         Turn limit per step (default 30).
    --keep                Keep the workspace under .evals/ for inspection.
    --workdir DIR         Where workspaces are created (default .kitbash/work/ when the map is in a .kitbash
                          folder, else catalog/.evals).
    --report FILE         Also write a JSON report.

A playbook is read here, never by a model. Each step composes its agent exactly as run_evals.py does,
inside the aspect the step names (that aspect's tools and the map's pack), and runs it in one shared
workspace so later steps see earlier edits. Between steps the handoff is decided by code: a `command`
handoff runs one of a bound tool's declared commands and passes on exit status zero; an `output`
handoff parses the JSON block the previous agent was told to end its message with and compares one
field. Each step's task is prefixed with the diff the previous step made to the fixtures, since a later
agent has no other way to know what changed. A false handoff stops the playbook. An eval fails without a judge if the path taken differs
from expect_path; otherwise the judge grades pass_if against every step's final message, each
handoff's outcome, and the workspace diff.
"""
import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

import run_evals as R
import validate as V  # before yaml: validate falls back to the vendored PyYAML
import yaml


def fill(text, values):
    for k, v in values.items():
        text = text.replace("{" + k + "}", str(v))
    return text


def json_block(message):
    """The last fenced JSON block in a message, parsed, or None."""
    blocks = re.findall(r"```json\s*(\{.*?\})\s*```", message or "", re.S)
    for b in reversed(blocks):
        try:
            return json.loads(b)
        except json.JSONDecodeError:
            continue
    return None


def outputs_instruction(agent):
    fields = ", ".join(f"{k} ({v})" for k, v in agent["outputs"].items())
    return ("## Outputs\nEnd your final message with one fenced ```json block, an object with exactly these "
            f"fields: {fields}. Code reads that block; nothing else in the message is parsed.")


def evaluate_handoff(h, step_no, agent, message, values, tool_names, cat, work):
    """(passed, one-line detail)."""
    if "command" in h:
        tool, _, cmd = str(h["command"]).partition(".")
        data = cat["tools"][tool][0]
        template = (data.get("commands") or {})[cmd]
        vals = dict(values)
        vals.update({k: fill(str(v), values) for k, v in h.items() if k != "command"})
        vals["report"] = os.path.join(work, f".handoff-{step_no}-{tool}-{cmd}.json")
        argv = [fill(a, vals) for a in shlex.split(template)]
        env = dict(os.environ, **{k: str(v) for k, v in (data.get("env") or {}).items()})
        proc = subprocess.run(argv, cwd=work, env=env, capture_output=True, text=True, timeout=300)
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-1:] or [""]
        return proc.returncode == 0, f"{tool}.{cmd} exit {proc.returncode}: {tail[0][:160]}"
    field = h["output"]
    block = json_block(message)
    if block is None or field not in block:
        return False, f"output '{field}': agent '{agent}' ended with no JSON block containing it"
    got = block[field]
    if "equals" in h:
        return got == h["equals"], f"output {field}={got!r}, wanted {h['equals']!r}"
    return got in V.as_list(h["in"]), f"output {field}={got!r}, wanted one of {V.as_list(h['in'])}"


def workspace_paths(diff):
    """Rewrite the a/ and b/ prefixes of a fixtures diff so the paths are the ones the next agent will see."""
    out = []
    for line in diff.splitlines():
        if line.startswith("diff "):
            line = line.replace(" a/", " before/fixtures/", 1).replace(" b/", " fixtures/", 1)
        elif line.startswith("--- a/"):
            line = "--- before/fixtures/" + line[6:]
        elif line.startswith("+++ b/"):
            line = "+++ fixtures/" + line[6:]
        out.append(line)
    return "\n".join(out)


def with_previous_diff(task, prev, diff):
    if not prev:
        return task
    return (f"The previous step of this playbook was the agent '{prev}'. Its changes to the workspace, as a "
            f"unified diff (empty if none):\n\n{diff or '(no changes)'}\n\nYour task: {task}")


def aspect_model(pm, aspect, agent):
    return (pm["aspects"][aspect] or {}).get("preferred_llm") or agent["preferred_llm"]


def run_playbook(pb, pm, map_path, values, cat, opts):
    work = tempfile.mkdtemp(prefix=f"{pb['name']}-", dir=opts.workdir)
    pristine = os.path.join(work, ".pristine")
    R.copy_fixtures(cat, work)
    shutil.copytree(os.path.join(work, "fixtures"), os.path.join(pristine, "fixtures"))
    t0 = time.time()
    out = {"path": [], "steps": [], "handoffs": [], "cost": 0.0, "workspace": work, "status": "ran"}
    all_tools, before = set(), {}
    steps = V.as_list(pb["steps"])
    prev_agent, prev_diff = None, ""
    for i, st in enumerate(steps):
        agent, _ = cat["agents"][st["agent"]]
        tool_names, pack = R.aspect_context(map_path, st["aspect"], cat)
        all_tools |= set(tool_names)
        system_prompt, denied, hooks = R.compose(agent, cat, tool_names, pack)
        if agent.get("outputs"):
            system_prompt += "\n\n" + outputs_instruction(agent)
        task = with_previous_diff(fill(st["task"], values), prev_agent, prev_diff)
        model = aspect_model(pm, st["aspect"], agent)
        args = R.claude_args(task, model, system_prompt, denied, hooks, R.mcp_config(tool_names, cat), opts, work)
        specs = R.inspectors(tool_names, cat)
        if opts.dry_run:
            print(f"\n===== step {i}: {st['agent']} in {st['aspect']} on {model} =====\n{system_prompt}\n"
                  f"----- task: {task}\n----- denied: {denied}  tools: {tool_names}  pack: {pack[0] if pack else None}"
                  f"\n----- handoff: {st.get('handoff_if')}")
            continue
        if i == 0 and specs:
            before = R.inspect_files(work, specs, cat, do_open=True)
        snapshot = os.path.join(work, f".step-{i}")
        shutil.copytree(os.path.join(work, "fixtures"), os.path.join(snapshot, "fixtures"))
        run = R.claude_json(args, cwd=work)
        out["cost"] += run.get("total_cost_usd", 0)
        step_diff = workspace_paths(R.workspace_diff(os.path.join(snapshot, "fixtures"), os.path.join(work, "fixtures"),
                                                     R.tool_artifacts(tool_names, cat)))
        rec = {"agent": st["agent"], "aspect": st["aspect"], "model": model, "task": task,
               "turns": run.get("num_turns"), "message": run.get("result", ""), "diff": step_diff}
        out["steps"].append(rec)
        if run.get("is_error"):
            out.update(status="error", reason=f"step {i} ({st['agent']}): {str(run.get('result'))[:300]}")
            break
        out["path"].append(st["agent"])
        prev_agent, prev_diff = st["agent"], step_diff
        h = st.get("handoff_if")
        if h and i < len(steps) - 1:
            ok, detail = evaluate_handoff(h, i, st["agent"], rec["message"], values, tool_names, cat, work)
            out["handoffs"].append({"after": st["agent"], "passed": ok, "detail": detail})
            print(f"       handoff after {st['agent']}: {'continue' if ok else 'stop'}  ({detail})")
            if not ok:
                break
    if opts.dry_run:
        shutil.rmtree(work, ignore_errors=True)
        return out
    out["seconds"] = round(time.time() - t0)
    diff = R.workspace_diff(os.path.join(pristine, "fixtures"), os.path.join(work, "fixtures"),
                            R.tool_artifacts(sorted(all_tools), cat))
    specs = R.inspectors(sorted(all_tools), cat)
    if specs:
        after = R.inspect_files(work, specs, cat)
        diff += "\n\nDOCUMENT STATE DIFF (structured dump before vs after):\n" + R.dump_diff(before, after)
        diff += "\n\nDOCUMENT STATE AFTER:\n" + "\n".join(after.values())[-6000:]
    out["diff"] = diff
    return out


def judge(pb, ev, run, opts, work):
    transcript = "\n\n".join(f"STEP {i}: {s['agent']} in {s['aspect']}\nTASK: {s['task']}\nFINAL MESSAGE:\n{s['message']}"
                             for i, s in enumerate(run["steps"]))
    handoffs = "\n".join(f"after {h['after']}: {'continued' if h['passed'] else 'STOPPED'} ({h['detail']})"
                         for h in run["handoffs"]) or "(none evaluated)"
    prompt = (
        "You are grading one evaluation of a playbook: a fixed sequence of AI agents that code ran and code handed "
        "off between. Decide only whether the pass condition is met.\n\n"
        f"PLAYBOOK: {pb['name']}: {pb.get('description', '')}\nINPUTS: {json.dumps(ev['inputs'])}\n\n"
        f"PASS CONDITION:\n{ev['pass_if']}\n\n"
        f"PATH TAKEN (agents that ran, in order): {run['path']}\nHANDOFFS DECIDED BY CODE:\n{handoffs}\n\n"
        f"{transcript}\n\n"
        f"CHANGES TO THE WORKSPACE (unified diff, empty if none):\n{run.get('diff') or '(no changes)'}\n\n"
        "Answer with pass=true only if the condition is clearly satisfied. Give a one-sentence reason."
    )
    j = R.claude_json([prompt, "--model", opts.judge_model, "--tools", "", "--json-schema", R.JUDGE_SCHEMA,
                       "--max-budget-usd", "0.20", *R.ISOLATION], cwd=work, timeout=300)
    verdict = j.get("structured_output") or {}
    status = "pass" if verdict.get("pass") else ("fail" if "pass" in verdict else "error")
    return status, verdict.get("reason") or str(j.get("result"))[:300], j.get("total_cost_usd", 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("playbook")
    ap.add_argument("--run", nargs="*", metavar="KEY=VALUE", help="run once with these inputs instead of the evals")
    ap.add_argument("--judge-model", default="claude-sonnet-5-5")
    ap.add_argument("--budget", type=float, default=1.00)
    ap.add_argument("--max-turns", type=int, default=30)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--workdir")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report")
    opts = ap.parse_args()

    pb_path = os.path.abspath(opts.playbook)
    pb = yaml.safe_load(open(pb_path))
    map_path = os.path.normpath(os.path.join(os.path.dirname(os.path.realpath(pb_path)), pb["map"]))
    rep = V.Report()
    V.check_project_map(map_path, rep, {})        # loads and checks the catalog the map names, rule 6 included
    if rep.errors:
        print("\n".join(f"error    {e}" for e in rep.errors))
        sys.exit("catalog, map or playbook does not validate; fix it before running")
    pm = yaml.safe_load(open(map_path))
    cat_dir = V.catalog_dir(map_path, pm.get("catalog"))
    cat = V.load_catalog(cat_dir, V.Report(), V.user_catalog(map_path))
    opts.workdir = os.path.abspath(opts.workdir) if opts.workdir else V.work_dir(map_path)
    os.makedirs(opts.workdir, exist_ok=True)

    if opts.run is not None:
        values = dict(kv.split("=", 1) for kv in opts.run)
        missing = set(V.as_list(pb.get("inputs"))) - set(values)
        if missing:
            ap.error(f"--run is missing inputs {sorted(missing)}")
        r = run_playbook(pb, pm, map_path, values, cat, opts)
        if opts.dry_run:
            return 0
        print(f"\npath: {r['path']}  ${r['cost']:.3f}  {r['seconds']}s  status: {r['status']}")
        if r["steps"]:
            print(f"\nfinal message of {r['steps'][-1]['agent']}:\n{r['steps'][-1]['message']}")
        print(f"workspace: {r['workspace']}" if opts.keep else "")
        if not opts.keep:
            shutil.rmtree(r["workspace"], ignore_errors=True)
        if opts.report:
            json.dump(r, open(opts.report, "w"), indent=2)
        return 0 if r["status"] == "ran" else 1

    results = []
    for i, ev in enumerate(V.as_list(pb["evals"])):
        print(f"\n[{pb['name']}][{i}] inputs: {json.dumps(ev['inputs'])}")
        r = run_playbook(pb, pm, map_path, ev["inputs"], cat, opts)
        if opts.dry_run:
            break
        expected = V.as_list(ev["expect_path"])
        if r["status"] == "error":
            status, reason, jcost = "error", r["reason"], 0
        elif r["path"] != expected:
            status, reason, jcost = "fail", f"path taken {r['path']} differs from expect_path {expected}", 0
        else:
            status, reason, jcost = judge(pb, ev, r, opts, r["workspace"])
        cost = round(r["cost"] + jcost, 4)
        print(f"{status:5s}  {pb['name']}[{i}]  path={r['path']}  ${cost:.3f}  {r.get('seconds', 0)}s  {reason}")
        rec = {"playbook": pb["name"], "index": i, "status": status, "reason": reason, "path": r["path"],
               "expect_path": expected, "handoffs": r["handoffs"], "cost": cost, "seconds": r.get("seconds"),
               "steps": [{k: v for k, v in s.items()} for s in r["steps"]]}
        if opts.keep:
            rec["workspace"] = r["workspace"]
        else:
            shutil.rmtree(r["workspace"], ignore_errors=True)
        results.append(rec)
    if opts.dry_run:
        return 0
    n_pass = sum(r["status"] == "pass" for r in results)
    print(f"\n{n_pass}/{len(results)} passed, ${sum(r['cost'] for r in results):.3f} total")
    if opts.report:
        json.dump(results, open(opts.report, "w"), indent=2)
        print(f"report written to {opts.report}")
    return 0 if n_pass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
