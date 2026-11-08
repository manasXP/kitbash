#!/usr/bin/env python3
"""Registry of imported skills and MCP servers: a SQLite database outside the vault, built from registry-sources.yaml.

Usage:
    registry.py sources                                   # trusted sources and their sync state
    registry.py sync [NAME ...]                           # fetch every source (or the named ones) into the database
    registry.py search QUERY [--kind skill|mcp] [--limit N] [--json]
    registry.py show NAME

The vault holds only registry-sources.yaml: what to trust, pinned to a commit (git sources) or filtered to a
namespace allowlist (the MCP registry API), plus the curator's capability tags for imported servers. This
script fetches that into ~/.local/share/kitbash/registry.db, so the database is disposable and rebuildable
from the vault alone. validate.load_catalog merges the rows into the catalog: an agent lists an imported
skill by name like any other, and a map binds an imported MCP server like any other tool.

Skill bodies are composed from the git checkout under ~/.cache/kitbash/sources/<source>/ (the loader
fetches it when missing); the copy in the database serves search and show. A server's config is derived
once at sync (a streamable-http remote first, else the npm, pypi or oci package) and secrets are stored as
environment variable names only; the config references them as ${NAME} for Claude Code to expand.
"""
import argparse
import glob
import json
import os
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request

import validate as V

HERE = os.path.dirname(os.path.abspath(__file__))
OFFICIAL = "io.modelcontextprotocol.registry/official"

DDL = """
CREATE TABLE IF NOT EXISTS sources (
  name TEXT PRIMARY KEY, kind TEXT NOT NULL, url TEXT NOT NULL, pin TEXT,
  config_sha TEXT NOT NULL, synced_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS skills (
  source TEXT NOT NULL REFERENCES sources(name) ON DELETE CASCADE, name TEXT NOT NULL,
  path TEXT NOT NULL, description TEXT NOT NULL, frontmatter TEXT NOT NULL, body TEXT NOT NULL,
  license TEXT, has_resources INTEGER NOT NULL, content_sha TEXT NOT NULL, imported_at TEXT NOT NULL,
  PRIMARY KEY (source, name));
CREATE TABLE IF NOT EXISTS mcp_servers (
  source TEXT NOT NULL REFERENCES sources(name) ON DELETE CASCADE, name TEXT NOT NULL,
  registry_name TEXT NOT NULL, version TEXT NOT NULL, title TEXT, description TEXT NOT NULL,
  repository_url TEXT, status TEXT NOT NULL, packages TEXT NOT NULL, remotes TEXT NOT NULL,
  server TEXT NOT NULL, transport TEXT NOT NULL, secrets TEXT NOT NULL, provides TEXT NOT NULL DEFAULT '[]',
  updated_at TEXT, imported_at TEXT NOT NULL,
  PRIMARY KEY (source, registry_name));
CREATE VIRTUAL TABLE IF NOT EXISTS skills_fts USING fts5(name, description, body, content='skills', content_rowid='rowid');
CREATE VIRTUAL TABLE IF NOT EXISTS mcp_fts USING fts5(name, title, description, content='mcp_servers', content_rowid='rowid');
"""


def open_db(readonly=False):
    if readonly:
        if not os.path.exists(V.REGISTRY_DB):
            sys.exit(f"no registry at {V.REGISTRY_DB}; run registry.py sync")
        db = sqlite3.connect(f"file:{V.REGISTRY_DB}?mode=ro", uri=True)
    else:
        os.makedirs(os.path.dirname(V.REGISTRY_DB), exist_ok=True)
        db = sqlite3.connect(V.REGISTRY_DB)
        db.executescript(DDL)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class Log(V.Report):
    """Report that also prints as it goes, so a long sync shows progress."""
    def error(self, where, msg):
        super().error(where, msg)
        print(f"error    {where}: {msg}")

    def warn(self, where, msg):
        super().warn(where, msg)
        print(f"warning  {where}: {msg}")


