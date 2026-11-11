#!/usr/bin/python3
"""Test Kitbash-User-Guide.html as printed: extract its tagged files into a copy of the repo and run its commands.

Usage: /usr/bin/python3 docs/check_guide.py WORKDIR

The guide is read from the working tree, and the repo it is tested against is `git archive HEAD`, so commit
first. The archive is also installed as a plugin under scratch config dirs in WORKDIR, which leaves your own
Claude Code config alone. Free: no model call. WORKDIR is deleted and recreated on each run. Set CLAUDE_BIN to
the real claude binary if the one on PATH is a wrapper. Exits 1 on any failure.
"""
import html, os, re, shlex, shutil, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.abspath(sys.argv[1])
src = open(os.path.join(ROOT, "_html", "Kitbash-User-Guide.html"), encoding="utf-8").read()
if os.path.exists(WORK) and os.listdir(WORK) and not os.path.isdir(os.path.join(WORK, "kitbash")):
    sys.exit(f"{WORK} is not empty and is not a previous check's folder; give a new or empty folder")
shutil.rmtree(WORK, ignore_errors=True)
os.makedirs(WORK)
kb = os.path.join(WORK, "kitbash")
os.makedirs(kb)
subprocess.run(f'git -C "{ROOT}" archive HEAD | tar -x -C "{kb}"', shell=True, check=True)
PY = "/usr/bin/python3"
cat = os.path.join(kb, "catalog")
fails = 0


def run(label, args, want=0, contains=None, cwd=cat):
    global fails
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    out = r.stdout + r.stderr
    ok = (want is None or r.returncode == want) and (not contains or contains in out)
    fails += not ok
    print(f"{'ok  ' if ok else 'FAIL'}  {label}  (exit {r.returncode})")
    if not ok:
        print("      " + out[-700:].replace("\n", "\n      "))
    return out


