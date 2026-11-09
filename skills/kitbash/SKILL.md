---
name: kitbash
description: Set up Claude Code subagents for this project from Kitbash's catalog of tested parts. Writes the project map in .kitbash/, validates it, runs each agent's evals (billed, only on the user's go-ahead) and deploys only the agents whose evals passed. Use when the user wants project subagents, mentions Kitbash or a .kitbash/ folder, or asks to check, evaluate or deploy agents.
argument-hint: "[what you want, e.g. set up agents for this repo]"
allowed-tools:
  - Bash(python3 "${CLAUDE_PLUGIN_ROOT}/catalog/scripts/validate.py")
  - Bash(python3 "${CLAUDE_PLUGIN_ROOT}/catalog/scripts/validate.py" *)
  - Bash(python3 "${CLAUDE_PLUGIN_ROOT}/catalog/scripts/run_evals.py" --dry-run *)
  - Bash(python3 "${CLAUDE_PLUGIN_ROOT}/catalog/scripts/run_playbook.py" --dry-run *)
  - Bash(python3 "${CLAUDE_PLUGIN_ROOT}/catalog/scripts/deploy.py" --dry-run)
  - Bash(python3 "${CLAUDE_PLUGIN_ROOT}/catalog/scripts/registry.py" search *)
---
# Kitbash

Kitbash builds a project's subagents from a catalog of parts (traits, skills, tools, agents), checks the result
with a validator, proves each agent with evals, and writes `.claude/agents/` only for agents that passed.

The user asked: $ARGUMENTS

The catalog ships with this plugin at `${CLAUDE_PLUGIN_ROOT}/catalog/`. Treat it as read-only: it is replaced on
every plugin update. Everything that belongs to the project goes in its `.kitbash/` folder:

```
.kitbash/
  project-map.yaml     aspects of the project, the tools bound to each, the agents routed to each
  playbooks/           optional multi-agent sequences
  catalog/             optional project agents, traits, skills, tools, hooks, fixtures (same layout as the catalog)
  evals.lock.json      eval results, written by run_evals.py; deploy.py reads it
  work/                eval workspaces, ignored by git
```

## Commands

Run every command from the project, so the scripts find `.kitbash/`. They need Python 3.9 or later.

Free (no model call):

```sh
python3 "${CLAUDE_PLUGIN_ROOT}/catalog/scripts/validate.py"                              # the project's map and catalog
python3 "${CLAUDE_PLUGIN_ROOT}/catalog/scripts/run_evals.py" --dry-run AGENT --aspect ASPECT   # composed prompt, no run
python3 "${CLAUDE_PLUGIN_ROOT}/catalog/scripts/run_playbook.py" --dry-run .kitbash/playbooks/NAME.yaml
python3 "${CLAUDE_PLUGIN_ROOT}/catalog/scripts/deploy.py" --dry-run                      # files it would write, and refusals
python3 "${CLAUDE_PLUGIN_ROOT}/catalog/scripts/deploy.py"                                # write .claude/agents/
python3 "${CLAUDE_PLUGIN_ROOT}/catalog/scripts/registry.py" search "TERMS"               # imported skills and servers
python3 "${CLAUDE_PLUGIN_ROOT}/catalog/scripts/registry.py" sync                         # builds that index; network, a few minutes
```

The first validation fetches the map's pack from GitHub into `~/.cache/kitbash/`, so it needs the network once.

Billed to the user's Claude account, each only after the user says yes to that run:

```sh
python3 "${CLAUDE_PLUGIN_ROOT}/catalog/scripts/run_evals.py" AGENT --aspect ASPECT       # one agent, one aspect
python3 "${CLAUDE_PLUGIN_ROOT}/catalog/scripts/run_playbook.py" .kitbash/playbooks/NAME.yaml
python3 "${CLAUDE_PLUGIN_ROOT}/catalog/scripts/make_agent.py" "REQUEST" --aspect ASPECT  # designs a project agent
```

Keep `--dry-run` directly after the script name, as written above.

## Rules

- **Ask before every billed run.** Name the agent, the aspect and how many evals it has, and give the ceiling:
  each eval may spend up to `--budget` (default 1.00 USD) on the agent plus 0.20 USD on the judge. Say which local
  tools the evals need (see below). Wait for a clear yes. `make_agent.py` bills even with `--dry-run`.
- **Say once how evals run.** Each eval runs `claude -p` on the user's account in a throwaway copy of the fixtures
  under `.kitbash/work/`, with permissions bypassed inside that copy only.
- **Never get around the deploy gate.** Do not edit `.kitbash/evals.lock.json`, and do not change an agent's evals
  or pass conditions to make them pass. If the user wants to deploy without an agent that has not passed, remove
  it from the map with their agreement and say so.
- **Never edit files under `${CLAUDE_PLUGIN_ROOT}`.** To change a catalog agent for this project, copy it into
  `.kitbash/catalog/` under a new name.
- **Report outcomes as they are.** Quote validator errors and failed evals' reasons; do not summarise a failure as
  a pass.
- `release.py` is the maintainer's release flow for another repository. Do not offer it.

## Workflow

### 1. Look

Find the project root (`git rev-parse --show-toplevel`, else the current directory). If
`.kitbash/project-map.yaml` exists, run the validator and the deploy dry run and report where things stand: which
agents are routed, which have a current pass, and what is refused and why. Then do what the user asked.

### 2. Write the map

Only when there is none, or the user asks to change it.

1. Inventory the project: top-level folders, languages, build and test files, design or hardware files, docs.
   A project often spans several repositories; ask whether there are others and where.
2. Read the catalog: every file in `${CLAUDE_PLUGIN_ROOT}/catalog/agents/` and `${CLAUDE_PLUGIN_ROOT}/catalog/tools/`,
   and the one-line description at the top of each file in `${CLAUDE_PLUGIN_ROOT}/catalog/packs/`. An agent lists
   the capabilities it `requires`; a tool lists the ones it `provides`. Some catalog agents were written for one
   project's stack (their description says which); route them only where that stack matches.
3. Propose aspects: one per part of the project that needs different tools or agents, each with path globs
   relative to the project root, the tools whose capabilities its agents require, and the agents. Ask the user
   which pack to attach (one, or none; each pack's base is composed before every agent in the map) and confirm the
   aspects before writing anything.
4. Write `.kitbash/project-map.yaml`. Leave out `catalog:`: the map then uses this plugin's catalog.

```yaml
project: acme
pack: superpowers                 # optional, at most one
aspects:
  api:
    paths: ["services/api/**"]
    tools: [python-toolchain]     # must provide every capability its agents require
    agents: [security-reviewer]
  firmware:
    paths: ["firmware/**"]
    tools: [stm32-toolchain]
    agents: [firmware-engineer]
    preferred_llm: claude-opus-5-5   # optional; must be in each routed agent's llms
shared_tools: [github]            # optional, bound to every aspect
```

An aspect may also drop part of the pack base for its agents:
`pack_exclude: {skills: [NAME], reason: "..."}`. `${CLAUDE_PLUGIN_ROOT}/catalog/README.md` has every field and
validator rule, and `${CLAUDE_PLUGIN_ROOT}/projects/smart-thermostat/` is a complete example with playbooks.

### 3. Validate

Run the validator. It must end with `0 error(s)`. Three warnings, that the gstack, gsd and super-board packs list
no base, are expected. So is "registry not synced" until `registry.py sync` has run; offer it only if the user wants
imported skills or servers. Fix each error in the project's files, explaining the rule it broke.

### 4. Evals

For each routed agent, run its dry run first, then check that the tools its aspect binds are installed on this
machine (for example `kicad-cli`, `xcodebuild`, the STM32 toolchain, or the Pen or FreeCAD desktop app for MCP
tools). `${CLAUDE_PLUGIN_ROOT}/catalog/README.md` lists what each fixture set needs. Paths to these tools can be
set with environment variables such as `KICAD_CLI`, `ANDROID_HOME`, `JAVA_HOME` or `DEVELOPER_DIR`. Then ask, and
run one agent at a time. Each run records its results in `.kitbash/evals.lock.json`. On a failure, quote the
judge's reason and let the user decide what to change.

### 5. Deploy

Run the deploy dry run. While any routed agent has no record, a failed eval, or has changed since its evals ran,
it lists them with the command to run, and the deploy itself is refused. When it is clean, run the deploy, list
the files it wrote, and tell the user to commit `.kitbash/` (its `work/` folder is ignored) and the written
`.claude/` files. The agents are available in new Claude Code sessions.

## Project agents

To add an agent the catalog does not have, write it under `.kitbash/catalog/` in the catalog's layout
(`agents/NAME.yaml`, `skills/NAME/SKILL.md`, `fixtures/NAME/...`), using a catalog agent as the model. Its name
must not match a catalog name. It may use catalog traits, skills, tools and hooks by name. Its evals reference
fixtures by `fixtures/...` paths that exist in either catalog. Or, with the user's go-ahead, `make_agent.py`
designs one and writes it there. Validate, then run its evals like any other agent.
