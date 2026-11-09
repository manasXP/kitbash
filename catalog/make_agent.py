#!/usr/bin/env python3
"""Meta-agent: assemble a new agent from the catalog, validate it, evaluate it, then register it.

Usage:
    make_agent.py "an agent that triages incoming GitHub issues"
    make_agent.py "..." --map ../projects/smart-thermostat/project-map.yaml --aspect api --register
    make_agent.py "..." --no-evals            # select, emit, validate only
    make_agent.py "..." --dry-run             # print the proposed files, write nothing

Stages (see docs/Composable-Agent-Taxonomy.pdf, part 7):
    1. Select   one headless Claude call reads the catalog inventory and picks traits, skills, capabilities.
    2. Emit     the script writes agents/<name>.yaml, any fixtures the evals need, and at most one new skill.
    3. Validate validate.py rules run; on failure the errors go back to the model for one repair pass,
                and if it still fails the written files are removed and the proposal is printed instead.
    4. Evaluate run_evals.py runs the agent's evals. With --register and an all-pass, the agent is added
                to the aspect's agent list in the project map. Nothing is registered on a failure.

Options:
    --map FILE --aspect NAME   Constrain capabilities to the aspect's tools and (with --register) register there.
    --model MODEL              Model that designs the agent (default claude-opus-5-5).
    --budget USD               Spend cap for the design call (default 1.00).
    --no-evals                 Stop after validation.
    --dry-run                  Print the proposal, write nothing.
    --search TERMS             Also offer the imported skills (registry.py) that rank highest for TERMS; repeatable.
                               Without it the inventory holds only the catalog's own skills, however many are imported.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

import validate as V

HERE = os.path.dirname(os.path.abspath(__file__))
KNOWN_MODELS = ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"]
ISOLATION = ["--no-session-persistence", "--setting-sources", "", "--strict-mcp-config", "--tools", ""]

SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "description": {"type": "string"},
        "traits": {"type": "array", "items": {"type": "string"}},
        "skills": {"type": "array", "items": {"type": "string"}},
        "new_skills": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "description": {"type": "string"},
            "requires": {"type": "object", "properties": {
                "tools": {"type": "array", "items": {"type": "string"}},
                "capabilities": {"type": "array", "items": {"type": "string"}},
                "min_model_tier": {"type": "string"}}},
            "body": {"type": "string"}},
            "required": ["name", "description", "body"]}},
        "hooks": {"type": "array", "items": {"type": "string"}},
        "capabilities": {"type": "array", "items": {"type": "string"}},
        "llms": {"type": "array", "items": {"type": "string"}},
        "preferred_llm": {"type": "string"},
        "prompt": {"type": "string"},
        "evals": {"type": "array", "items": {"type": "object", "properties": {
            "task": {"type": "string"}, "pass_if": {"type": "string"}},
            "required": ["task", "pass_if"]}},
        "fixtures": {"type": "array", "items": {"type": "object", "properties": {
            "path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"]}},
        "rationale": {"type": "string"},
    },
    "required": ["name", "description", "traits", "skills", "capabilities", "llms",
                 "preferred_llm", "prompt", "evals", "rationale"],
}


# ---------------------------------------------------------------- inventory

def body(path):
    return re.sub(r"^---\n.*?\n---\n", "", open(path).read(), count=1, flags=re.S).strip()


def skill_entry(d):
    e = {"description": d.get("description"), "requires": d.get("requires", {})}
    if "_source" in d:
        e.update({"source": d["_source"], "license": d.get("_license")})
    return e


def inventory(cat, allowed_tools, pack=None, offered=()):
    """What the designing model sees. Imported skills appear only when named in `offered` (from --search)."""
    tools = {n: cat["tools"][n][0] for n in allowed_tools}
    capabilities = sorted({c for t in tools.values() for c in V.as_list(t.get("provides"))})
    return {
        "traits": {n: {"tools": d.get("tools", []), "denies": d.get("denies", []), "text": body(p)}
                   for n, (d, p) in cat["traits"].items()},
        "skills": {n: skill_entry(d) for n, (d, p) in cat["skills"].items() if "_source" not in d or n in offered},
        "tools": {n: {"provides": d.get("provides", []), "kind": d.get("kind")} for n, d in tools.items()},
        "capabilities_available": capabilities,
        "hooks": sorted(os.path.relpath(p, cat["dir"]) for p in
                        [os.path.join(cat["dir"], "hooks", f) for f in os.listdir(os.path.join(cat["dir"], "hooks"))]
                        if os.path.isfile(p)),
        "existing_fixtures": sorted(os.path.relpath(os.path.join(r, f), cat["dir"])
                                    for r, _, fs in os.walk(os.path.join(cat["dir"], "fixtures")) for f in fs),
        "existing_agent_names": sorted(cat["agents"]),
        "models": KNOWN_MODELS,
        "pack_applied_by_map": None if not pack else {
            "name": pack, "note": "composed before every agent in this map; do not repeat what it says",
            "base_traits": V.pack_base(cat["packs"][pack][0])[0],
            "base_skills": {s: cat["packs"][pack][0]["_skills"][s][0].get("description")
                            for s in V.pack_base(cat["packs"][pack][0])[1]}},
    }


def design_prompt(request, inv, example_yaml, aspect, errors=None, previous=None):
    rules = f"""You design one new agent for a composable agent catalog. Return JSON matching the schema.

