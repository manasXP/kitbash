
Steps

1. Make the scripts portable.
- Replace the /Users/manaspradhan/... paths in the four catalog files with PATH lookups or environment variables. Do the same for the hardcoded /Applications paths for KiCad, Xcode and Pen.
- Move the Epicura path in recipe-validator.yaml into the private projects repo.
- Vendor pure-Python PyYAML under catalog/scripts/vendor/ so any python3 3.9 or newer works.
- Check: git archive HEAD into a temp folder and run the validator with a different Python. It should end with 0 errors and 3 warnings.

2. Find maps in the user's project.
- validate.py, run_evals.py, run_playbook.py and deploy.py look for $CLAUDE_PROJECT_DIR/.kitbash/project-map.yaml (or the current folder's) when no map is given.
- A map without a catalog: line uses the plugin's own catalog. The repo's own maps keep their explicit paths, so projects/ and private/projects/ still validate.
- --workdir defaults to .kitbash/work/.
- Check: a scratch project with only a .kitbash/ folder validates, does an eval --dry-run and deploys with --dry-run.

3. Add the user catalog layer.
- load_catalog merges the built-in catalog with .kitbash/catalog/.
- A name used in both is an error, the same rule the registry already applies to imports.
- run_evals.py currently copies fixtures from a single cat["dir"]. It should copy both fixture folders, the shipped ones and the user's.
- make_agent.py writes new agents, and --register edits, under .kitbash/ only. Nothing is written inside the plugin.
- Check: an agent in the scratch project's .kitbash/catalog/ validates and composes. A name clash is reported as an error.

4. Enforce the eval gate on deploy.
- Today "evals before routing" is a rule people follow, and only release.py enforces it.
- Reuse release.py's per-agent hash for this. run_evals.py records results in .kitbash/evals.lock.json, and deploy.py refuses any agent without a current pass.
- Changing the agent or anything it composes changes the hash, so its pass no longer counts.
- Check: deploy refuses a fresh agent, and editing one of an agent's skills makes deploy refuse it again. I can test this with fake records, so no billed run is needed.

5. Package it as a plugin.
- Add .claude-plugin/marketplace.json ("source": "./") and .claude-plugin/plugin.json with a version.
- Add skills/kitbash/SKILL.md. It covers writing the map, then validate, evals, deploy, refusing anything without a current pass.
- Free scripts are allowed through allowed-tools rules on ${CLAUDE_PLUGIN_ROOT}/catalog/scripts/.... Billed commands stay behind an explicit request from the user.
- release.py ships but the skill doesn't offer it.
- Check: claude plugin validate, then install from a local marketplace path into a clean project and walk through /kitbash:kitbash up to deploy.

Status on branch plugin-portable: steps 1 to 5 are done and committed. claude plugin validate passes with two
warnings (root CLAUDE.md is not loaded for plugin users, which is expected; no icon). Install and the user flow
were tested from a local clone in a throwaway CLAUDE_CONFIG_DIR, with evals faked.

5b. Billed walkthrough of the skill (approved 10 Nov 2026), before step 6.
- Goal: a real session that uses /kitbash:kitbash in a scratch project, up to the deploy dry run, no evals.
  Budget roughly $0.20 to $0.50.
- Confirms what only a session can: ${CLAUDE_PLUGIN_ROOT} is substituted in the skill body, the allowed-tools
  rules (quoted path, --dry-run right after the script name) run without a permission prompt, and the skill
  asks which pack and confirms aspects before writing .kitbash/project-map.yaml.
- Setup that leaves ~/.claude untouched: a git clone of this branch with the plugin files, added with
  `claude plugin marketplace add <clone path>` and `claude plugin install kitbash@kitbash` under
  CLAUDE_CONFIG_DIR=<scratch>/cfg. A fresh config dir may have no login; if so, ask before using the real one.
- Scratch project: a git repo with a services/api/ folder. Drive it with `claude -p` (cap with --max-budget-usd)
  or ask the user to run it interactively. Record what was prompted for, what was run, and the cost.
- Not exercised by a local-path install: the copy into ~/.claude/plugins/cache/, which only a GitHub install does.
- Ran 10 Nov 2026 on Claude Code 2.1.319, about $0.55 in total (Opus turn $0.25, Sonnet two turns $0.28, Haiku
  probes about $0.02). Results:
  - ${CLAUDE_PLUGIN_ROOT} is substituted in the skill body. The quoted-path Bash rules match: validate.py and
    deploy.py --dry-run ran with no prompt in the turn that invoked the skill.
  - Fixed: the catalog is outside the project, so every read of it (Read, ls, find) needed approval. Added
    Read(/${CLAUDE_PLUGIN_ROOT}/**) to allowed-tools, which also lets ls, find and grep on that folder run. This
    CLI has no Glob or Grep tools. Shell variables and brace expansion in a command still need approval, and the
    skill now says to write the plugin path out.
  - The skill asked which pack to use, whether there are other repos, and to confirm the aspects. It wrote nothing
    until the next turn. Sonnet proposed api: services/api/**, [python-toolchain, github], [security-reviewer],
    and left out backend-engineer because of its stack. The map it wrote validates with 0 errors, and the deploy
    dry run refuses security-reviewer with no eval result.
  - allowed-tools apply only in the turn that invoked the skill. After the user answered the pack question, the
    next turn needed approval for validate.py, even within one process (checked with two stream-json turns). The
    skill now asks the pack, other-repos and aspects questions in one AskUserQuestion call, whose answers arrive
    within the skill's turn. Checked in one interactive Sonnet session in the scratch project: the questions came
    as a dialog, and validate.py then ran with no prompt.
  - Not run in a session: the deploy dry run (I ran it by hand), and anything interactive (AskUserQuestion is not
    available under -p).
  - The cmux claude wrapper on PATH adds a PermissionRequest hook that can hold a -p run for up to 125 s. Use
    ~/.local/bin/claude for these tests.

6. Update the docs.
- Add install steps to the README.
- Rewrite the guide's setup chapter around the plugin and .kitbash/.
- Point the guide's commands at catalog/scripts/.
- Check: the guide checker runs against the plugin layout.

The fixtures ship as they are, about 10 MB per install, and stay read-only in the cache. Each eval already copies them into its own workspace.
