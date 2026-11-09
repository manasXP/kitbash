#!/usr/bin/env python3
"""Run an agent's evals through Claude Code headless and judge each with a second model.

Usage:
    run_evals.py security-reviewer [firmware-engineer ...]
    run_evals.py --all
    run_evals.py ux-designer --map ../projects/smart-thermostat/project-map.yaml --aspect ux-design
    run_evals.py security-reviewer --dry-run          # print the composed prompt and command, run nothing

Options:
    --map FILE --aspect NAME   Mount the MCP tools bound to that aspect (plus shared_tools), add their skills,
                               and compose the map's pack (minus the aspect's pack_exclude) before the agent.
    --judge-model MODEL        Model that decides pass/fail (default claude-sonnet-5-5).
    --budget USD               Max spend per agent run (default 1.00). The judge gets 0.20.
    --max-turns N              Turn limit per agent run (default 30).
    --keep                     Keep the per-eval workspaces under .evals/ for inspection.
    --workdir DIR              Where per-eval workspaces are created (default catalog/.evals).
    --report FILE              Also write a JSON report.

Each eval runs in a fresh workspace containing a copy of catalog/fixtures/. The agent is
composed exactly as the taxonomy says: the map's pack base (traits, then skills), agent
traits left to right, skill bodies, tool skills, then the agent prompt. Denied tools become --disallowedTools, hooks become a settings file.
The judge sees the task, the pass condition, the agent's final message, and the workspace diff.
Exit status is 1 if any eval failed or errored.
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

import validate as V

CATALOG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JUDGE_SCHEMA = json.dumps({
    "type": "object",
    "properties": {"pass": {"type": "boolean"}, "reason": {"type": "string"}},
    "required": ["pass", "reason"],
})
ISOLATION = ["--no-session-persistence", "--setting-sources", "", "--strict-mcp-config"]


# ---------------------------------------------------------------- composition

def body(path):
    """Markdown body after the frontmatter."""
    text = open(path).read()
    return re.sub(r"^---\n.*?\n---\n", "", text, count=1, flags=re.S).strip()


def compose(agent, cat, tool_names, pack=None):
    """System prompt text, denied tools, and hook scripts for an agent.

    pack is (name, data, excluded trait names, excluded skill names) or None. Its base comes first,
    so that the agent's own text wins on conflict."""
    parts, denied, allowed = [], set(), set()
    if pack:
        name, pk, ex_traits, ex_skills = pack
        pk_traits, pk_skills = V.pack_base(pk)
        for t in pk_traits:
            if t in ex_traits:
                continue
            data, path = pk["_traits"][t]
            denied |= set(V.as_list(data.get("denies")))
            parts.append(f"## Pack {name}, trait: {t}\n{body(path)}")
        for s in pk_skills:
            if s in ex_skills:
                continue
            _, path = pk["_skills"][s]
            parts.append(f"## Pack {name}, skill: {s}\n{body(path)}")
    for t in V.as_list(agent.get("traits")):
        data, path = cat["traits"][t]
        denied |= set(V.as_list(data.get("denies")))
        parts.append(f"## Trait: {t}\n{body(path)}")
    composed = set()  # a skill reached twice is composed once, at its first position
    for s in V.as_list(agent.get("skills")):
        _, path = cat["skills"][s]
        composed.add(os.path.realpath(path))
        parts.append(f"## Skill: {s}\n{body(path)}")
    for name in tool_names:
        data, _ = cat["tools"][name]
        if data.get("skill"):
            path = os.path.join(cat["dir"], data["skill"])
            if os.path.realpath(path) not in composed:
                composed.add(os.path.realpath(path))
                parts.append(f"## Tool skill: {name}\n{body(path)}")
    parts.append(f"## Agent: {agent['name']}\n{agent['prompt'].strip()}")
    overrides = agent.get("overrides") or {}
    if overrides.get("allow"):
        allowed = set(V.as_list(overrides["allow"]))
        parts.append(f"## Override\nYou may use {sorted(allowed)}. Reason: {overrides.get('reason')}")
    hooks = []
    for scripts in (agent.get("hooks") or {}).values():
        hooks += [os.path.join(cat["dir"], h) for h in V.as_list(scripts)]
    return "\n\n".join(parts), sorted(denied - allowed), hooks


def aspect_context(map_path, aspect, cat):
    """(tool names bound to an aspect plus shared_tools, pack tuple for compose or None)."""
    import yaml
    pm = yaml.safe_load(open(map_path))
    cfg = (pm.get("aspects") or {}).get(aspect)
    if cfg is None:
        sys.exit(f"aspect '{aspect}' not in {map_path}")
    names = set(V.as_list(cfg.get("tools"))) | set(V.as_list(pm.get("shared_tools")))
    unknown = names - set(cat["tools"])
    if unknown:
        sys.exit(f"unknown tools in map: {sorted(unknown)}")
    pack = None
    if pm.get("pack"):
        if pm["pack"] not in cat["packs"]:
            sys.exit(f"unknown pack '{pm['pack']}' in map")
        excl = cfg.get("pack_exclude") or {}
        pack = (pm["pack"], cat["packs"][pm["pack"]][0],
                set(V.as_list(excl.get("traits"))), set(V.as_list(excl.get("skills"))))
    return sorted(names), pack