REQUEST FROM THE USER:
{request}

CATALOG INVENTORY (JSON):
{json.dumps(inv, indent=1)}

EXAMPLE OF AN EXISTING AGENT FILE, FOR SHAPE AND TONE:
{example_yaml}

RULES
- name: kebab-case, not in existing_agent_names, describes the job.
- traits: only names from the inventory, in the order they should apply. Reuse before inventing.
- skills: names from the inventory. A skill with a source is imported; list it by name like any other. If no skill
  covers the job, add at most ONE entry to new_skills with a concrete procedure in its body (markdown, 15-40 lines,
  written for the agent to follow). Then list its name in skills.
- capabilities: only values from capabilities_available{" (the tools bound to aspect '" + aspect + "')" if aspect else ""}.
  Never name a vendor or tool in the prompt; name the capability.
- hooks: only paths from the inventory, or empty.
- llms: from models. preferred_llm must be in llms. Use opus for review or safety work, sonnet for routine production.
- prompt: 2-5 sentences of job-specific instruction. Do not repeat what the traits or skills already say.
- evals: 2 or 3. Each task must reference an input file by a path starting with fixtures/, either from
  existing_fixtures or one you supply in fixtures. Each pass_if must be checkable from the agent's final
  message plus the diff of files it changed. Include one eval where the right behavior is to find nothing
  or to decline, so the agent is tested against over-reporting.
- fixtures: realistic, small files under fixtures/<agent-name>/. Make a defect fixture actually contain the defect.
- rationale: two sentences on why these parts were chosen.
"""
    if errors:
        rules += f"""
YOUR PREVIOUS PROPOSAL FAILED VALIDATION. Fix every error below and return the corrected full proposal.
ERRORS:
{chr(10).join(errors)}

