#!/usr/bin/env python3
"""Build, evaluate, approve and publish a project's plugins and CLAUDE.md files.

Usage:
    release.py build PROJECT            # regenerate PROJECT/build/; touches no target repo
    release.py evals PROJECT            # run the evals of every agent without a current pass
    release.py check PROJECT            # readiness to publish, and drift between targets and the build
    release.py publish PROJECT          # open a PR in each target repo that differs from the build
    release.py publish PROJECT --dry-run

PROJECT holds project-map.yaml, playbooks/, claude/ (source CLAUDE files) and release.yaml:

    target: ~/code/Project              # the map's target
    claude:                             # destination, relative to target or absolute: source under PROJECT
      project-repo/CLAUDE.md: claude/project-repo.md
    remove: [project-repo/sub/CLAUDE.md]
    eval_budget: {some-agent: 2.50}     # per run, default 1.00

build writes build/plugins/<plugin>/ and build/lock.json. The lock holds, per (aspect, agent), a hash of the agent file,
its hooks and its evals, and the eval result recorded against that hash, so any change invalidates the pass.

Approval is a merge. publish refuses unless PROJECT's repo is clean and level with origin/main, a fresh build matches
the committed one, and every agent has a passing result for its current hash. It never sets workspace trust, and a
repo plugin loads only once its exact folder is trusted. A destination outside any git repo is written directly.
"""
import argparse
import concurrent.futures
import filecmp
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

import yaml

import deploy as D
import validate as V

CATALOG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def git(repo, *args, data=False, check=True):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True)
    if check and r.returncode:
        sys.exit(f"git {' '.join(args)} failed in {repo}:\n{r.stderr.decode()}")
    return r if not check or data else r.stdout.decode().strip()


class Project:
    def __init__(self, path):
        self.dir = os.path.abspath(path)
        self.map = os.path.join(self.dir, "project-map.yaml")
        self.cfg = yaml.safe_load(open(os.path.join(self.dir, "release.yaml")))
        self.target = os.path.abspath(os.path.expanduser(self.cfg["target"]))
        self.build = os.path.join(self.dir, "build")
        self.lock_path = os.path.join(self.build, "lock.json")
        rep = V.Report()
        V.check_project_map(self.map, rep, {})
        if rep.errors:
            sys.exit("\n".join(f"error    {e}" for e in rep.errors) + "\nmap does not validate")
        self.pm = yaml.safe_load(open(self.map))
        self.cat = V.load_catalog(V.catalog_dir(self.map, self.pm["catalog"]), V.Report())

    def dest(self, path):
        return os.path.join(self.target, os.path.expanduser(path))

    def generate(self):
        """({plugin-relative path: (bytes, executable)}, {plugin: repo}, {'aspect/agent': lock entry})."""
        files, agents = D.plan_plugins(self.map, self.pm, self.cat, self.target)
        tree, repos = {}, {}
        for rel, content in files.items():
            repo, rest = os.path.join(self.target, rel).split("/.claude/skills/")
            repos[rest.split("/")[0]] = repo
            tree[rest] = (open(content[1], "rb").read(), True) if isinstance(content, tuple) else (content.encode(), False)
        entries = {}
        for (asp, ag), a in agents.items():
            h = hashlib.sha256(a["text"].encode())
            for hook in a["hooks"]:
                h.update(open(hook, "rb").read())
            h.update(yaml.safe_dump(self.cat["agents"][ag][0]["evals"]).encode())
            entries[f"{asp}/{ag}"] = {"plugin": a["plugin"], "file": a["file"], "hash": h.hexdigest()}
        return tree, repos, entries

    def lock(self):
        return json.load(open(self.lock_path)) if os.path.exists(self.lock_path) else {"agents": {}}

    def save_lock(self, lock):
        with open(self.lock_path, "w") as f:
            json.dump(lock, f, indent=2, sort_keys=True)
            f.write("\n")

    def desired(self):
        """{repo or None: {path in repo, absolute when repo is None: (bytes, executable) or None to remove}}."""
        tree, repos, _ = self.generate()
        out = {}
        for rest, content in tree.items():
            out.setdefault(repos[rest.split("/")[0]], {})[f".claude/skills/{rest}"] = content
        for dest, src in (self.cfg.get("claude") or {}).items():
            path = self.dest(dest)
            repo = D.git_root(os.path.dirname(path))
            data = (open(os.path.join(self.dir, src), "rb").read(), False)
            out.setdefault(repo, {})[os.path.relpath(path, repo) if repo else path] = data
        for dest in self.cfg.get("remove") or []:
            path = self.dest(dest)
            repo = D.git_root(os.path.dirname(path))
            out.setdefault(repo, {})[os.path.relpath(path, repo) if repo else path] = None
        return out

    def drift(self):
        """{repo or None: [(path, content or None)]}: what must change for a target to match the build."""
        out = {}
        for repo, want in self.desired().items():
            changes = []
            if repo is None:
                for path, content in want.items():
                    have = open(path, "rb").read() if os.path.exists(path) else None
                    if have != (content[0] if content else None):
                        changes.append((path, content))
            else:
                git(repo, "fetch", "-q", "origin")
                for path, content in want.items():
                    r = git(repo, "show", f"origin/main:{path}", check=False)
                    have = r.stdout if r.returncode == 0 else None
                    if have != (content[0] if content else None):
                        changes.append((path, content))
                roots = {"/".join(p.split("/")[:3]) for p in want if p.startswith(".claude/skills/")}
                for root in roots:
                    for path in git(repo, "ls-tree", "-r", "--name-only", "origin/main", root).split("\n"):
                        if path and path not in want:
                            changes.append((path, None))
            if changes:
                out[repo] = changes
        return out