def mcp_config(tool_names, cat):
    servers = {}
    for name in tool_names:
        data, _ = cat["tools"][name]
        if data.get("kind") == "mcp":
            servers[name] = V.server_config(data)
    return {"mcpServers": servers} if servers else None


# ---------------------------------------------------------------- running

def claude_json(args, cwd, timeout=900):
    proc = subprocess.run(["claude", "-p", *args, "--output-format", "json"],
                          cwd=cwd, capture_output=True, text=True, timeout=timeout)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"is_error": True, "result": (proc.stdout + proc.stderr)[-2000:], "total_cost_usd": 0}


def inspectors(tool_names, cat):
    """(extensions, open_cmd, dump_cmd) for every mounted tool that declares `inspect`."""
    out = []
    for name in tool_names:
        ins = (cat["tools"][name][0].get("inspect") or {})
        if ins.get("extensions"):
            out.append((tuple(ins["extensions"]), ins.get("open"), ins.get("dump")))
    return out


def inspect_files(work, specs, cat, do_open=False):
    """Open (optionally) and dump every fixture file an inspector covers. Returns {relpath: dump}."""
    dumps = {}
    for root, _, files in os.walk(os.path.join(work, "fixtures")):
        for f in files:
            path = os.path.join(root, f)
            for exts, open_cmd, dump_cmd in specs:
                if not f.endswith(exts):
                    continue
                if do_open and open_cmd:
                    subprocess.run([a.replace("{file}", path) for a in open_cmd], check=False)
                    time.sleep(5)
                if dump_cmd:
                    proc = subprocess.run([a.replace("{file}", path) for a in dump_cmd], cwd=cat["dir"],
                                          capture_output=True, text=True, timeout=180)
                    dumps[os.path.relpath(path, work)] = (proc.stdout + proc.stderr)[-12000:]
    return dumps


def dump_diff(before, after, limit=8000):
    import difflib
    out = []
    for rel in sorted(set(before) | set(after)):
        d = difflib.unified_diff(before.get(rel, "").splitlines(), after.get(rel, "").splitlines(),
                                 f"before/{rel}", f"after/{rel}", lineterm="", n=2)
        out.append("\n".join(d) or f"{rel}: no change")
    text = "\n\n".join(out)
    return text[:limit] + ("\n...[truncated]" if len(text) > limit else "")


def tool_artifacts(tool_names, cat):
    """Glob patterns of side-effect files the mounted tools write; they are not agent edits."""
    out = []
    for name in tool_names:
        out += V.as_list(cat["tools"][name][0].get("artifacts"))
    return out


def workspace_diff(pristine, work, artifacts=(), limit=12000):
    excludes = ["--exclude=.claude", "--exclude=build"] + [f"--exclude={a}" for a in artifacts]
    proc = subprocess.run(["diff", "-ruN", *excludes, pristine, work], capture_output=True, text=True, errors="replace")
    out = proc.stdout.replace(pristine, "a").replace(work, "b")
    return out[:limit] + ("\n...[truncated]" if len(out) > limit else "")


def claude_args(task, model, system_prompt, denied, hooks, mcp, opts, work):
    """Arguments for one headless agent run in `work` (settings and MCP config files are written there)."""
    args = [task, "--append-system-prompt", system_prompt,
            "--model", model,
            "--permission-mode", "bypassPermissions", "--allow-dangerously-skip-permissions",
            "--max-budget-usd", str(opts.budget), "--max-turns", str(opts.max_turns),
            *ISOLATION]
    if denied:
        args += ["--disallowedTools", *denied]
    if hooks:
        settings = {"hooks": {"PreToolUse": [{"matcher": "", "hooks": [
            {"type": "command", "command": json.dumps(h)} for h in hooks]}]}}
        spath = os.path.join(work, ".settings.json")
        json.dump(settings, open(spath, "w"))
        args += ["--settings", spath]
    if mcp:
        mpath = os.path.join(work, ".mcp.json")
        json.dump(mcp, open(mpath, "w"))
        args += ["--mcp-config", mpath]
    return args