# ---------------------------------------------------------------- git-skills sources

def skill_license(data, folder):
    lic = data.get("license")
    if lic:
        return str(lic)
    for cand in ("LICENSE.txt", "LICENSE", "LICENSE.md"):
        p = os.path.join(folder, cand)
        if os.path.isfile(p):
            for line in open(p, errors="replace"):
                if line.strip():
                    return line.strip()
    return None


def sync_git(db, name, src, rep):
    """Upsert every skill the layout finds in the pinned checkout; drop rows no longer there. Returns the count."""
    root = V.git_checkout(os.path.join(V.SOURCE_CACHE, name), src["url"], src["commit"], name, rep)
    if root is None:
        return 0
    prefix, _, suffix = src["layout"].partition("{name}")
    seen = []
    for p in sorted(glob.glob(os.path.join(root, prefix + "*" + suffix))):
        rel = os.path.relpath(p, root)
        n = rel[len(prefix):len(rel) - len(suffix)]
        if not n or "/" in n:
            continue
        data = V.load_frontmatter(p, rep)
        if data is None:
            continue
        if data.get("name") != n:
            rep.error(f"{name}:{rel}", f"name '{data.get('name')}' does not match folder '{n}'; skipped")
            continue
        if not data.get("description"):
            rep.error(f"{name}:{rel}", "missing 'description'; skipped")
            continue
        text = open(p).read()
        body = re.sub(r"^---\n.*?\n---\n", "", text, count=1, flags=re.S).strip()
        folder = os.path.dirname(p)
        resources = [f for f in os.listdir(folder)
                     if f != os.path.basename(p) and not f.upper().startswith("LICENSE")]
        import hashlib
        db.execute("""INSERT INTO skills (source, name, path, description, frontmatter, body, license, has_resources,
                        content_sha, imported_at) VALUES (?,?,?,?,?,?,?,?,?,?)
                      ON CONFLICT(source, name) DO UPDATE SET path=excluded.path, description=excluded.description,
                        frontmatter=excluded.frontmatter, body=excluded.body, license=excluded.license,
                        has_resources=excluded.has_resources, content_sha=excluded.content_sha,
                        imported_at=CASE WHEN skills.content_sha=excluded.content_sha THEN skills.imported_at
                                         ELSE excluded.imported_at END""",
                   (name, n, rel, str(data["description"]), json.dumps(data, default=str), body,
                    skill_license(data, folder), int(bool(resources)),
                    hashlib.sha256(text.encode()).hexdigest(), now()))
        seen.append(n)
    db.execute(f"DELETE FROM skills WHERE source=? AND name NOT IN ({','.join('?' * len(seen)) or 'NULL'})", (name, *seen))
    return len(seen)


# ---------------------------------------------------------------- mcp-registry sources

def arg_values(args):
    """Command-line pieces for a registry argument list (positional values, or --name value pairs)."""
    out = []
    for a in args or []:
        if a.get("type") == "named":
            out.append(a["name"])
            if a.get("value") or a.get("default"):
                out.append(a.get("value") or a.get("default"))
        elif a.get("value") or a.get("default"):
            out.append(a.get("value") or a.get("default"))
    return out