def write_tree(tree, root):
    for rest, (data, executable) in tree.items():
        path = os.path.join(root, rest)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        os.chmod(path, 0o755 if executable else 0o644)


def build(p):
    tree, _, entries = p.generate()
    plugins = os.path.join(p.build, "plugins")
    shutil.rmtree(plugins, ignore_errors=True)
    write_tree(tree, plugins)
    old = p.lock()["agents"]
    for key, e in entries.items():
        if old.get(key, {}).get("hash") == e["hash"] and "evals" in old[key]:
            e["evals"] = old[key]["evals"]
    p.save_lock({"agents": entries})
    return entries


def problems(p):
    """Why this project cannot be published now."""
    out = []
    top = git(p.dir, "rev-parse", "--show-toplevel")
    git(top, "fetch", "-q", "origin")
    if git(top, "status", "--porcelain"):
        out.append(f"{top} has uncommitted changes")
    if git(top, "rev-parse", "HEAD") != git(top, "rev-parse", "origin/main"):
        out.append(f"{top} is not level with origin/main, so this build has not been approved by a merge")
    tree, _, entries = p.generate()
    with tempfile.TemporaryDirectory() as fresh:
        write_tree(tree, fresh)
        out += [f"the committed build differs from a fresh build: {d}" for d in tree_diff(fresh, os.path.join(p.build, "plugins"))]
    lock = p.lock()["agents"]
    for key, e in entries.items():
        got = lock.get(key)
        ev = (got or {}).get("evals")
        if not got or got.get("hash") != e["hash"]:
            out.append(f"{key}: the agent changed since the last build")
        elif not ev:
            out.append(f"{key}: no eval result")
        elif ev["passed"] != ev["total"] or not ev["total"]:
            out.append(f"{key}: evals passed {ev['passed']} of {ev['total']}")
    return out


def tree_diff(a, b):
    out = []
    cmp = filecmp.dircmp(a, b, ignore=[".DS_Store"])
    out += [x + " (new)" for x in cmp.left_only]
    out += [x + " (gone)" for x in cmp.right_only]
    out += [x for x in cmp.common_files if not filecmp.cmp(os.path.join(a, x), os.path.join(b, x), shallow=False)]
    for sub in cmp.common_dirs:
        out += [f"{sub}/{x}" for x in tree_diff(os.path.join(a, sub), os.path.join(b, sub))]
    return out


def passing(entry):
    ev = entry.get("evals")
    return bool(ev and ev["total"] and ev["passed"] == ev["total"])


def evals(p, opts):
    entries = build(p)
    lock = p.lock()
    guard = threading.Lock()
    spent = [0.0]
    todo = [k for k, e in entries.items() if not passing(e)]
    if opts.only:
        todo = [k for k in todo if k in opts.only]
    print(f"{len(todo)} agent(s) to evaluate, {len(entries) - len(todo)} already current; ceiling ${opts.max_total:.2f}", flush=True)
    workdir = opts.workdir or tempfile.mkdtemp(prefix="kitbash-evals-")

    def run(key):
        with guard:
            if spent[0] >= opts.max_total:
                print(f"{key}: skipped, ceiling reached at ${spent[0]:.2f}", flush=True)
                return
        asp, ag = key.split("/")
        report = os.path.join(workdir, f"{asp}-{ag}.json")
        if os.path.exists(report):
            os.remove(report)
        budget = str((p.cfg.get("eval_budget") or {}).get(ag, 1.0))
        proc = subprocess.Popen([sys.executable, os.path.join(CATALOG, "scripts", "run_evals.py"), ag, "--map", p.map, "--aspect", asp,
                                 "--budget", budget, "--workdir", workdir, "--report", report],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=CATALOG)
        for line in proc.stdout:
            print(f"{key}: {line.rstrip()}", flush=True)
        proc.wait()
        results = json.load(open(report)) if os.path.exists(report) else []
        cost = sum(r.get("cost", 0) for r in results)
        with guard:
            spent[0] += cost
            lock["agents"][key]["evals"] = {
                "date": time.strftime("%Y-%m-%d"), "cost": round(cost, 4), "budget_per_run": float(budget),
                "passed": sum(r["status"] == "pass" for r in results), "total": len(results),
                "results": [{"index": r["index"], "task": r["task"], "status": r["status"], "reason": r.get("reason", "")}
                            for r in results]}
            p.save_lock(lock)
            print(f"{key}: recorded {lock['agents'][key]['evals']['passed']}/{len(results)}, ${cost:.2f}; total ${spent[0]:.2f}", flush=True)

    with concurrent.futures.ThreadPoolExecutor(opts.jobs) as pool:
        list(pool.map(run, todo))
    bad = [k for k, e in lock["agents"].items() if not passing(e)]
    print(f"\nspent ${spent[0]:.2f}; {len(lock['agents']) - len(bad)}/{len(lock['agents'])} agents fully passing" + (f"; not passing: {bad}" if bad else ""))
    return 1 if bad else 0