def sh(cmd, cwd):
    subprocess.run(cmd, shell=True, cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


# 1. tagged files, exactly as printed; private/projects/ is a clone of a local remote, as in the release chapter
rem = os.path.join(WORK, "remotes")
os.makedirs(rem)
sh("git init -q --bare -b main app.git; git init -q --bare -b main projects.git", rem)
os.makedirs(os.path.join(kb, "private"))
sh(f'git clone -q "{rem}/projects.git" projects', os.path.join(kb, "private"))
tagged = re.findall(r'<pre data-file="([^"]+)">(.*?)</pre>', src, re.S)
for rel, body in tagged:
    path = os.path.join(kb, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").write(html.unescape(body) + "\n")
print(f"extracted {len(tagged)} tagged files")

# 2. every printed command
pres = re.findall(r'<div class="code( [a-z]+)?">(?:<div class="cap">(.*?)</div>)?<pre[^>]*>(.*?)</pre>', src, re.S)
cmds = []
for kind, cap, body in pres:
    text = html.unescape(re.sub(r"\\\n\s*", " ", body))
    for line in text.split("\n"):
        line = re.sub(r"\s+# .*$", "", line).strip()
        if line.startswith("/usr/bin/python3 ") and "*" not in line:
            cmds.append((kind.strip(), line))
print(f"{len(cmds)} printed commands")

SKIP_LIVE = ("publish ../private/projects/acme", "--target ~/code/acme", "make_agent.py", "release.py evals", "registry.py sync",
             "-m pip", "-c \"import", "--budget 0.50 --report")
placeholder = re.compile(r"\bNAME\b|\bAGENT\b|\bASPECT\b|\bPLAYBOOK\b|\bMAP\b|PATH/TO|\bDIR\b|\"\.\.\.\"")
target = os.path.join(WORK, "code", "acme")
os.makedirs(target)
demo = os.path.join(WORK, "kitbash-demo")
os.makedirs(demo)
in_project = []                      # commands printed for a project's .kitbash/, run in section 8
for kind, line in cmds:
    if "~/kitbash/" in line:
        in_project.append(line)
        continue
    argv = [{"/tmp/kitbash-demo": demo, "~/code/acme": target}.get(a, a) for a in shlex.split(line)]
    name = line.replace(PY + " ", "")
    if placeholder.search(line) or any(s in line for s in SKIP_LIVE):
        if "--dry-run" not in line or "make_agent" in line:
            continue
    if "release.py" in line or placeholder.search(line):
        continue
    if kind == "bill" and "--dry-run" not in argv:
        if os.path.basename(argv[1]) in ("run_evals.py", "run_playbook.py"):
            argv.append("--dry-run")
            name += "  [+--dry-run]"
    run(name[:96], argv, want=None if "validate" not in line else 0, contains=None)

# 3. flags of billed commands parse (argparse rejects unknown flags before any model call)
for script, flags in {
    "make_agent.py": ["--dry-run", "--no-evals", "--map", "--aspect", "--register", "--search", "--model", "--budget"],
    "run_evals.py": ["--all", "--map", "--aspect", "--dry-run", "--budget", "--max-turns", "--judge-model", "--keep", "--workdir", "--report"],
    "run_playbook.py": ["--run", "--dry-run", "--budget", "--max-turns", "--judge-model", "--keep", "--workdir", "--report"],
    "deploy.py": ["--target", "--dry-run", "--force"],
}.items():
    helptext = subprocess.run([PY, "scripts/" + script, "--help"], cwd=cat, capture_output=True, text=True).stdout
    missing = [f for f in flags if f not in helptext]
    fails += bool(missing)
    print(f"{'ok  ' if not missing else 'FAIL'}  flags of {script}" + (f" missing {missing}" if missing else ""))
for sub, flags in {"evals": ["--only", "--max-total", "--jobs", "--workdir"], "publish": ["--dry-run", "--trailer", "--pr-footer"]}.items():
    helptext = subprocess.run([PY, "scripts/release.py", sub, "--help"], cwd=cat, capture_output=True, text=True).stdout
    missing = [f for f in flags if f not in helptext]
    fails += bool(missing)
    print(f"{'ok  ' if not missing else 'FAIL'}  flags of release.py {sub}")

# 4. the map as printed: last line, deploy, re-deploy refusal
acme = "../private/projects/acme/project-map.yaml"
out = run("printed map validates", [PY, "scripts/validate.py", acme], contains="0 error(s), 3 warning(s)")
print("      " + out.strip().split("\n")[-1])
run("printed playbook dry-runs", [PY, "scripts/run_playbook.py", "../private/projects/acme/playbooks/triage-then-review.yaml", "--dry-run"], contains="step 1: security-reviewer")
out = run("deploy", [PY, "scripts/deploy.py", acme, "--target", target], contains="5 file(s) deployed")
for f in ("docs-reviewer", "security-reviewer", "issue-triager", "backend-engineer"):
    if f"wrote    .claude/agents/{f}.md" not in out:
        fails += 1
        print("FAIL  missing in deploy output", f)
run("evals work before routing via --map", [PY, "scripts/run_evals.py", "spec-reviewer", "--map", acme, "--aspect", "docs", "--dry-run"], contains="pack: superpowers")

# 5. printed snippets
map_path = os.path.join(kb, "private/projects/acme/project-map.yaml")
base = open(map_path).read()
exclude = base.replace("    agents: [docs-reviewer]\n", "    agents: [docs-reviewer]\n    pack_exclude:\n      skills: [verification-before-completion]\n      reason: this agent only reads and runs no commands\n")
open(map_path, "w").write(exclude)
out = run("pack_exclude snippet", [PY, "scripts/validate.py", acme], contains="0 error(s)")
out = run("pack_exclude removes pack text", [PY, "scripts/run_evals.py", "docs-reviewer", "--map", acme, "--aspect", "docs", "--dry-run"])
if "verification-before-completion" in out.split("----- denied")[0]:
    fails += 1
    print("FAIL  excluded skill still composed")
open(map_path, "w").write(base.replace("tools: [python-toolchain]", "tools: [node-toolchain]"))
run("swap tool, one line", [PY, "scripts/validate.py", acme], contains="0 error(s)")
open(map_path, "w").write(base.replace('tools: []', 'tools: [context7]'))
run("bind imported MCP", [PY, "scripts/validate.py", acme], contains="0 error(s)")
open(map_path, "w").write(base)

# 6. release as printed, against local remotes
sh(f'git init -q -b main . && mkdir -p docs services/api && echo a > docs/a.md && echo b > services/api/b.py && git add . && git commit -qm init && git remote add origin "{rem}/app.git" && git push -q -u origin main', target)
proj = os.path.join(kb, "private/projects/acme")
shutil.rmtree(os.path.join(proj, "playbooks"))    # its steps name agents the release map below drops
os.makedirs(os.path.join(proj, "claude"))
open(os.path.join(proj, "claude/app.md"), "w").write("# App\n")
rel_body = dict(tagged)["private/projects/acme/release.yaml"]
open(os.path.join(proj, "release.yaml"), "w").write(html.unescape(rel_body).replace("~/code/acme", target) + "\n")
open(os.path.join(proj, "project-map.yaml"), "w").write(base
    .replace('paths: ["docs/**", "README.md"]', 'paths: ["docs/**"]')
    .replace("    agents: [security-reviewer, issue-triager, backend-engineer]\n", "    agents: [backend-engineer]\n"))
P = "../private/projects/acme"
run("release build", [PY, "scripts/release.py", "build", P], contains="built 2 agent(s)")
sh("git add -A && git commit -qm build && git push -q -u origin HEAD:main", os.path.dirname(proj))
run("check: not ready", [PY, "scripts/release.py", "check", P], want=1, contains="no eval result")
run("publish --dry-run refuses", [PY, "scripts/release.py", "publish", P, "--dry-run"], want=1, contains="refusing to publish")
out = run("check lists plugin paths", [PY, "scripts/release.py", "check", P], want=1, contains=".claude/skills/acme/agents/docs-reviewer.md")
print("      " + "\n      ".join(out.replace(WORK, "<work>").strip().split("\n")))

# model an aspect override puts in a plugin
mp = os.path.join(proj, "project-map.yaml")
text = open(mp).read()
open(mp, "w").write(text.replace("    agents: [backend-engineer]\n", "    agents: [backend-engineer]\n    preferred_llm: claude-sonnet-5-5\n"))
run("build with aspect model", [PY, "scripts/release.py", "build", P])
agent_md = open(os.path.join(proj, "build/plugins/acme/agents/backend-engineer.md")).read()
print("      plugin model:", re.search(r"^model: .*$", agent_md, re.M).group(0))
fails += "model: claude-sonnet-5-5" not in agent_md

# 7. layout and privacy
plain = re.sub(r"<style>.*?</style>", "", src, flags=re.S)
for rel_kind in re.findall(r"<pre[^>]*>(.*?)</pre>", plain, re.S):
    for line in html.unescape(rel_kind).split("\n"):
        if len(line) > 99:
            print("LONG ", len(line), line)
            fails += 1
private_words = ["iCloud", "Obsidian", "kitbash-projects", os.environ.get("USER", "")]
email = subprocess.run(["git", "-C", ROOT, "config", "user.email"], capture_output=True, text=True).stdout.strip()
private_words.append(email.split("@")[0] + "@" if email else "")
extra = os.path.join(ROOT, "private", "guide-private-words.txt")   # optional, one word per line; private/ is ignored
if os.path.exists(extra):
    private_words += [w.strip() for w in open(extra) if w.strip()]
for word in filter(None, private_words):
    if word in plain:
        print("PRIVATE?", word)
        fails += 1
# 8. the plugin layout: the archive root is the plugin (marketplace source "./")
CLAUDE = os.environ.get("CLAUDE_BIN") or shutil.which("claude")
blocks = [html.unescape(b) for _, _, b in pres]
installs = [l.strip() for b in blocks for l in b.split("\n") if l.strip().startswith("claude plugin ")]
print(f"{len(installs)} printed install commands")
run("claude plugin validate", [CLAUDE, "plugin", "validate", kb], cwd=WORK, contains="Validation passed")
for i, group in enumerate([[l for l in installs if "--marketplace" in l],
                           [l for l in installs if "--marketplace" not in l]]):
    cfg = os.path.join(WORK, f"cfg{i}")
    os.makedirs(cfg)
    env = {**os.environ, "CLAUDE_CONFIG_DIR": cfg}
    for line in group:
        argv = [CLAUDE] + [kb if a == "manasXP/kitbash" else a for a in shlex.split(line)[1:]]
        r = subprocess.run(argv, cwd=WORK, env=env, capture_output=True, text=True)
        ok = r.returncode == 0
        fails += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {line}  [source: archive]  (exit {r.returncode})")
        if not ok:
            print("      " + (r.stdout + r.stderr)[-500:])
    listed = subprocess.run([CLAUDE, "plugin", "list"], cwd=WORK, env=env, capture_output=True, text=True).stdout
    ok = bool(group) and "kitbash@kitbash" in listed and "enabled" in listed
    fails += not ok
    print(f"{'ok  ' if ok else 'FAIL'}  install form {i + 1} leaves kitbash@kitbash enabled")

# the in-project commands, against a scratch project holding only a .kitbash/ map
proj = os.path.join(WORK, "project")
os.makedirs(os.path.join(proj, "services/api"))
open(os.path.join(proj, "services/api/app.py"), "w").write("print('api')\n")
os.makedirs(os.path.join(proj, ".kitbash"))
open(os.path.join(proj, ".kitbash/project-map.yaml"), "w").write(
    'project: acme\naspects:\n  api:\n    paths: ["services/api/**"]\n'
    '    tools: [python-toolchain, github]\n    agents: [security-reviewer]\n')
sh("git init -q -b main . && git add -A && git commit -qm init", proj)
printed_refusal = re.search(r'deploy would be refused[^<]*', src).group(0)
for line in in_project:
    argv = [a.replace("~/kitbash/", kb + "/") for a in shlex.split(line)]
    script = os.path.basename(argv[1])
    want = {"validate.py": "0 error(s)", "run_evals.py": "composed system prompt",
            "deploy.py": html.unescape(printed_refusal)}.get(script)
    run(f"in project: {line.replace(PY + ' ~/kitbash/catalog/', '')}", argv, cwd=proj, contains=want,
        want=1 if script == "deploy.py" else 0)   # a dry run that would be refused exits 1
if len(in_project) != 3:
    fails += 1
    print(f"FAIL  expected 3 in-project commands, found {len(in_project)}")
fails += os.path.exists(os.path.join(proj, ".claude"))
print(f"{'ok  ' if not os.path.exists(os.path.join(proj, '.claude')) else 'FAIL'}  dry runs wrote no .claude/")

print(f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
