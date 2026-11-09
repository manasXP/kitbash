
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

6. Update the docs.
- Add install steps to the README.
- Rewrite the guide's setup chapter around the plugin and .kitbash/.
- Point the guide's commands at catalog/scripts/.
- Check: the guide checker runs against the plugin layout.

The fixtures ship as they are, about 10 MB per install, and stay read-only in the cache. Each eval already copies them into its own workspace.
