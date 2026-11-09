#!/usr/bin/env python3
"""Validate an agent catalog and the project maps that bind it.

Usage:
    validate.py                       # catalog containing this script + ../projects/*/ and ../private/projects/*/project-map.yaml
    validate.py path/to/project-map.yaml [...]
    validate.py --catalog DIR         # catalog only, no maps

Rules (see GOAL.md):
    1. preferred_llm is in the agent's llms list, and an aspect's preferred_llm is in every routed agent's list.
    2. Every skill's requirements are satisfied: required tools are not denied, and the preferred LLM meets min_model_tier.
    3. Tools bound to an aspect (plus shared_tools) provide every capability its agents require.
    4. A tool that one trait uses and another denies needs overrides.allow with a reason.
    5. A project map attaches at most one pack. The pack's base traits and skills must be satisfiable by every
       agent routed in the map: required tools not denied, min_model_tier met, capabilities provided by the
       aspect's tools; a pack trait and an agent trait must not conflict on a tool. An aspect may exclude a
       pack trait or skill under pack_exclude with a reason.
    6. Every playbook beside a map (playbooks/*.yaml) names that map; every step's agent is routed in the aspect
       the step names; every step but the last has one handoff_if, either a `command` of a tool bound to that
       aspect (plus shared_tools) or an `output` field the step's agent declares under `outputs`; every
       placeholder is a declared input; and the playbook has at least one eval with inputs, an expect_path that
       is a prefix of the step agents, and pass_if.
Plus: every referenced trait, skill, hook, fixture, tool, agent, and pack must exist, and names must match filenames.
A pack (packs/<name>.md) names a GitHub repo and a full commit; its base skills are read from that commit, fetched
into ~/.cache/kitbash/packs/<name>/ on first use (network needed once per pin; nothing is fetched for an empty base).
Imported skills and MCP servers (registry-sources.yaml, synced by registry.py into ~/.local/share/kitbash/registry.db)
are merged into the catalog by name, so the rules above apply to them unchanged. Registry rules:
    R1. registry-sources.yaml is well-formed: unique names, a known kind, a git source has url, a full commit and a
        layout with {name}; an API source has api and namespaces; provides values are non-empty lists;
        names maps a registry name to the tool name to use instead of its last segment.
    R2. A source whose entry changed since the last sync is stale: run registry.py sync NAME.
    R3. An imported name must not collide with a catalog file or another import.
    R4. A map may bind an imported MCP server only once it has provides (curated in registry-sources.yaml).
    R5. A bound imported server whose secrets name an unset environment variable is a warning.
    R6. An agent composing an imported skill that ships scripts, references or assets is a warning: only SKILL.md is composed.
    R7. registry-sources.yaml present but no database is a warning; imports are then unknown names.

Exit status is 1 if any error was found, else 0. Warnings never fail the run.
"""
import glob
import os
import re
import subprocess
import sys

try:
    import yaml
except ImportError:
    sys.exit("validate.py needs PyYAML. Install with: python3 -m pip install pyyaml")

MODEL_TIERS = ["haiku", "sonnet", "opus", "fable"]
PACK_CACHE = os.path.expanduser("~/.cache/kitbash/packs")
SOURCE_CACHE = os.path.expanduser("~/.cache/kitbash/sources")
REGISTRY_DB = os.path.expanduser("~/.local/share/kitbash/registry.db")
SOURCES_FILE = "registry-sources.yaml"
SOURCE_KINDS = {"git-skills", "mcp-registry"}
TOOL_KINDS = {"mcp", "cli"}


class Report:
    def __init__(self):
        self.errors, self.warnings = [], []

    def error(self, where, msg):
        self.errors.append(f"{where}: {msg}")

    def warn(self, where, msg):
        self.warnings.append(f"{where}: {msg}")


# ---------------------------------------------------------------- loading

def load_yaml(path, rep):
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except Exception as e:  # noqa: BLE001
        rep.error(path, f"cannot parse YAML ({e})")
        return None
    if not isinstance(data, dict):
        rep.error(path, "top level must be a mapping")
        return None
    return data


def load_frontmatter(path, rep):
    text = open(path).read()
    m = re.match(r"---\n(.*?)\n---", text, re.S)
    if not m:
        rep.error(path, "missing YAML frontmatter")
        return None
    try:
        data = yaml.safe_load(m.group(1))
    except Exception as e:  # noqa: BLE001
        rep.error(path, f"cannot parse frontmatter ({e})")
        return None
    if not isinstance(data, dict):
        rep.error(path, "frontmatter must be a mapping")
        return None
    return data