PREVIOUS PROPOSAL:
{json.dumps(previous, indent=1)}
"""
    return rules


def claude_json(args, timeout=600):
    proc = subprocess.run(["claude", "-p", *args, "--output-format", "json"],
                          cwd=HERE, capture_output=True, text=True, timeout=timeout)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        sys.exit(f"claude returned no JSON:\n{(proc.stdout + proc.stderr)[-2000:]}")


# ---------------------------------------------------------------- emit

class Literal(str):
    pass


def _literal(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")


yaml.add_representer(Literal, _literal)


def agent_yaml(p):
    doc = {
        "name": p["name"],
        "description": p["description"],
        "traits": p["traits"],
        "skills": p["skills"],
    }
    if p.get("hooks"):
        doc["hooks"] = {"pre_tool_use": p["hooks"]}
    if p.get("capabilities"):
        doc["requires"] = {"capabilities": p["capabilities"]}
    doc["llms"] = p["llms"]
    doc["preferred_llm"] = p["preferred_llm"]
    doc["prompt"] = Literal(p["prompt"].strip() + "\n")
    doc["evals"] = [{"task": e["task"], "pass_if": e["pass_if"]} for e in p["evals"]]
    text = yaml.dump(doc, sort_keys=False, width=100, allow_unicode=True)
    return f"# generated by make_agent.py\n# rationale: {p['rationale'].strip()}\n" + text


def skill_md(s):
    fm = {"name": s["name"], "description": s["description"]}
    if s.get("requires"):
        fm["requires"] = {k: v for k, v in s["requires"].items() if v}
    return "---\n" + yaml.dump(fm, sort_keys=False).strip() + "\n---\n" + s["body"].strip() + "\n"


def planned_files(p):
    files = {f"agents/{p['name']}.yaml": agent_yaml(p)}
    for s in p.get("new_skills") or []:
        files[f"skills/{s['name']}/SKILL.md"] = skill_md(s)
    for f in p.get("fixtures") or []:
        path = f["path"].lstrip("/")
        if not path.startswith("fixtures/"):
            path = "fixtures/" + path
        files[path] = f["content"]
    return files


def write_files(files):
    written = []
    for rel, content in files.items():
        path = os.path.join(HERE, rel)
        if os.path.exists(path) and not rel.startswith("fixtures/"):
            sys.exit(f"refusing to overwrite existing {rel}")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").write(content)
        written.append(path)
    return written


def remove_files(paths):
    for p in paths:
        if os.path.exists(p):
            os.remove(p)
        d = os.path.dirname(p)
        if os.path.isdir(d) and not os.listdir(d):
            os.rmdir(d)


# ---------------------------------------------------------------- validate / register

def validate_all(map_path, aspect, agent_name):
    """Catalog rules plus, if a map is given, the map with the new agent routed into the aspect."""
    rep = V.Report()
    cat = V.load_catalog(HERE, rep)
    V.check_catalog(cat, rep)
    if map_path:
        pm = yaml.safe_load(open(map_path))
        agents = pm["aspects"][aspect].setdefault("agents", [])
        if agent_name not in agents:
            agents.append(agent_name)
        pm["catalog"] = os.path.relpath(HERE, V.map_dir(map_path))
        tmp = tempfile.NamedTemporaryFile("w", suffix=".yaml", dir=V.map_dir(map_path),
                                          delete=False)
        yaml.safe_dump(pm, tmp, sort_keys=False)
        tmp.close()
        try:
            V.check_project_map(tmp.name, rep, {HERE: cat})
        finally:
            os.remove(tmp.name)
        rep.errors = [e.replace(tmp.name, map_path) for e in rep.errors]
    return rep


def register(map_path, aspect, agent_name):
    """Add the agent to the aspect's flow-style agents list, preserving the rest of the file verbatim."""
    text = open(map_path).read()
    pattern = re.compile(rf"(^  {re.escape(aspect)}:\n(?:    .*\n)*?    agents: \[)([^\]]*)(\])", re.M)
    m = pattern.search(text)
    if not m:
        return False
    current = [a.strip() for a in m.group(2).split(",") if a.strip()]
    if agent_name in current:
        return True
    current.append(agent_name)
    text = text[:m.start()] + m.group(1) + ", ".join(current) + m.group(3) + text[m.end():]
    open(map_path, "w").write(text)
    return True


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("request")
    ap.add_argument("--map")
    ap.add_argument("--aspect")
    ap.add_argument("--register", action="store_true")
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--budget", type=float, default=1.00)
    ap.add_argument("--no-evals", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--search", action="append", default=[], metavar="TERMS")
    opts = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)   # keep stage lines ordered with run_evals output
    if bool(opts.map) != bool(opts.aspect):
        ap.error("--map and --aspect go together")
    if opts.register and not opts.map:
        ap.error("--register needs --map and --aspect")

    rep = V.Report()
    cat = V.load_catalog(HERE, rep)
    V.check_catalog(cat, rep)
    if rep.errors:
        sys.exit("catalog does not validate; fix it first:\n" + "\n".join(rep.errors))

    allowed_tools, pack = sorted(cat["tools"]), None
    if opts.map:
        pm = yaml.safe_load(open(opts.map))
        if opts.aspect not in (pm.get("aspects") or {}):
            sys.exit(f"aspect '{opts.aspect}' not in {opts.map}")
        allowed_tools = sorted(set(V.as_list(pm["aspects"][opts.aspect].get("tools"))) |
                               set(V.as_list(pm.get("shared_tools"))))
        pack = pm.get("pack")
    offered = set()
    if opts.search:
        import registry
        for terms in opts.search:
            hits = [h["name"] for h in registry.search(terms, kind="skill", limit=10) if h["name"] in cat["skills"]]
            print(f"search   '{terms}' offers imported skills: {hits}")
            offered |= set(hits)
    inv = inventory(cat, allowed_tools, pack, offered)
    example = open(cat["agents"]["security-reviewer"][1]).read() if "security-reviewer" in cat["agents"] \
        else open(next(iter(cat["agents"].values()))[1]).read()

    # Stage 1: select + design
    print(f"stage 1  designing agent for: {opts.request}")
    out = claude_json([design_prompt(opts.request, inv, example, opts.aspect), "--model", opts.model,
                       "--json-schema", json.dumps(SCHEMA), "--max-budget-usd", str(opts.budget), *ISOLATION])
    proposal = out.get("structured_output")
    if not proposal:
        sys.exit(f"design call returned no structured output: {str(out.get('result'))[:500]}")
    cost = out.get("total_cost_usd", 0)
    print(f"         proposed '{proposal['name']}': traits={proposal['traits']} skills={proposal['skills']} "
          f"capabilities={proposal['capabilities']} new_skills={[s['name'] for s in proposal.get('new_skills') or []]}")

    if opts.dry_run:
        for rel, content in planned_files(proposal).items():
            print(f"\n----- {rel}\n{content}")
        print(f"\n(dry run, nothing written; design cost ${cost:.3f})")
        return 0

    # Stage 2 + 3: emit, validate, one repair pass
    written = []
    for attempt in (1, 2):
        remove_files(written)
        written = write_files(planned_files(proposal))
        print(f"stage 2  wrote {len(written)} file(s)")
        rep = validate_all(opts.map, opts.aspect, proposal["name"])
        if not rep.errors:
            print("stage 3  validation passed")
            break
        print("stage 3  validation failed:\n" + "\n".join(f"         {e}" for e in rep.errors))
        if attempt == 2:
            remove_files(written)
            print("\nremoved the generated files. Last proposal:\n" + json.dumps(proposal, indent=1))
            return 1
        print("         asking the model to repair")
        out = claude_json([design_prompt(opts.request, inv, example, opts.aspect, rep.errors, proposal),
                           "--model", opts.model, "--json-schema", json.dumps(SCHEMA),
                           "--max-budget-usd", str(opts.budget), *ISOLATION])
        proposal = out.get("structured_output") or proposal
        cost += out.get("total_cost_usd", 0)

    for w in written:
        print(f"         {os.path.relpath(w, HERE)}")
    if opts.no_evals:
        print(f"\ndone without evals. design cost ${cost:.3f}")
        return 0

    # Stage 4: evaluate, then register
    cmd = [sys.executable, os.path.join(HERE, "run_evals.py"), proposal["name"]]
    if opts.map:
        cmd += ["--map", opts.map, "--aspect", opts.aspect]
    print("stage 4  running evals")
    rc = subprocess.call(cmd, cwd=HERE)
    if rc != 0:
        print(f"\nevals did not all pass. '{proposal['name']}' stays in the catalog but is NOT registered. "
              f"Inspect with: run_evals.py {proposal['name']} --keep")
        return 1
    if opts.register:
        if register(opts.map, opts.aspect, proposal["name"]):
            print(f"registered '{proposal['name']}' in aspect '{opts.aspect}' of {opts.map}")
        else:
            print(f"could not edit {opts.map} automatically; add '{proposal['name']}' to aspect '{opts.aspect}' by hand")
    print(f"\ndone. design cost ${cost:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