def derive_server(sv, tool):
    """(server config, transport, secret env var names) for a registry entry, or (None, None, []) if unusable.

    A streamable-http or sse remote wins; else the npm, pypi or oci package in that order. Header values and
    environment variables become ${NAME} references; nothing secret is ever stored."""
    for r in sv.get("remotes") or []:
        if r.get("type") in ("streamable-http", "sse") and r.get("url"):
            headers, secrets = {}, []
            for h in r.get("headers") or []:
                var = re.sub(r"[^A-Z0-9]", "_", f"{tool}_{h['name']}".upper())
                headers[h["name"]] = "${" + var + "}"
                secrets.append(var)
            cfg = {"type": "http", "url": r["url"]}
            if headers:
                cfg["headers"] = headers
            return cfg, "http", secrets
    pk = {}
    for p in sv.get("packages") or []:
        pk.setdefault(p.get("registryType"), p)
    for rt in ("npm", "pypi", "oci"):
        p = pk.get(rt)
        if not p:
            continue
        ident, ver = p["identifier"], p.get("version")
        if rt == "npm":
            cmd, args = p.get("runtimeHint") or "npx", ["-y", f"{ident}@{ver}" if ver else ident, *arg_values(p.get("packageArguments"))]
        elif rt == "pypi":
            cmd, args = p.get("runtimeHint") or "uvx", [f"{ident}=={ver}" if ver else ident, *arg_values(p.get("packageArguments"))]
        else:
            cmd, args = p.get("runtimeHint") or "docker", ["run", "-i", "--rm", *arg_values(p.get("runtimeArguments")),
                                                           ident, *arg_values(p.get("packageArguments"))]
        env, secrets = {}, []
        for ev in p.get("environmentVariables") or []:
            env[ev["name"]] = "${" + ev["name"] + "}"
            if ev.get("isSecret"):
                secrets.append(ev["name"])
        variables = {}
        for a in (p.get("runtimeArguments") or []) + (p.get("packageArguments") or []):
            variables.update(a.get("variables") or {})
        def ref(m):
            # NAME={var} takes the environment variable NAME; a bare {var} takes VAR
            var = (m.group(1) or m.group(2)).upper()
            if (variables.get(m.group(2)) or {}).get("isSecret") and var not in secrets:
                secrets.append(var)
            return (m.group(1) + "=" if m.group(1) else "") + "${" + var + "}"
        args = [re.sub(r"(?:(\w+)=)?\{(\w+)\}", ref, str(a)) for a in args]
        cfg = {"type": "stdio", "command": cmd, "args": args}
        if env:
            cfg["env"] = env
        return cfg, "stdio", secrets
    return None, None, []


def fetch_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/json"}), timeout=60) as r:
        return json.load(r)


def sync_mcp(db, name, src, rep):
    """Page the registry per namespace, keep exact prefix matches, upsert; drop rows no longer listed. Returns the count."""
    api = src["api"].rstrip("/")
    provides = src.get("provides") or {}
    names = src.get("names") or {}
    seen = {}
    for ns in V.as_list(src["namespaces"]):
        cursor = None
        while True:
            q = {"search": ns + "/", "limit": 100, "version": "latest"}
            if cursor:
                q["cursor"] = cursor
            try:
                data = fetch_json(f"{api}/servers?{urllib.parse.urlencode(q)}")
            except Exception as e:  # noqa: BLE001
                rep.error(name, f"cannot read {api} for namespace '{ns}': {e}")
                return 0
            for item in data.get("servers") or []:
                sv, meta = item["server"], (item.get("_meta") or {}).get(OFFICIAL) or {}
                if not sv["name"].startswith(ns + "/"):
                    continue
                tool = names.get(sv["name"]) or sv["name"].rsplit("/", 1)[1]
                if tool in seen:
                    rep.error(name, f"'{seen[tool]}' and '{sv['name']}' both derive the tool name '{tool}'; "
                                    f"map one to another name under 'names:' in registry-sources.yaml")
                    continue
                server, transport, secrets = derive_server(sv, tool)
                if server is None:
                    rep.warn(name, f"'{sv['name']}' has no streamable-http remote or npm/pypi/oci package; skipped")
                    continue
                seen[tool] = sv["name"]
                db.execute("""INSERT INTO mcp_servers (source, name, registry_name, version, title, description,
                                repository_url, status, packages, remotes, server, transport, secrets, provides,
                                updated_at, imported_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                              ON CONFLICT(source, registry_name) DO UPDATE SET name=excluded.name, version=excluded.version,
                                title=excluded.title, description=excluded.description, repository_url=excluded.repository_url,
                                status=excluded.status, packages=excluded.packages, remotes=excluded.remotes,
                                server=excluded.server, transport=excluded.transport, secrets=excluded.secrets,
                                provides=excluded.provides, updated_at=excluded.updated_at,
                                imported_at=CASE WHEN mcp_servers.version=excluded.version THEN mcp_servers.imported_at
                                                 ELSE excluded.imported_at END""",
                           (name, tool, sv["name"], str(sv.get("version") or ""), sv.get("title"),
                            str(sv.get("description") or ""), (sv.get("repository") or {}).get("url"),
                            meta.get("status") or "active", json.dumps(sv.get("packages") or []),
                            json.dumps(sv.get("remotes") or []), json.dumps(server), transport, json.dumps(secrets),
                            json.dumps(V.as_list(provides.get(tool))), meta.get("updatedAt"), now()))
            cursor = (data.get("metadata") or {}).get("nextCursor")
            if not cursor:
                break
    for tool in set(provides) - set(seen):
        rep.error(name, f"provides names '{tool}', which no listed namespace publishes (have {sorted(seen)})")
    keep = list(seen.values())
    db.execute(f"DELETE FROM mcp_servers WHERE source=? AND registry_name NOT IN ({','.join('?' * len(keep)) or 'NULL'})",
               (name, *keep))
    return len(seen)