def load_named(paths, loader, rep, expected_name_from):
    """Load files into {name: (data, path)}, checking name matches filename."""
    out = {}
    for p in sorted(paths):
        data = loader(p, rep)
        if data is None:
            continue
        name = data.get("name")
        if not name:
            rep.error(p, "missing 'name'")
            continue
        expected = expected_name_from(p)
        if name != expected:
            rep.error(p, f"name '{name}' does not match path (expected '{expected}')")
        if name in out:
            rep.error(p, f"duplicate name '{name}' (also in {out[name][1]})")
        out[name] = (data, p)
    return out


def git_checkout(d, url, commit, where, rep):
    """Working tree of a repo at a full commit under d, fetched on first use; None (and an error) if it cannot be."""
    git = lambda *args: subprocess.run(["git", "-C", d, *args], capture_output=True, text=True, check=True)  # noqa: E731
    try:
        if os.path.isdir(os.path.join(d, ".git")) and git("rev-parse", "HEAD").stdout.strip() == commit:
            return d
        os.makedirs(d, exist_ok=True)
        if not os.path.isdir(os.path.join(d, ".git")):
            git("init", "-q")
        git("fetch", "-q", "--depth", "1", url, commit)
        git("checkout", "-q", "--detach", "FETCH_HEAD")
    except subprocess.CalledProcessError as e:
        rep.error(where, f"cannot fetch {url} at {commit[:7]}: {(e.stderr or '').strip()}")
        return None
    return d


def source_dir(url, commit):
    """Checkout directory of a git source, keyed by repo and pin so sources that differ only in layout share a tree."""
    return os.path.join(SOURCE_CACHE, f"{url.rstrip('/').rsplit('/', 1)[-1]}-{commit[:12]}")


def pack_checkout(name, pk, path, rep):
    """Working tree of the pack's repo at source.commit, fetched into PACK_CACHE/<name>/ on first use."""
    src = pk.get("source") or {}
    url, commit = src.get("url"), str(src.get("commit") or "")
    if not url or not re.fullmatch(r"[0-9a-f]{40}", commit):
        rep.error(path, "source needs 'url' and a full 40-character 'commit'")
        return None
    return git_checkout(os.path.join(PACK_CACHE, name), url, commit, path, rep)


def pack_members(pk, path, root, kind, rep):
    """{name: (data, path)} for the base traits or skills a pack lists, read from its checkout."""
    pattern = (pk.get("layout") or {}).get(kind)
    out = {}
    for n in as_list((pk.get("base") or {}).get(kind)):
        if not pattern:
            rep.error(path, f"base lists {kind} but layout.{kind} gives no path pattern")
            break
        rel = pattern.replace("{name}", n)
        p = os.path.join(root, rel)
        if not os.path.isfile(p):
            rep.error(path, f"base {kind[:-1]} '{n}' not found at {rel} in {pk['source']['url']} "
                            f"at {pk['source']['commit'][:7]}")
            continue
        data = load_frontmatter(p, rep)
        if data is None:
            continue
        if data.get("name") != n:
            rep.error(p, f"name '{data.get('name')}' does not match '{n}'")
        out[n] = (data, p)
    return out


def source_sha(entry):
    """Fingerprint of one registry-sources.yaml entry; the database records it so a changed entry reads as stale."""
    import hashlib
    import json
    return hashlib.sha256(json.dumps(entry, sort_keys=True, default=str).encode()).hexdigest()


def load_sources(cat, rep):
    """{name: entry} from registry-sources.yaml, or {} when the catalog has none. Rule R1."""
    path = os.path.join(cat, SOURCES_FILE)
    if not os.path.exists(path):
        return {}
    data = load_yaml(path, rep)
    out = {}
    for i, src in enumerate(as_list((data or {}).get("sources"))):
        where = f"{path} [sources[{i}]]"
        if not isinstance(src, dict) or not src.get("name"):
            rep.error(where, "each source needs a 'name'")
            continue
        name = src["name"]
        where = f"{path} [{name}]"
        if name in out:
            rep.error(where, f"duplicate source name '{name}'")
            continue
        kind = src.get("kind")
        if kind not in SOURCE_KINDS:
            rep.error(where, f"'kind' must be one of {sorted(SOURCE_KINDS)}")
            continue
        if kind == "git-skills":
            if not src.get("url") or not re.fullmatch(r"[0-9a-f]{40}", str(src.get("commit") or "")):
                rep.error(where, "a git-skills source needs 'url' and a full 40-character 'commit'")
                continue
            if "{name}" not in str(src.get("layout") or ""):
                rep.error(where, "a git-skills source needs 'layout' containing {name}, e.g. skills/{name}/SKILL.md")
                continue
        else:
            if not src.get("api") or not as_list(src.get("namespaces")):
                rep.error(where, "an mcp-registry source needs 'api' and a non-empty 'namespaces' list")
                continue
            provides = src.get("provides") or {}
            if not isinstance(provides, dict) or not all(as_list(v) for v in provides.values()):
                rep.error(where, "'provides' must map tool names to non-empty capability lists")
                continue
            names = src.get("names") or {}
            if not isinstance(names, dict) or not all(isinstance(k, str) and "/" in k and isinstance(v, str) and v
                                                       for k, v in names.items()):
                rep.error(where, "'names' must map registry names (with a '/') to non-empty tool names")
                continue
        out[name] = src
    return out