def show_drift(drift):
    for repo, changes in drift.items():
        print(repo or "(outside git, written directly)")
        for path, content in changes:
            print(f"  {'remove' if content is None else 'write '} {path}")


def check(p):
    bad = problems(p)
    print("\n".join(f"not ready: {b}" for b in bad) or "ready to publish")
    drift = p.drift()
    if drift:
        print("\ntargets differ from the build:")
        show_drift(drift)
    else:
        print("targets match the build")
    return 1 if bad or drift else 0


def publish(p, opts):
    bad = problems(p)
    if bad:
        sys.exit("refusing to publish:\n" + "\n".join(f"  {b}" for b in bad))
    drift = p.drift()
    show_drift(drift)
    if opts.dry_run or not drift:
        print("\ndry run, nothing written" if opts.dry_run else "targets already match the build")
        return 0
    top = git(p.dir, "rev-parse", "--show-toplevel")
    sha = git(top, "rev-parse", "--short", "HEAD")
    branch = f"feature/kitbash-release-{sha}"
    failed = False
    for repo, changes in drift.items():
        if repo is None:
            for path, content in changes:
                if content is None:
                    os.remove(path)
                else:
                    with open(path, "wb") as f:
                        f.write(content[0])
                print(f"wrote    {path}")
            continue
        with tempfile.TemporaryDirectory() as tmp:
            wt = os.path.join(tmp, "wt")
            git(repo, "worktree", "add", "-q", "-b", branch, wt, "origin/main")
            for path, content in changes:
                full = os.path.join(wt, path)
                if content is None:
                    os.remove(full)
                else:
                    os.makedirs(os.path.dirname(full), exist_ok=True)
                    with open(full, "wb") as f:
                        f.write(content[0])
                    os.chmod(full, 0o755 if content[1] else 0o644)
                git(wt, "add", "-A", path)
            message = f"chore(agents): release the approved Kitbash build {sha}\n"
            if opts.trailer:
                message += f"\n{opts.trailer}\n"
            git(wt, "commit", "-q", "-m", message)
            git(wt, "push", "-q", "-u", "origin", branch)
            body = (f"Release of the build approved at `{sha}` in the private Kitbash projects repo. Review and eval "
                    "results are there; change these files there, not here.\n\n"
                    + "\n".join(f"- {'Removes' if c is None else 'Writes'} `{x}`" for x, c in changes)
                    + "\n\nA repo plugin loads only when a session starts at this repo's root and this exact folder is trusted.\n")
            if opts.pr_footer:
                body += f"\n{opts.pr_footer}\n"
            r = subprocess.run(["gh", "pr", "create", "--base", "main", "--head", branch,
                                "--title", f"chore(agents): release the approved Kitbash build {sha}", "--body", body],
                               cwd=wt, capture_output=True, text=True)
            print(r.stdout.strip() or f"PR not created for {repo}: {r.stderr.strip()}")
            failed |= r.returncode != 0
            git(repo, "worktree", "remove", "--force", wt)
            git(repo, "branch", "-q", "-D", branch)
    return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    for name in ("build", "check"):
        sub.add_parser(name).add_argument("project")
    e = sub.add_parser("evals")
    e.add_argument("project")
    e.add_argument("--only", nargs="*", help="aspect/agent keys; default every agent without a current pass")
    e.add_argument("--max-total", type=float, default=30.0, help="start no further agent once this many USD are spent")
    e.add_argument("--jobs", type=int, default=3)
    e.add_argument("--workdir", help="where eval workspaces go; default a temp folder")
    u = sub.add_parser("publish")
    u.add_argument("project")
    u.add_argument("--dry-run", action="store_true")
    u.add_argument("--trailer", help="last lines of each commit message")
    u.add_argument("--pr-footer", help="last lines of each PR description")
    opts = ap.parse_args()
    p = Project(opts.project)
    if opts.command == "build":
        entries = build(p)
        current = sum("evals" in e for e in entries.values())
        print(f"built {len(entries)} agent(s) into {p.build}; {current} keep a result for their current hash")
        return 0
    if opts.command == "evals":
        return evals(p, opts)
    if opts.command == "check":
        return check(p)
    return publish(p, opts)


if __name__ == "__main__":
    sys.exit(main())
