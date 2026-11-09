# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Kitbash assembles AI agents from a catalog of reusable parts, validates them, and runs their evals before they can join a project. `GOAL.md` is the spec, with dated decisions and the build order. `catalog/README.md` is the full reference for merge order, validator rules and every flag. `Composable-Agent-Taxonomy.pdf` is the paper behind the design.

Not built yet: map synthesis, a `/kitbash` skill and `csv-index` registry sources. Project maps are written by hand.

## Commands

There is no build step, test suite or linter. Run everything from `catalog/` with `/usr/bin/python3`: on this machine `./validate.py` and plain `python3` resolve to an interpreter without PyYAML and fail. That interpreter is Python 3.9, so the scripts must stay 3.9-compatible.

Free, no model call:

```sh
/usr/bin/python3 validate.py                       # catalog + ../projects/*/project-map.yaml; exit 1 on any error
/usr/bin/python3 validate.py PATH/TO/project-map.yaml                # one map, which may live outside this repo
/usr/bin/python3 run_evals.py security-reviewer --dry-run           # print composed prompt and command
/usr/bin/python3 run_playbook.py PLAYBOOK --dry-run
/usr/bin/python3 deploy.py MAP --target DIR --dry-run                # DIR must already exist
/usr/bin/python3 deploy.py MAP --target DIR --plugin --dry-run       # one plugin per git repo; each aspect must sit in one repo
/usr/bin/python3 registry.py search "pdf forms" [--kind skill|mcp]
/usr/bin/python3 registry.py sync [NAME ...]       # network, no model; under two minutes
```

A clean validator run ends with 0 errors and 3 warnings: gstack, gsd and super-board have empty pack bases on purpose.

These bill the user's account through the `claude` CLI. `--budget` caps each agent run or playbook step (default $1.00), and the judge gets $0.20:

```sh
/usr/bin/python3 run_evals.py security-reviewer    # one agent is the smallest unit; there is no per-eval selector
/usr/bin/python3 run_evals.py AGENT --map ../projects/NAME/project-map.yaml --aspect ASPECT   # with pack and MCP tools
/usr/bin/python3 run_playbook.py PLAYBOOK          # runs the playbook's evals
/usr/bin/python3 make_agent.py "..."               # also bills with --dry-run, which still makes the design call
```

Some evals need the real tool: KiCad, the Pen desktop app, the FreeCAD app with its addon, or an STM32 toolchain. `catalog/README.md` has the per-fixture requirements.

## Architecture

**`validate.py` is also the shared library.** `load_catalog` merges the catalog files, pack checkouts and registry rows by name, so imported skills and servers look like ordinary members to every script. `run_evals.py` imports it and adds `compose` and `aspect_context`. `run_playbook.py` and `deploy.py` import both, so what passes evals is exactly what gets deployed. `registry.py` and `make_agent.py` import `validate.py` only.

**An agent is composed, not inherited.** `compose` concatenates text in this order: the map's pack base (traits, then skills), the agent's traits left to right, its skills, the skills of mounted tools, `prompt`, `overrides`. Later text wins. A skill reached twice is composed once, at its first position.

**Tools bind to aspects, not agents.** A project map divides a project into aspects, each with paths, tools and routed agents. An agent requires vendor-neutral capabilities, and the aspect's tools plus `shared_tools` must provide them. Swapping a tool is a one-line map edit. A map attaches at most one pack.

**Playbooks are read by code, never by a model.** They live beside a map in `projects/<name>/playbooks/`. Steps are linear and share a workspace. Handoffs are decided by a tool command's exit status or by one field of the previous agent's `outputs` JSON block.

**Some state lives outside the repo.** All of it is disposable and rebuilt from repo files:
- `~/.cache/kitbash/packs/<name>/`: pinned pack checkouts, fetched on first use. `packs/<name>.md` holds only the link and commit.
- `~/.cache/kitbash/sources/<name>/`: pinned checkouts of git import sources. Imported skill bodies are composed from here.
- `~/.local/share/kitbash/registry.db`: the SQLite registry, built from `registry-sources.yaml`. It stays outside the vault so iCloud never syncs it mid-write.

The scripts never browse the web for leads: a map must validate and deploy from repo files and pinned sources alone.

## Working in this repo

- **Evals gate registration.** Don't route an agent in a map until its evals pass. After changing an agent or anything it composes, re-run its evals. After changing a map's pack, re-run the evals of every agent in that map.
- **Don't fix the fixtures' defects.** `fixtures/firmware/pdu/` is an unaltered snapshot of a real project whose real defects two evals target. `fixtures/backend/` and `fixtures/mobile/` carry planted defects that evals target.
- **Epicura's live map is outside this repo**, at `__Workspaces/Appliance/Epicura/epi-PM/Agents/project-map.yaml` in the vault, targeting `~/code/Epicura`. `projects/epicura/` is an older copy that names deleted repos, and `validate.py` with no arguments checks only `projects/`, so pass the live map explicitly.
- **Run backend and mobile evals through a map** (`--aspect cloud` or `--aspect ios` on the live Epicura map). The aspect's toolchain `artifacts` keep `node_modules` and `.build` out of the judge's diff.
- **Evals that create files** list them under `creates:`, and those paths must not already exist.
- **After editing `registry-sources.yaml`**, including `provides` or `names`, run `registry.py sync` or the validator reports the source as stale. Capabilities for an imported server are always tagged by hand, never inferred. Only tagged servers can be bound.
- **Before writing a project map**, ask which pack to attach and where the code root is. A project's code is usually separate from its docs workspace and spans several repos, so inventory every repo and map them all.
- **Tool and skill files contain host-specific absolute paths**, and deployed agent files inline them as they stand. A deploy is only valid for this machine.
- **`--keep` leaves workspaces in `catalog/.evals/`**, which is not gitignored. Use `--workdir` when two sessions run at once.
- **`private/` and `Composable-Agent-Taxonomy.html`** (the PDF's source) are gitignored. The PDF is tracked.
- **Check the maps directly for what's routed.** `GOAL.md` and `catalog/README.md` are partly dated narrative and can lag them. For example, `mechanical-engineer` is in the catalog but not routed in any map, so the README's `--aspect mechanical` command fails.