def load_registry(cat, sources, rep):
    """(imported skills, imported tools) as {name: (data, path)} from the registry database. Rules R2, R7."""
    skills, tools = {}, {}
    if not sources:
        return skills, tools
    sources_path = os.path.join(cat, SOURCES_FILE)
    if not os.path.exists(REGISTRY_DB):
        rep.warn(sources_path, f"registry not synced ({REGISTRY_DB} is missing); run registry.py sync")
        return skills, tools
    import json
    import sqlite3
    db = sqlite3.connect(f"file:{REGISTRY_DB}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    synced = {r["name"]: r for r in db.execute("SELECT name, config_sha FROM sources")}
    for name, src in sources.items():
        where = f"{sources_path} [{name}]"
        row = synced.get(name)
        if row is None or row["config_sha"] != source_sha(src):
            rep.error(where, f"registry is stale for source '{name}'; run registry.py sync {name}")
            continue
        if src["kind"] == "git-skills":
            root = None
            for r in db.execute("SELECT name, path, frontmatter, license, has_resources FROM skills WHERE source=?", (name,)):
                if root is None:
                    root = git_checkout(source_dir(src["url"], src["commit"]), src["url"], src["commit"], where, rep)
                    if root is None:
                        break
                data = json.loads(r["frontmatter"])
                data.update({"_source": name, "_license": r["license"], "_has_resources": bool(r["has_resources"])})
                p = os.path.join(root, r["path"])
                if not os.path.isfile(p):
                    rep.error(where, f"skill '{r['name']}' is not at {r['path']} in the checkout; run registry.py sync {name}")
                    continue
                skills[r["name"]] = (data, p)
        else:
            for r in db.execute("SELECT * FROM mcp_servers WHERE source=? AND status='active'", (name,)):
                data = {"name": r["name"], "kind": "mcp", "description": r["description"],
                        "provides": json.loads(r["provides"]), "server": json.loads(r["server"]),
                        "secrets": json.loads(r["secrets"]), "_source": name,
                        "_registry_name": r["registry_name"], "_version": r["version"]}
                tools[r["name"]] = (data, f"registry://{name}/{r['registry_name']}")
    db.close()
    return skills, tools


def server_config(tool):
    """Claude Code MCP server definition for a tool of kind mcp: stdio {command, args, env} or http {url, headers}."""
    srv = tool.get("server") or {}
    cfg = {"type": srv.get("type") or "stdio"}
    for k in ("command", "args", "env", "url", "headers"):
        if srv.get(k) is not None:
            cfg[k] = srv[k]
    if cfg["type"] == "stdio":
        cfg.setdefault("args", [])
    return cfg


def load_catalog(cat, rep):
    stem = lambda p: os.path.splitext(os.path.basename(p))[0]  # noqa: E731
    skill_dir = lambda p: os.path.basename(os.path.dirname(p))  # noqa: E731
    packs = load_named(glob.glob(f"{cat}/packs/*.md"), load_frontmatter, rep, stem)
    for name, (pk, path) in packs.items():
        pk["_traits"], pk["_skills"] = {}, {}
        if any(pack_base(pk)):
            root = pack_checkout(name, pk, path, rep)
            if root:
                pk["_traits"] = pack_members(pk, path, root, "traits", rep)
                pk["_skills"] = pack_members(pk, path, root, "skills", rep)
    out = {
        "dir": cat,
        "traits": load_named(glob.glob(f"{cat}/traits/*.md"), load_frontmatter, rep, stem),
        "skills": load_named(glob.glob(f"{cat}/skills/*/SKILL.md"), load_frontmatter, rep, skill_dir),
        "tools": load_named(glob.glob(f"{cat}/tools/*/*.yaml"), load_yaml, rep, stem),
        "agents": load_named(glob.glob(f"{cat}/agents/*.yaml"), load_yaml, rep, stem),
        "packs": packs,
    }
    out["sources"] = load_sources(cat, rep)
    imported_skills, imported_tools = load_registry(cat, out["sources"], rep)
    for kind, imported in (("skills", imported_skills), ("tools", imported_tools)):
        for n, (d, p) in imported.items():
            if n in out[kind]:   # rule R3; the catalog item is kept so the rest of the run stays meaningful
                rep.error(p, f"imported {kind[:-1]} '{n}' from source '{d['_source']}' collides with {out[kind][n][1]}; "
                             f"rename the catalog item or drop the import from its source")
            else:
                out[kind][n] = (d, p)
    return out


# ---------------------------------------------------------------- helpers

def as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def model_tier(model_id):
    for tier in MODEL_TIERS:
        if tier in model_id:
            return MODEL_TIERS.index(tier)
    return None


def agent_capabilities(agent, skills):
    need = set(as_list(agent.get("requires", {}).get("capabilities")))
    for s in as_list(agent.get("skills")):
        if s in skills:
            need |= set(as_list(skills[s][0].get("requires", {}).get("capabilities")))
    return need


# ---------------------------------------------------------------- catalog checks

def check_traits(traits, rep):
    for name, (t, p) in traits.items():
        for key in ("tools", "denies"):
            if key in t and not isinstance(t[key], list):
                rep.error(p, f"'{key}' must be a list")
        overlap = set(as_list(t.get("tools"))) & set(as_list(t.get("denies")))
        if overlap:
            rep.error(p, f"trait both uses and denies {sorted(overlap)}")


def check_skills(skills, rep):
    for name, (s, p) in skills.items():
        if not s.get("description"):
            rep.error(p, "missing 'description'")
        req = s.get("requires", {}) or {}
        if not isinstance(req, dict):
            rep.error(p, "'requires' must be a mapping")
            continue
        tier = req.get("min_model_tier")
        if tier and tier not in MODEL_TIERS:
            rep.error(p, f"unknown min_model_tier '{tier}' (one of {MODEL_TIERS})")


def pack_base(pk):
    """(trait names, skill names) a pack applies to every agent."""
    base = pk.get("base") or {}
    return as_list(base.get("traits")), as_list(base.get("skills"))


def check_packs(cat, rep):
    for name, (pk, p) in cat["packs"].items():
        if not pk.get("description"):
            rep.error(p, "missing 'description'")
        check_traits(pk["_traits"], rep)
        check_skills(pk["_skills"], rep)
        traits, skills = pack_base(pk)
        if not traits and not skills:
            rep.warn(p, "pack base lists no traits or skills")


def check_tools(cat, rep):
    for name, (t, p) in cat["tools"].items():
        if "_source" in t:   # imported: shape is fixed by registry.py; provides is checked where the map binds it (R4)
            continue
        if t.get("kind") not in TOOL_KINDS:
            rep.error(p, f"'kind' must be one of {sorted(TOOL_KINDS)}")
        elif os.path.basename(os.path.dirname(p)) != t["kind"]:
            rep.error(p, f"kind '{t['kind']}' but the file is under tools/{os.path.basename(os.path.dirname(p))}/")
        if not as_list(t.get("provides")):
            rep.error(p, "'provides' must list at least one capability")
        skill = t.get("skill")
        if skill and not os.path.exists(os.path.join(cat["dir"], skill)):
            rep.error(p, f"skill file not found: {skill}")


def check_agent(name, a, p, cat, rep):
    traits, skills = cat["traits"], cat["skills"]

    for key in ("name", "llms", "preferred_llm", "prompt", "evals"):
        if not a.get(key):
            rep.error(p, f"missing '{key}'")
    llms = as_list(a.get("llms"))
    preferred = a.get("preferred_llm")

    # Rule 1
    if preferred and preferred not in llms:
        rep.error(p, f"preferred_llm '{preferred}' is not in llms {llms}")

    # References
    for t in as_list(a.get("traits")):
        if t not in traits:
            rep.error(p, f"unknown trait '{t}'")
    for s in as_list(a.get("skills")):
        if s not in skills:
            rep.error(p, f"unknown skill '{s}'")
        elif skills[s][0].get("_has_resources"):   # rule R6
            rep.warn(p, f"skill '{s}' (imported from {skills[s][0]['_source']}) ships scripts, references or assets "
                        f"that are not in the workspace; only its SKILL.md body is composed")
    hooks = a.get("hooks", {}) or {}
    for event, scripts in hooks.items():
        for h in as_list(scripts):
            hp = os.path.join(cat["dir"], h)
            if not os.path.exists(hp):
                rep.error(p, f"hook not found: {h}")
            elif not os.access(hp, os.X_OK):
                rep.warn(p, f"hook is not executable: {h}")
    evals = as_list(a.get("evals"))
    for i, e in enumerate(evals):
        if not isinstance(e, dict) or not e.get("task") or not e.get("pass_if"):
            rep.error(p, f"evals[{i}] needs 'task' and 'pass_if'")
            continue
        check_fixture_refs(e["task"], set(as_list(e.get("creates"))), cat, p, f"evals[{i}]", rep)
    outputs = a.get("outputs")
    if outputs is not None and (not isinstance(outputs, dict) or not outputs
                                or not all(isinstance(k, str) and isinstance(v, str) for k, v in outputs.items())):
        rep.error(p, "'outputs' must be a non-empty mapping of field name to a one-line description")

    # Effective tool policy from traits
    uses, denied = set(), set()
    for t in as_list(a.get("traits")):
        if t in traits:
            uses |= set(as_list(traits[t][0].get("tools")))
            denied |= set(as_list(traits[t][0].get("denies")))
    overrides = a.get("overrides", {}) or {}
    allowed = set(as_list(overrides.get("allow")))
    if overrides and "allow" in overrides and not overrides.get("reason"):
        rep.error(p, "overrides.allow needs a 'reason'")
    unneeded = allowed - denied
    if unneeded:
        rep.warn(p, f"overrides.allow lists {sorted(unneeded)} which no trait denies")

    # Rule 4: trait conflicts
    conflict = (uses & denied) - allowed
    if conflict:
        rep.error(p, f"traits conflict on {sorted(conflict)}; add overrides.allow with a reason")

    # Rule 2: skill requirements
    pref_tier = model_tier(preferred or "")
    for s in as_list(a.get("skills")):
        if s not in skills:
            continue
        req = skills[s][0].get("requires", {}) or {}
        blocked = (set(as_list(req.get("tools"))) & denied) - allowed
        if blocked:
            rep.error(p, f"skill '{s}' requires {sorted(blocked)} which a trait denies")
        tier = req.get("min_model_tier")
        if tier and pref_tier is not None and pref_tier < MODEL_TIERS.index(tier):
            rep.error(p, f"skill '{s}' needs min_model_tier {tier}; preferred_llm '{preferred}' is below it")
        if tier and pref_tier is None and preferred:
            rep.warn(p, f"cannot infer tier of '{preferred}' to check skill '{s}' min_model_tier")


def check_fixture_refs(text, creates, cat, p, what, rep):
    for fx in re.findall(r"fixtures/[^\s,;'\"]+", text):
        fx = fx.rstrip(".:)")
        if fx in creates:
            if os.path.exists(os.path.join(cat["dir"], fx)):
                rep.error(p, f"{what} says it creates {fx}, but that fixture already exists")
        elif not os.path.exists(os.path.join(cat["dir"], fx)):
            rep.error(p, f"{what} references missing fixture {fx}")


def check_catalog(cat, rep):
    check_traits(cat["traits"], rep)
    check_skills(cat["skills"], rep)
    check_tools(cat, rep)
    check_packs(cat, rep)
    for name, (a, p) in cat["agents"].items():
        check_agent(name, a, p, cat, rep)


# ---------------------------------------------------------------- project map checks

def map_dir(path):
    """Directory of a project map through any symbolic link, so a map linked into a project still finds
    its catalog and its playbooks/ beside the real file."""
    return os.path.dirname(os.path.realpath(os.path.expanduser(path)))


def catalog_dir(map_path, cat_rel):
    """The catalog a map names: relative to the map's real location, or absolute (with ~ expanded)."""
    return os.path.normpath(os.path.join(map_dir(map_path), os.path.expanduser(cat_rel)))


def check_project_map(path, rep, catalogs):
    pm = load_yaml(path, rep)
    if pm is None:
        return
    if not pm.get("project"):
        rep.error(path, "missing 'project'")
    cat_rel = pm.get("catalog")
    if not cat_rel:
        rep.error(path, "missing 'catalog' (path to the catalog directory)")
        return
    cat_dir = catalog_dir(path, cat_rel)
    if not os.path.isdir(cat_dir):
        rep.error(path, f"catalog directory not found: {cat_dir}")
        return
    if cat_dir not in catalogs:
        catalogs[cat_dir] = load_catalog(cat_dir, rep)
        check_catalog(catalogs[cat_dir], rep)
    cat = catalogs[cat_dir]
    tools, agents, skills = cat["tools"], cat["agents"], cat["skills"]

    shared = set(as_list(pm.get("shared_tools")))
    for t in shared:
        if t not in tools:
            rep.error(path, f"shared_tools: unknown tool '{t}'")
        else:
            check_imported_tool(t, tools[t][0], f"{path} [shared_tools]", rep)

    # Rule 5: at most one pack, attached by name
    pack = None
    if "pack" in pm:
        if isinstance(pm["pack"], list):
            rep.error(path, f"'pack' must name exactly one pack, not a list {pm['pack']}; "
                            "one base skill set per project map so base skills cannot clash")
        elif not isinstance(pm["pack"], str):
            rep.error(path, "'pack' must be the name of one pack")
        elif pm["pack"] not in cat["packs"]:
            rep.error(path, f"unknown pack '{pm['pack']}'")
        else:
            pack = cat["packs"][pm["pack"]][0]

    aspects = pm.get("aspects") or {}
    if not isinstance(aspects, dict) or not aspects:
        rep.error(path, "'aspects' must be a non-empty mapping")
        return

    for asp, cfg in aspects.items():
        where = f"{path} [{asp}]"
        cfg = cfg or {}
        paths = as_list(cfg.get("paths"))
        if not paths or not all(isinstance(x, str) for x in paths):
            rep.error(where, "'paths' must be a non-empty list of globs")
        bound = set(as_list(cfg.get("tools")))
        for t in bound:
            if t not in tools:
                rep.error(where, f"unknown tool '{t}'")
            else:
                check_imported_tool(t, tools[t][0], where, rep)
        all_tools = (bound | shared) & set(tools)
        provided = set()
        for t in all_tools:
            provided |= set(as_list(tools[t][0].get("provides")))

        routed = as_list(cfg.get("agents"))
        if not routed:
            rep.warn(where, "aspect routes no agents")
        asp_llm = cfg.get("preferred_llm")

        excl = cfg.get("pack_exclude") or {}
        ex_traits, ex_skills = set(as_list(excl.get("traits"))), set(as_list(excl.get("skills")))
        if excl and not excl.get("reason"):
            rep.error(where, "pack_exclude needs a 'reason'")
        if excl and pack is None:
            rep.warn(where, "pack_exclude given but the map attaches no pack")
        if pack is not None:
            pk_traits, pk_skills = pack_base(pack)
            for n in ex_traits - set(pk_traits):
                rep.error(where, f"pack_exclude names trait '{n}' which the pack base does not apply")
            for n in ex_skills - set(pk_skills):
                rep.error(where, f"pack_exclude names skill '{n}' which the pack base does not apply")
        for ag in routed:
            if ag not in agents:
                rep.error(where, f"unknown agent '{ag}'")
                continue
            a = agents[ag][0]
            # Rule 3
            missing = agent_capabilities(a, skills) - provided
            if missing:
                rep.error(where, f"agent '{ag}' requires {sorted(missing)}; bound tools provide {sorted(provided)}")
            # Rule 1 at aspect level
            if asp_llm and asp_llm not in as_list(a.get("llms")):
                rep.error(where, f"aspect preferred_llm '{asp_llm}' is not in agent '{ag}' llms")
            # Rule 5: the pack's base must be satisfiable by this agent, here
            if pack is not None:
                check_pack_against_agent(where, pm["pack"], pack, ex_traits, ex_skills, ag, a, cat,
                                         provided, asp_llm or a.get("preferred_llm"), rep)

    # Rule 6: playbooks beside this map
    for pb_path in sorted(glob.glob(os.path.join(map_dir(path), "playbooks", "*.yaml"))):
        check_playbook(pb_path, path, pm, cat, rep)


def check_imported_tool(name, t, where, rep):
    """Rules R4 and R5 for an imported MCP server a map binds."""
    if "_source" not in t:
        return
    if not as_list(t.get("provides")):
        rep.error(where, f"imported server '{name}' provides no capabilities; add provides: {{{name}: [...]}} under "
                         f"source '{t['_source']}' in {SOURCES_FILE} and run registry.py sync {t['_source']}")
    for var in as_list(t.get("secrets")):
        if not os.environ.get(var):
            rep.warn(where, f"imported server '{name}' needs ${var}, which is not set in this environment")


# ---------------------------------------------------------------- playbook checks (rule 6)

PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def check_placeholders(text, inputs, where, what, rep, extra=()):
    unknown = set(PLACEHOLDER.findall(str(text))) - set(inputs) - set(extra)
    if unknown:
        rep.error(where, f"{what} uses undeclared input(s) {sorted(unknown)}; declare them under 'inputs'")


def check_playbook(pb_path, map_path, pm, cat, rep):
    pb = load_yaml(pb_path, rep)
    if pb is None:
        return
    expected = os.path.splitext(os.path.basename(pb_path))[0]
    if pb.get("name") != expected:
        rep.error(pb_path, f"name '{pb.get('name')}' does not match path (expected '{expected}')")
    if not pb.get("map"):
        rep.error(pb_path, "missing 'map' (path to the project map, relative to this file)")
    elif os.path.realpath(os.path.join(os.path.dirname(pb_path), pb["map"])) != os.path.realpath(map_path):
        rep.error(pb_path, f"'map' must name the map beside this playbooks/ directory ({os.path.basename(map_path)})")
    inputs = as_list(pb.get("inputs"))
    if not all(isinstance(x, str) for x in inputs):
        rep.error(pb_path, "'inputs' must be a list of names")
        inputs = [x for x in inputs if isinstance(x, str)]

    aspects = pm.get("aspects") or {}
    shared = set(as_list(pm.get("shared_tools")))
    steps = as_list(pb.get("steps"))
    if not steps:
        rep.error(pb_path, "'steps' must be a non-empty list")
    agents_in_order = []
    for i, st in enumerate(steps):
        where = f"{pb_path} [steps[{i}]]"
        if not isinstance(st, dict):
            rep.error(where, "step must be a mapping")
            continue
        ag, asp = st.get("agent"), st.get("aspect")
        for key in ("agent", "aspect", "task"):
            if not st.get(key):
                rep.error(where, f"missing '{key}'")
        agents_in_order.append(ag)
        cfg = aspects.get(asp) if isinstance(aspects, dict) else None
        if asp and cfg is None:
            rep.error(where, f"unknown aspect '{asp}' in {os.path.basename(map_path)}")
        if ag and ag not in cat["agents"]:
            rep.error(where, f"unknown agent '{ag}'")
        elif ag and cfg is not None and ag not in as_list((cfg or {}).get("agents")):
            rep.error(where, f"agent '{ag}' is not routed in aspect '{asp}'; add it to the aspect's agents "
                             f"(and pass its evals there) before a playbook can run it there")
        check_placeholders(st.get("task", ""), inputs, where, "task", rep)
        last = i == len(steps) - 1
        h = st.get("handoff_if")
        if last and h:
            rep.warn(where, "handoff_if on the last step is never evaluated")
        elif not last and not h:
            rep.error(where, "every step but the last needs a handoff_if ({command: tool.name, ...} or {output: field, ...})")
        if h and not last:
            bound = (set(as_list((cfg or {}).get("tools"))) | shared) & set(cat["tools"])
            check_handoff(h, ag, bound, inputs, cat, where, rep)

    evals = as_list(pb.get("evals"))
    if not evals:
        rep.error(pb_path, "'evals' must be a non-empty list; a playbook without evals cannot be trusted")
    for i, e in enumerate(evals):
        where = f"{pb_path} [evals[{i}]]"
        if not isinstance(e, dict) or not e.get("pass_if") or not e.get("expect_path"):
            rep.error(where, "needs 'inputs', 'expect_path' and 'pass_if'")
            continue
        given = e.get("inputs") or {}
        if not isinstance(given, dict):
            rep.error(where, "'inputs' must be a mapping of input name to value")
            given = {}
        missing, unknown = set(inputs) - set(given), set(given) - set(inputs)
        if missing:
            rep.error(where, f"inputs missing {sorted(missing)}")
        if unknown:
            rep.error(where, f"inputs {sorted(unknown)} are not declared by the playbook")
        for v in given.values():
            check_fixture_refs(str(v), set(), cat, where, "inputs", rep)
        path = as_list(e.get("expect_path"))
        if path != agents_in_order[:len(path)] or not path:
            rep.error(where, f"expect_path {path} is not a non-empty prefix of the step agents {agents_in_order}")


def check_handoff(h, ag, bound, inputs, cat, where, rep):
    if not isinstance(h, dict) or sum(k in h for k in ("command", "output")) != 1:
        rep.error(where, "handoff_if must be a mapping with exactly one of 'command' or 'output'")
        return
    if "command" in h:
        ref = str(h["command"])
        tool, _, cmd = ref.partition(".")
        if tool not in bound:
            rep.error(where, f"handoff command '{ref}': tool '{tool}' is not bound to this aspect or shared "
                             f"(bound: {sorted(bound)})")
            return
        commands = cat["tools"][tool][0].get("commands") or {}
        if cmd not in commands:
            rep.error(where, f"handoff command '{ref}': tool '{tool}' declares no command '{cmd}' "
                             f"(has {sorted(commands)})")
            return
        given = {k: v for k, v in h.items() if k != "command"}
        for k, v in given.items():
            check_placeholders(v, inputs, where, f"handoff field '{k}'", rep)
        needed = set(PLACEHOLDER.findall(str(commands[cmd]))) - {"report"}
        unmet = needed - set(given) - set(inputs)
        if unmet:
            rep.error(where, f"handoff command '{ref}' needs {sorted(unmet)}; give them as handoff fields or inputs")
    else:
        field = h["output"]
        ops = [k for k in ("equals", "in") if k in h]
        if len(ops) != 1:
            rep.error(where, "an output handoff needs exactly one of 'equals' or 'in'")
        declared = (cat["agents"][ag][0].get("outputs") or {}) if ag in cat["agents"] else {}
        if field not in declared:
            rep.error(where, f"output handoff on '{field}', which agent '{ag}' does not declare under 'outputs' "
                             f"(declares {sorted(declared)})")


def check_pack_against_agent(where, pack_name, pack, ex_traits, ex_skills, ag, a, cat, provided, preferred, rep):
    traits, skills = cat["traits"], cat["skills"]
    fix = "add pack_exclude with a reason in this aspect"
    uses, denied = set(), set()
    for t in as_list(a.get("traits")):
        if t in traits:
            uses |= set(as_list(traits[t][0].get("tools")))
            denied |= set(as_list(traits[t][0].get("denies")))
    allowed = set(as_list((a.get("overrides") or {}).get("allow")))
    pk_traits, pk_skills = pack_base(pack)
    pk_denied = set()
    for t in pk_traits:
        if t in ex_traits or t not in pack["_traits"]:
            continue
        pt = pack["_traits"][t][0]
        pk_uses, pk_den = set(as_list(pt.get("tools"))), set(as_list(pt.get("denies")))
        pk_denied |= pk_den
        conflict = ((pk_uses & denied) | (pk_den & uses)) - allowed
        if conflict:
            rep.error(where, f"pack '{pack_name}' trait '{t}' and agent '{ag}' traits conflict on "
                             f"{sorted(conflict)}; {fix} or overrides.allow in the agent")
    for s in as_list(a.get("skills")):
        if s in skills:
            blocked = (set(as_list((skills[s][0].get("requires") or {}).get("tools"))) & pk_denied) - allowed
            if blocked:
                rep.error(where, f"pack '{pack_name}' traits deny {sorted(blocked)} which agent '{ag}' "
                                 f"skill '{s}' requires; {fix}")
    pref_tier = model_tier(preferred or "")
    for s in pk_skills:
        if s in ex_skills or s not in pack["_skills"]:
            continue
        req = pack["_skills"][s][0].get("requires", {}) or {}
        blocked = (set(as_list(req.get("tools"))) & denied) - allowed
        if blocked:
            rep.error(where, f"pack '{pack_name}' skill '{s}' requires {sorted(blocked)} which agent '{ag}' "
                             f"denies; {fix}")
        tier = req.get("min_model_tier")
        if tier and pref_tier is not None and pref_tier < MODEL_TIERS.index(tier):
            rep.error(where, f"pack '{pack_name}' skill '{s}' needs min_model_tier {tier}; agent '{ag}' "
                             f"runs on '{preferred}' here; {fix}")
        missing = set(as_list(req.get("capabilities"))) - provided
        if missing:
            rep.error(where, f"pack '{pack_name}' skill '{s}' requires {sorted(missing)}; bound tools provide "
                             f"{sorted(provided)}; {fix}")


# ---------------------------------------------------------------- main

def main(argv):
    rep = Report()
    catalogs = {}
    here = os.path.dirname(os.path.abspath(__file__))

    if "--catalog" in argv:
        cat_dir = os.path.abspath(argv[argv.index("--catalog") + 1])
        catalogs[cat_dir] = load_catalog(cat_dir, rep)
        check_catalog(catalogs[cat_dir], rep)
        maps = [a for a in argv if a.endswith(".yaml") and a != argv[argv.index("--catalog") + 1]]
    else:
        maps = [a for a in argv if a.endswith(".yaml")]
        if not maps:
            catalogs[here] = load_catalog(here, rep)
            check_catalog(catalogs[here], rep)
            maps = sorted(glob.glob(os.path.join(here, "..", "projects", "*", "project-map.yaml")) +
                          glob.glob(os.path.join(here, "..", "private", "projects", "*", "project-map.yaml")))

    for m in maps:
        check_project_map(os.path.normpath(m), rep, catalogs)

    for w in rep.warnings:
        print(f"warning  {w}")
    for e in rep.errors:
        print(f"error    {e}")
    n_agents = sum(len(c["agents"]) for c in catalogs.values())
    n_pb = sum(len(glob.glob(os.path.join(map_dir(m), "playbooks", "*.yaml"))) for m in maps)
    print(f"{len(rep.errors)} error(s), {len(rep.warnings)} warning(s); "
          f"{n_agents} agent(s), {len(maps)} project map(s), {n_pb} playbook(s) checked")
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