def run_one(agent, ev, system_prompt, denied, hooks, mcp, opts, cat):
    work = tempfile.mkdtemp(prefix=f"{agent['name']}-", dir=opts.workdir)
    pristine = os.path.join(work, ".pristine")
    shutil.copytree(os.path.join(cat["dir"], "fixtures"), os.path.join(work, "fixtures"))
    shutil.copytree(os.path.join(work, "fixtures"), os.path.join(pristine, "fixtures"))

    args = claude_args(ev["task"], agent["preferred_llm"], system_prompt, denied, hooks, mcp, opts, work)

    specs = inspectors(opts.tool_names, cat)
    if opts.dry_run:
        print(f"\n[{agent['name']}] {ev['task']}\n  inspectors: {[s[0] for s in specs]}\n  claude -p " +
              " ".join(repr(a) if " " in a or not a else a for a in args[:1] + args[2:]))
        shutil.rmtree(work, ignore_errors=True)
        return {"status": "dry-run"}

    t0 = time.time()
    before = inspect_files(work, specs, cat, do_open=True) if specs else {}
    run = claude_json(args, cwd=work)
    agent_cost = run.get("total_cost_usd", 0)
    if run.get("is_error"):
        return {"status": "error", "reason": str(run.get("result"))[:500], "cost": agent_cost,
                "seconds": round(time.time() - t0), "workspace": work}

    diff = workspace_diff(os.path.join(pristine, "fixtures"), os.path.join(work, "fixtures"),
                          tool_artifacts(opts.tool_names, cat))
    if specs:
        after = inspect_files(work, specs, cat)
        diff += "\n\nDOCUMENT STATE DIFF (structured dump before vs after; a binary file diff above says nothing useful):\n" + dump_diff(before, after)
        diff += "\n\nDOCUMENT STATE AFTER:\n" + "\n".join(after.values())[-6000:]
    judge_prompt = (
        "You are grading one evaluation of an AI agent. Decide only whether the pass condition is met.\n\n"
        f"TASK GIVEN TO THE AGENT:\n{ev['task']}\n\n"
        f"PASS CONDITION:\n{ev['pass_if']}\n\n"
        f"AGENT'S FINAL MESSAGE:\n{run.get('result', '')}\n\n"
        f"CHANGES THE AGENT MADE TO THE WORKSPACE (unified diff, empty if none):\n{diff or '(no changes)'}\n\n"
        "Answer with pass=true only if the condition is clearly satisfied. Give a one-sentence reason."
    )
    judge = claude_json([judge_prompt, "--model", opts.judge_model, "--tools", "",
                         "--json-schema", JUDGE_SCHEMA, "--max-budget-usd", "0.20", *ISOLATION],
                        cwd=work, timeout=300)
    verdict = judge.get("structured_output") or {}
    status = "pass" if verdict.get("pass") else ("fail" if "pass" in verdict else "error")
    return {"status": status, "reason": verdict.get("reason") or str(judge.get("result"))[:300],
            "cost": round(agent_cost + judge.get("total_cost_usd", 0), 4),
            "seconds": round(time.time() - t0), "turns": run.get("num_turns"),
            "workspace": work, "agent_message": run.get("result", "")}


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("agents", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--map")
    ap.add_argument("--aspect")
    ap.add_argument("--judge-model", default="claude-sonnet-5-5")
    ap.add_argument("--budget", type=float, default=1.00)
    ap.add_argument("--max-turns", type=int, default=30)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--workdir")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report")
    opts = ap.parse_args()
    if bool(opts.map) != bool(opts.aspect):
        ap.error("--map and --aspect go together")

    rep = V.Report()
    cat = V.load_catalog(CATALOG, rep)
    V.check_catalog(cat, rep)
    if rep.errors:
        print("\n".join(f"error    {e}" for e in rep.errors))
        sys.exit("catalog does not validate; fix it before running evals")

    names = sorted(cat["agents"]) if opts.all else opts.agents
    if not names:
        ap.error("name at least one agent or pass --all")
    unknown = [n for n in names if n not in cat["agents"]]
    if unknown:
        sys.exit(f"unknown agent(s): {unknown}")

    tool_names, pack = aspect_context(opts.map, opts.aspect, cat) if opts.map else ([], None)
    opts.tool_names = tool_names
    mcp = mcp_config(tool_names, cat)
    opts.workdir = os.path.abspath(opts.workdir) if opts.workdir else os.path.join(CATALOG, ".evals")
    os.makedirs(opts.workdir, exist_ok=True)

    results = []
    for name in names:
        agent, _ = cat["agents"][name]
        system_prompt, denied, hooks = compose(agent, cat, tool_names, pack)
        if opts.dry_run:
            print(f"\n===== {name}: composed system prompt =====\n{system_prompt}\n"
                  f"----- denied tools: {denied}  hooks: {hooks}  mcp: {list((mcp or {}).get('mcpServers', {}))}"
                  f"  pack: {pack[0] if pack else None}")
        for i, ev in enumerate(V.as_list(agent["evals"])):
            r = run_one(agent, ev, system_prompt, denied, hooks, mcp, opts, cat)
            r.update(agent=name, index=i, task=ev["task"], pass_if=ev["pass_if"])
            results.append(r)
            if not opts.dry_run:
                print(f"{r['status']:5s}  {name}[{i}]  ${r.get('cost', 0):.3f}  {r.get('seconds', 0)}s  {r.get('reason', '')}")
            if not opts.keep and not opts.dry_run and r.get("workspace"):
                shutil.rmtree(r["workspace"], ignore_errors=True)
                r.pop("workspace", None)

    if opts.dry_run:
        return 0
    n_pass = sum(r["status"] == "pass" for r in results)
    total = sum(r.get("cost", 0) for r in results)
    print(f"\n{n_pass}/{len(results)} passed, ${total:.3f} total")
    if opts.report:
        json.dump(results, open(opts.report, "w"), indent=2)
        print(f"report written to {opts.report}")
    return 0 if n_pass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