# ---------------------------------------------------------------- commands

def cmd_sources(opts):
    rep = Log()
    sources = V.load_sources(HERE, rep)
    db = open_db() if os.path.exists(V.REGISTRY_DB) else None
    synced = {r["name"]: r for r in db.execute("SELECT * FROM sources")} if db else {}
    for name, src in sources.items():
        row = synced.get(name)
        if row is None:
            state = "not synced"
        elif row["config_sha"] != V.source_sha(src):
            state = f"STALE (entry changed since {row['synced_at']})"
        else:
            n = db.execute("SELECT count(*) FROM skills WHERE source=?", (name,)).fetchone()[0] if src["kind"] == "git-skills" \
                else db.execute("SELECT count(*) FROM mcp_servers WHERE source=?", (name,)).fetchone()[0]
            state = f"synced {row['synced_at']}, {n} row(s)"
        pin = src.get("commit", "")[:7] if src["kind"] == "git-skills" else ", ".join(V.as_list(src.get("namespaces")))
        print(f"{name:<20} {src['kind']:<13} {pin:<24} {state}")
    print(f"database: {V.REGISTRY_DB}" + ("" if db else " (missing)"))
    return 1 if rep.errors else 0


def cmd_sync(opts):
    rep = Log()
    sources = V.load_sources(HERE, rep)
    if rep.errors:
        return 1
    names = opts.names or list(sources)
    unknown = [n for n in names if n not in sources]
    if unknown:
        sys.exit(f"unknown source(s) {unknown}; have {sorted(sources)}")
    db = open_db()
    for name in names:
        src = sources[name]
        errors_before = len(rep.errors)
        with db:
            db.execute("INSERT OR IGNORE INTO sources (name, kind, url, pin, config_sha, synced_at) VALUES (?,?,?,?,?,?)",
                       (name, src["kind"], src.get("url") or src.get("api"), src.get("commit"), "", now()))
            n = sync_git(db, name, src, rep) if src["kind"] == "git-skills" else sync_mcp(db, name, src, rep)
            if len(rep.errors) > errors_before:
                print(f"{name}: {n} row(s) written, with errors; source left marked stale")
                continue
            db.execute("UPDATE sources SET kind=?, url=?, pin=?, config_sha=?, synced_at=? WHERE name=?",
                       (src["kind"], src.get("url") or src.get("api"), src.get("commit"), V.source_sha(src), now(), name))
            print(f"{name}: {n} {'skill' if src['kind'] == 'git-skills' else 'server'}(s)")
    with db:
        db.execute("INSERT INTO skills_fts(skills_fts) VALUES('rebuild')")
        db.execute("INSERT INTO mcp_fts(mcp_fts) VALUES('rebuild')")
    return 1 if rep.errors else 0


def fts_query(text):
    return " ".join('"' + t.replace('"', "") + '"' for t in text.split()) or '""'


def search(query, kind=None, limit=10):
    """Ranked rows [{kind, name, source, description, license|transport, rank}] from the FTS tables."""
    db = open_db(readonly=True)
    q, rows = fts_query(query), []
    if kind in (None, "skill"):
        for r in db.execute("""SELECT s.name, s.source, s.description, s.license, bm25(skills_fts) AS rank
                               FROM skills_fts JOIN skills s ON s.rowid = skills_fts.rowid
                               WHERE skills_fts MATCH ? ORDER BY rank LIMIT ?""", (q, limit)):
            rows.append({"kind": "skill", "name": r["name"], "source": r["source"], "description": r["description"],
                         "license": r["license"], "rank": r["rank"]})
    if kind in (None, "mcp"):
        for r in db.execute("""SELECT m.name, m.source, m.description, m.transport, m.provides, bm25(mcp_fts) AS rank
                               FROM mcp_fts JOIN mcp_servers m ON m.rowid = mcp_fts.rowid
                               WHERE mcp_fts MATCH ? ORDER BY rank LIMIT ?""", (q, limit)):
            rows.append({"kind": "mcp", "name": r["name"], "source": r["source"], "description": r["description"],
                         "transport": r["transport"], "provides": json.loads(r["provides"]), "rank": r["rank"]})
    db.close()
    rows.sort(key=lambda r: r["rank"])
    return rows[:limit]


def cmd_search(opts):
    rows = search(opts.query, opts.kind, opts.limit)
    if opts.json:
        print(json.dumps(rows, indent=1))
    else:
        for r in rows:
            print(f"{r['kind']:<6} {r['name']:<28} {r['source']:<18} {r['description'][:100]}")
        if not rows:
            print("no match")
    return 0


def cmd_show(opts):
    db = open_db(readonly=True)
    r = db.execute("SELECT * FROM skills WHERE name=?", (opts.name,)).fetchone()
    if r:
        print(f"skill        {r['name']}  (source {r['source']}, {r['path']})")
        print(f"description  {r['description']}")
        print(f"license      {r['license']}")
        print(f"resources    {'yes: scripts/references/assets beside SKILL.md' if r['has_resources'] else 'none'}")
        print(f"checkout     {os.path.join(V.SOURCE_CACHE, r['source'], r['path'])}")
        print(f"imported     {r['imported_at']}  sha {r['content_sha'][:12]}  body {len(r['body'])} chars")
        return 0
    r = db.execute("SELECT * FROM mcp_servers WHERE name=?", (opts.name,)).fetchone()
    if r:
        print(f"mcp server   {r['name']}  (source {r['source']}, {r['registry_name']} {r['version']}, {r['status']})")
        print(f"description  {r['description']}")
        print(f"repository   {r['repository_url']}")
        print(f"provides     {json.loads(r['provides']) or '[] (bind refused until tagged in registry-sources.yaml)'}")
        print(f"server       {json.dumps(json.loads(r['server']))}")
        print(f"secrets      {json.loads(r['secrets'])}  (environment variable names; set them before an eval or deploy)")
        print(f"imported     {r['imported_at']}")
        return 0
    sys.exit(f"'{opts.name}' is not in the registry")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sources").set_defaults(fn=cmd_sources)
    p = sub.add_parser("sync"); p.add_argument("names", nargs="*"); p.set_defaults(fn=cmd_sync)
    p = sub.add_parser("search"); p.add_argument("query"); p.add_argument("--kind", choices=["skill", "mcp"])
    p.add_argument("--limit", type=int, default=10); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_search)
    p = sub.add_parser("show"); p.add_argument("name"); p.set_defaults(fn=cmd_show)
    opts = ap.parse_args()
    return opts.fn(opts)


if __name__ == "__main__":
    sys.exit(main())
