# Agent catalog

Layout: `traits/`, `skills/<name>/SKILL.md`, `tools/cli/` and `tools/mcp/` (one YAML per tool, in the folder matching its `kind`, with helper scripts beside), `agents/`, `packs/<name>.md`, `registry-sources.yaml`, `hooks/`, `fixtures/`, and `scripts/` holding `validate.py`, `run_evals.py`, `make_agent.py`, `run_playbook.py`, `deploy.py`, `release.py`, `registry.py`. Run the scripts from this directory.
Projects live outside the catalog and bind it through `project-map.yaml`. Its `catalog:` is resolved against the
map's real location (symbolic links are followed, so a map linked into a project keeps working) or may be absolute,
with `~` expanded; `playbooks/` is likewise looked up beside the real file. A map with no `catalog:` uses this
catalog, the one around the scripts. A project may also hold `playbooks/`, sequences of agent invocations run by
code (defined in GOAL.md, checked by rule 6, run by `run_playbook.py`).

A project can keep its map in its own repo as `.kitbash/project-map.yaml`, with playbooks in `.kitbash/playbooks/`.
Run inside that project (from its root or any folder below it), `validate.py` with no map checks that map,
`run_evals.py --aspect NAME` uses it without `--map`, and `deploy.py` with no map deploys it into the project.
Workspaces then go in `.kitbash/work/`, which holds a `.gitignore` of `*` so they are never committed.

The project's own agents, traits, skills, tools, hooks and fixtures go in `.kitbash/catalog/`, laid out like this
catalog, and every script run inside the project merges them in by name. A name this catalog already has is an error,
as is a fixture file at a path this catalog's `fixtures/` already uses, since both fixture folders are copied into
each eval workspace. A path a file gives relative to its catalog (a tool's `skill`, an agent's `hooks`, an eval's
fixture) is looked up in the file's own catalog first, then the other, so a project agent can use
`hooks/block-network.py` from here. `${KITBASH_CATALOG}` in a project file is `.kitbash/catalog/`. Packs and registry
sources come from this catalog only. Inside a project `make_agent.py` writes there too, and it refuses to write into
a catalog installed as a Claude Code plugin.

## Semantics

Merge order for an agent: the map's pack base (its traits, then its skills), then the agent's traits left to right,
then its skills, then the skills of mounted tools, then `prompt`, then `overrides`. Later text wins, so the pack
sets the floor and the agent's own text sharpens it. A skill reached twice, as when an agent lists the skill its
mounted tool carries, is composed once, at its first position.

A **pack** is one external skill set (superpowers, gstack, GSD, pstack, super-board) described by `packs/<name>.md`: frontmatter
with `source` (the GitHub `url`, a full `commit`, `version`, `license`), a `layout` giving where a skill lives in that
repo (`skills: skills/{name}/SKILL.md`), and a `base` of traits and skills that apply to every agent. Nothing is
copied into the catalog: `validate.py` fetches the pinned commit into `~/.cache/kitbash/packs/<name>/` on first use
and every script reads the base from there, so the first run with a new pin needs the network and a pack with an
empty base fetches nothing. A project map attaches **at most one** pack (`pack: <name>`), so base skills never
overlap or clash. An aspect may leave out part of the base under
`pack_exclude: {traits: [...], skills: [...], reason: "..."}`.

In a trait, `tools` lists the tools the trait relies on and `denies` lists tools it forbids.
A tool denied by any trait stays denied unless listed under `overrides.allow` with a `reason`.

An agent gets the tools of the aspect it runs in plus `shared_tools`. Capabilities in
`requires.capabilities` (its own and its skills') must be provided by those tools, or the route is invalid.

An agent may declare `outputs: {field: description, ...}`. The playbook runner then tells it to end its final
message with a JSON block of exactly those fields, and an `output` handoff compares one of them (`equals` or `in`).
`run_evals.py` does not add that instruction, so an agent's own evals are unaffected by `outputs`. A tool may
declare gate forms of its commands for handoffs (`kicad.erc-gate` exits 5 on violations where `erc` exits 0).

**Notation.** Every file kind is YAML (with a markdown body for traits and skills); there is no symbolic notation,
decided 1 Nov 2026 once rule 6 and `run_playbook.py` existed (see Notation in GOAL.md). A one-line step chain
would replace 6 of a playbook's 23 lines and add a parser to all four scripts, which today parse nothing
beyond YAML. The notation that exists is three conventions inside scalars: `{name}` placeholders in tasks and
commands, `tool.command` references in handoffs, and `expect_path` as an ordered list that must be a prefix of
the steps. List order is merge order. Reopen only if an eval needs a branching playbook.

The scripts run on any Python 3.9 or later. They use an installed PyYAML, else the pure-Python copy in
`scripts/vendor/` (PyYAML 6.0.3, MIT licensed).

Catalog files name host-specific values instead of writing them out, and the loader resolves them in tool files and
in the catalog's own trait and skill text (pack and imported text is composed as written):

- `${KITBASH_CATALOG}` is the catalog directory, wherever it is checked out or installed.
- `${KITBASH_PYTHON}` is the interpreter running Kitbash, or the `KITBASH_PYTHON` environment variable when set.
- `${NAME:-default}` is the environment variable `NAME`, else the default, which is the usual macOS location, such as
  `${KICAD_CLI:-/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli}`. A leading `~` in a default is expanded in
  tool files, whose values reach a process with no shell, and kept in skill text, which a shell reads.

Any other `${...}`, such as a secret reference in a server config, is left for Claude Code. The variables in use are
`KICAD_CLI`, `KICAD_SYMBOL_DIR`, `KICAD_SCH_PYTHON`, `PEN_MCP_SERVER`, `ANDROID_HOME`, `JAVA_HOME` and
`DEVELOPER_DIR`.

## Validator

```
./scripts/validate.py                                  # .kitbash/project-map.yaml here or above, else this catalog + ../projects/*/project-map.yaml
./scripts/validate.py path/to/project-map.yaml [...]   # specific maps; catalog is taken from each map's `catalog` field, else this one
./scripts/validate.py --catalog DIR                    # catalog only
```

Exit status 1 on any error. Warnings are printed but do not fail the run.

Rules checked:

1. `preferred_llm` is in the agent's `llms`; an aspect's `preferred_llm` is in every routed agent's `llms`.
2. Each skill's `requires.tools` are not denied by a trait, and `preferred_llm` meets `requires.min_model_tier`.
3. The tools bound to an aspect, plus `shared_tools`, provide every capability its agents require.
4. A tool one trait uses and another denies needs `overrides.allow` with a `reason`.
5. `pack` names exactly one existing pack (a list is an error). Every base trait and skill must be satisfiable by every
   agent routed in the map: required tools not denied by the agent's traits, `min_model_tier` met by the model the agent
   runs on in that aspect, required capabilities provided by the aspect's tools plus `shared_tools`, and no pack trait
   may conflict with an agent trait on a tool. Otherwise the aspect must `pack_exclude` it with a reason.
6. Each `playbooks/*.yaml` beside a map names that map; each step's `agent` is routed in the step's `aspect`; each
   step but the last has one `handoff_if`, `{command: tool.cmd, ...}` with the tool bound there or shared and the
   command declared, or `{output: field, equals|in: ...}` with the field under the agent's `outputs`; every
   `{placeholder}` is a declared input; and `evals` is non-empty, each with `inputs` covering the declared inputs,
   an `expect_path` that is a non-empty prefix of the step agents, and `pass_if`.

Also: names match filenames, no duplicate names, and every referenced trait, skill, hook,
fixture, tool, and agent exists. An eval whose task creates a file lists it under `creates:`;
that path must not exist yet. Hooks that are not executable and overrides that allow
nothing denied are warnings.

Registry rules (imports, see below): R1 `registry-sources.yaml` is well-formed; R2 a source whose entry changed since
its last sync is stale (error naming `registry.py sync NAME`); R3 an imported name must not collide with a catalog file
or another import; R4 a map may bind an imported MCP server only once `provides` is tagged for it in the sources file;
R5 a bound imported server whose secrets name an unset environment variable is a warning; R6 an agent composing an
imported skill that ships `scripts/`, `references/` or `assets/` is a warning, since only its `SKILL.md` body is
composed; R7 a sources file with no database is a warning, and imports are then unknown names.

## Registry

```
./scripts/registry.py sources                       # trusted sources and their sync state
./scripts/registry.py sync [NAME ...]               # fetch every source (or the named ones) into the database
./scripts/registry.py search "pdf forms" [--kind skill|mcp] [--limit N] [--json]
./scripts/registry.py show pdf                      # license, resources, checkout path; for a server: config and secret names
```

Skills and MCP servers imported in bulk from trusted sources live in a SQLite registry, not in the catalog. The
vault holds only `registry-sources.yaml`: each source is a GitHub repo pinned to a full commit with a `layout`
pattern (`skills/{name}/SKILL.md`), or the official MCP registry API with a `namespaces` allowlist (exact prefix
before `/`), the curator's `provides` tags per server, and an optional `names` map for a registry name whose last
segment would collide (`com.notion/mcp: notion-mcp`). Listed today: `io.github.github` (GitHub's official server),
`io.github.modelcontextprotocol` (the reference servers' namespace, empty on the registry as of 2 Nov 2026, kept
so a later sync picks them up) and 14 vendor-owned namespaces (Microsoft, Upstash, AWS, HashiCorp, Grafana,
MongoDB, Redis, Sentry, Vercel, Notion, Stripe, Atlassian; 21 servers). 17 are tagged in the sources
file and bindable; the 4 untagged ones are unmaintained, duplicates or niche and say so in a comment there.
Capabilities by server: github-mcp-server `source-control`; playwright-mcp `browser-automation`; context7
`library-docs`; atlassian-mcp-server `issue-tracking`, `wiki-docs`; notion-mcp `knowledge-base`; stripe-mcp
`payments`; vercel-mcp `deploy-hosting`; next-devtools-mcp `nextjs-devtools`; aws-mcp `cloud-infra`;
terraform-mcp-server `infra-as-code`; sentry-mcp `error-monitoring`; mcp-grafana `observability-dashboards`;
mongodb-mcp-server `document-database`; mcp-redis, redis-mcp and upstash-mcp-server `key-value-store`, the last
also `message-queue` and `vector-search`; EnterpriseMCP `identity-directory`. `ai.smithery` was tried and dropped the
same day: 213 hosted remotes, mostly personal or test servers. Skills come from anthropics/skills (19) and from
anthropics/claude-plugins-official, one source per plugin since a source takes one layout (11 plugins, 21 skills;
frontend-design and skill-creator left out as duplicates of anthropics/skills). `registry.py sync` fetches that into
`~/.local/share/kitbash/registry.db` (outside the vault, so iCloud never syncs a database mid-write) and git
checkouts into `~/.cache/kitbash/sources/<repo>-<commit>/`, one per repo and pin however many sources share it; both
are disposable and rebuilt from the vault file.

`validate.load_catalog` merges the rows into the catalog by name, so an agent lists an imported skill like any
other and a map binds an imported server like any other tool; every script goes through that loader. A skill's body
is composed from the checkout (the loader fetches it when missing); the copy in the database serves search (FTS5)
and `show`. A server's config is derived once at sync, a streamable-http remote first, else the npm, pypi or oci
package, with every header or environment value written as `${NAME}` for Claude Code to expand; only the names are
stored, and `run_evals.py` and `deploy.py` emit the config through `validate.server_config`. Capabilities for an
imported server are never inferred: tag them under `provides` in the sources file, then sync. Licenses are stored
per row; `deploy.py` warns once per agent file that composes a proprietary skill (the Anthropic docx, pdf, pptx and
xlsx skills) and writes it anyway. `make_agent.py --search TERMS` offers the ten best-ranked imported skills for the
terms to the designing model; without it the inventory holds only the catalog's own skills.

Planned, not built: a `csv-index` source kind for purchased or downloaded listing datasets (the
claudemarketplace.net skills and MCP CSVs). Such a file holds metadata only, a name, description, category and
repo URL or registry name per row, never a SKILL.md body or a server manifest, so its rows load as searchable
candidates that cannot be composed or bound. Promotion is by hand: a chosen skill row becomes a git-skills source
pinned to a commit with its own layout, and a chosen server row becomes a namespace in the mcp-registry source,
or a derived config from its npm or docker install command when it is not on the registry. The CSV itself stays
outside the vault beside the database, under `~/.local/share/kitbash/`, with only its path and sha256 in the
sources file, since a purchased dataset may not be redistributable. Nothing bulk-clones the index: thousands of
repos with uneven layouts would mostly fail the name and collision rules, and the registry stays curated.

Filling a gap while building a map (decided 2 Nov 2026): search the registry first; if nothing fits, the operator
(the assistant in a session, not a script) browses the claudemarketplace.net listing pages for leads, each of which
links to a GitHub repo or a registry entry; a lead is verified by shallow clone (layout, frontmatter, name equals
folder, license, collisions with existing names) before it is added as a source or namespace, tagged, synced and
bound. The scripts never call the web: a map must validate and deploy from the vault file and pinned sources
alone, so there is no search flag in `make_agent.py` or `validate.py` for it. The `csv-index` source above
replaces the browsing step with a local search once the datasets are bought.

## Eval runner

```
./scripts/run_evals.py security-reviewer firmware-engineer
./scripts/run_evals.py --all
./scripts/run_evals.py ux-designer --map ../projects/smart-thermostat/project-map.yaml --aspect ux-design
./scripts/run_evals.py ux-designer --aspect ux-design   # inside a project: its .kitbash/project-map.yaml
./scripts/run_evals.py security-reviewer --dry-run      # print composed prompt and command, run nothing
```

Each eval runs `claude -p` in a fresh workspace under `.evals/` (`.kitbash/work/` inside a project) holding a copy
of `fixtures/`.
The agent is composed as the taxonomy says: the map's pack base (with `--map/--aspect`, minus that
aspect's `pack_exclude`), then trait bodies left to right, skill bodies, the skills of any mounted
tools, then the agent prompt. Denied tools become `--disallowedTools`, hooks become a `--settings`
file, and `--map/--aspect` turns the aspect's MCP tools into `--mcp-config`. Without a map no pack is
composed. Changing a map's pack changes every routed agent's composed prompt, so re-run the evals of
every agent in the map before trusting it. Runs are isolated from your own settings (`--setting-sources ""`,
`--strict-mcp-config`, no session persistence) and use bypass permissions inside the
throwaway workspace.

A second model (`--judge-model`, default claude-sonnet-5-5) reads the task, the pass condition,
the agent's final message, and the workspace diff, and returns a structured pass/fail with a reason.
Exit status 1 if any eval failed or errored. `--report FILE` writes the full results as JSON,
`--keep` leaves workspaces in place, `--budget` caps spend per agent run (default 1.00 USD), and `--workdir DIR`
puts the per-eval workspaces somewhere other than `.evals/` so two sessions do not share one.

With `--aspect`, an agent runs on the model it is deployed with there: the aspect's `preferred_llm`, else its own.
For a map in a project's `.kitbash/` folder, each agent's results are also recorded in `.kitbash/evals.lock.json`
under `aspect/agent`, against a hash of what the agent does in that aspect, taken before its evals start. That file
is meant to be committed, and `deploy.py` reads it (see Deploy).

A tool may declare `artifacts: [globs]` for side-effect files it writes (kicad-cli leaves a `.kicad_prl` beside a
board after DRC). The runner excludes them from the diff the judge sees, since they are not edits by the agent.

The runner refuses to start if the catalog does not validate.

`--map/--aspect` writes the aspect's MCP tools to a `.mcp.json` through `validate.server_config`, so an imported
http server appears as `{type: http, url, headers}` with `${NAME}` references that Claude Code expands from the
environment; set those variables before an eval or the server will not connect.

Document fixtures (`.pen` and `.FCStd`): a tool may declare `inspect` with `extensions`, an `open` command
and a `dump` command. Before the agent runs, the runner opens each matching workspace fixture with the
tool's app and dumps its structure; after the run it dumps again and gives the judge a diff of the two
dumps plus the final state, because the app does not write the file back to disk on its own. For Pen,
`tools/mcp/pen_dump.py` is the dump command; it talks to the Pen MCP server directly. The Pen desktop app
must be running, and each eval leaves its workspace copy open in the app. For FreeCAD, `tools/mcp/fcstd_dump.py`
reads the file on disk (an `.FCStd` is a zip of XML; no FreeCAD in the loop), so the agent must save, which the
mechanical-design skill requires; the FreeCAD app must be running with the freecad-mcp addon (RPC on
localhost:9875) for the agent's MCP calls to work. `fixtures/mech/bracket.FCStd` was built headless with
`freecadcmd`, which rejects single-letter spreadsheet aliases, hence `L_plate`, `T_plate`.

## Playbook runner

```
./scripts/run_playbook.py ../projects/smart-thermostat/playbooks/schematic-change-and-check.yaml   # run its evals
./scripts/run_playbook.py PLAYBOOK --run request="Add ..." file=fixtures/eda/x.kicad_sch            # one run, no judge
./scripts/run_playbook.py ../projects/smart-thermostat/playbooks/triage-and-review.yaml              # output handoff
./scripts/run_playbook.py PLAYBOOK --dry-run                                                        # print, run nothing
```

A playbook is read by this script, never by a model. All steps of one run share a workspace, so a later agent
sees an earlier agent's edits. Each step composes its agent as `run_evals.py` does, inside the step's aspect (its
tools, the map's pack, the aspect's `preferred_llm` if set). After every step but the last the handoff is decided
here: a `command` handoff runs the tool command with the inputs substituted (`{report}` is a file in the
workspace) and passes on exit 0; an `output` handoff parses the previous agent's JSON block. Each step's task
is prefixed with the diff the previous step made (paths `before/fixtures/...` and `fixtures/...`), so a later agent
knows what changed. A false handoff
stops the run. An eval whose path differs from `expect_path` fails without a judge; otherwise the judge grades
`pass_if` against every step's final message, each handoff's outcome, and the diff. `--budget` is per step.

## Deploy

```
./scripts/deploy.py ../projects/smart-thermostat/project-map.yaml --target ~/src/smart-thermostat
./scripts/deploy.py                                # inside a project: its .kitbash/project-map.yaml, into that project
./scripts/deploy.py MAP --target DIR --dry-run     # print the files, write nothing
./scripts/deploy.py MAP --target DIR --force       # overwrite agent files Kitbash did not write
```

Writes the map into a real project's `.claude/`. Each (aspect, agent) pair becomes one Claude Code subagent,
`.claude/agents/<agent>.md` (`<agent>-<aspect>.md` if the agent is routed in several aspects), with the body
composed by the same function `run_evals.py` uses, so what passed its evals is what is deployed. The frontmatter
carries the map: `model` is the aspect's `preferred_llm` or the agent's; `disallowedTools` is the trait denials
plus `mcp__<tool>` for every MCP tool in the catalog not bound to the aspect, so other aspects' tools are never
mounted; `mcpServers` inlines the aspect's MCP tools, connected only while that agent runs; `hooks` are copied to
`.claude/kitbash/hooks/` and referenced through `$CLAUDE_PROJECT_DIR`. The description ends with the aspect
name and its `paths`, which is what Claude Code reads when deciding which subagent to use. A manifest at
`.claude/kitbash.json` lists the written files; the next deploy overwrites those, removes any the map no longer
produces, and refuses to overwrite a file it did not write unless `--force` is given. The map must validate
(rule 6 included) or nothing is written. Tool and skill files name host-specific paths (KiCAD, Pen, a venv) as
placeholders, and the agent files inline the values they resolve to, so a deploy is for the machine that made it.

For a map in a project's `.kitbash/` folder, deploy also enforces the eval gate: it refuses, writing nothing, while
any routed agent has no record in `.kitbash/evals.lock.json`, failed one of its evals, or has changed since they ran,
and names the `run_evals.py` command for each. `--dry-run` lists the same refusals and exits 1. The hash covers the
model, disallowed tools, MCP config, composed prompt, hook scripts and evals, not the agent's name or description,
so routing an agent into a second aspect or editing an aspect's `paths` keeps its pass. Catalog directories and the
interpreter are replaced by their placeholders before hashing, so a plugin update or a moved project keeps every
pass whose composed text is unchanged, while an update that changes a skill refuses only the agents composing it.
Values resolved from `${NAME:-default}` are hashed as resolved, so a pass recorded on one machine counts on another
only where those tools sit at the same paths. Maps outside a `.kitbash/` folder have no gate here; `release.py`
gates its own.

## Release

```
./scripts/release.py build PROJECT      # regenerate PROJECT/build/; touches no target repo
./scripts/release.py evals PROJECT      # bills: run the evals of every agent without a current pass (--max-total, default $30)
./scripts/release.py check PROJECT      # readiness to publish, and drift between targets and the build
./scripts/release.py publish PROJECT    # open a PR in each target repo that differs (--dry-run to list)
```

Release is how a project's plugins and CLAUDE files reach its repos. Project content is private, so it lives in a
private repo checked out at `private/projects/`, which this repo gitignores; the catalog and these scripts stay public.
A project folder holds `project-map.yaml`, `playbooks/`, `release.yaml`, `claude/` (hand-written CLAUDE files) and
`build/`. The options of `release.yaml` are in the docstring of `release.py`.

`build` generates `build/plugins/<plugin>/`, one plugin per git repo, grouping aspects by the checkout holding their
paths, which may be absolute and outside the target. The agent bodies are the same text `deploy.py` writes.
`build/lock.json` records, per (aspect, agent), a hash of the agent file, its hooks and its evals, and `evals` records
the result against that hash, so any change invalidates the pass. Fixtures are not in the hash.

Merging a PR in the private repo is the approval: its diff is exactly what each agent will receive, beside the eval
result for that text. `publish` refuses unless that repo is clean and level with `origin/main`, a fresh build matches
the committed one, and every agent has a passing result for its current hash. It then opens one PR per target repo
from a throwaway worktree, so checkouts stay as they are. A destination outside any git repo, such as a project's docs
workspace, is written directly. Tested end to end against scratch remotes, including each refusal.

A plugin gives per-repo tool scope, not per-agent, and loads only when a session starts at the repo root, not in a
subfolder. Plugin subagents ignore `hooks` and `mcpServers`, so an agent's hooks go to the plugin's `hooks/hooks.json`
behind `hooks/only-for-agents.py`, which matches `agent_type` (`<plugin>:<agent>`), and a map that binds an MCP tool is
refused. A plugin cannot carry a `CLAUDE.md`, so those are separate destinations. It loads only once that exact folder
is trusted: `claude -p` or a trusted parent is not enough, and nothing warns that it did not load. `publish` never sets
trust. Tested on the five Epicura repos on 9 Nov 2026: each loaded as `<plugin>@skills-dir` once trusted, and in
`epicura-cloud` the hook blocked `security-reviewer` and left the main session alone.

## Firmware fixture

`fixtures/firmware/pdu/` is a snapshot of a real project, pdu-firmware (STM32G474RE, 30 kW PDU,
github.com/manasXP/pdu-firmware at c70311f plus the working tree of 1 Nov 2026), minus `.git`,
`build/`, `docs/`, CI and the Cube driver cache. The source was not altered; two of the
firmware-engineer evals target defects the real code has. `scripts/build.sh`, `test.sh` and
`flash.sh` were added to match the commands `tools/cli/stm32-toolchain.yaml` declares. `build.sh`
rebuilds from clean, treats warnings in `Core/` and `App/` as errors, and needs an
arm-none-eabi toolchain that ships newlib: `$PREFIX`, then `~/.local/arm-gnu-toolchain`, then
PATH. Homebrew's `arm-none-eabi-gcc` has no C library and cannot link it. `test.sh` is a smoke
test (build plus ELF checks); the project has no unit-test framework. `flash.sh` exits 2 with a
clear message when no ST-Link programmer is installed, which one eval relies on.

## Mechanical fixture

`fixtures/mech/bracket.FCStd` is a 60 x 40 x 4 mm plate with one centred M5 clearance hole, built headless on
2 Nov 2026 (`fixtures/mech/params.md` lists it). Every dimension is an aliased cell in a `Params` spreadsheet
(columns Name, Value (mm), Source) and every object property is an expression on an alias, never a literal:
Plate (Part::Box), Hole (Part::Cylinder placed by `Params.L_plate / 2`), Bracket (Part::Cut). This is the
convention of the owner's own models (EverProtect, EverMerge), and `skills/mechanical-design/SKILL.md` requires
it: read Params and the tree first, change dimensions through Params cells, give a new dimension its own row
with a Source note (`decided:`, `inference:`, `PLACEHOLDER:`), bind with `setExpression`, one change per
request, recompute, check validity, save. `agents/mechanical-engineer.yaml` requires `mechanical-cad`, which
`tools/mcp/freecad.yaml` provides through `uvx freecad-mcp`; its two evals add a second hole on a new
`hole_pitch` alias and change thickness through `T_plate` alone. They have not been run: the FreeCAD app must
be up with the freecad-mcp addon, and port 9875 was closed when the set was built. No map routes the agent today,
so running them also needs an aspect that binds `freecad`. To rebuild the fixture,
feed a script to `/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd` on stdin ending with `exit()`
and pass the output path through an environment variable: `-c` waits on stdin and every positional argument
is taken as a file to open.

## Backend and mobile fixtures

`fixtures/backend/recipe-engine` (Python 3, standard library `unittest`) and `fixtures/backend/api` (Fastify 5,
Zod, Vitest; `pnpm install` first) are cut-down versions of the Epicura CM5 recipe engine and cloud API, each
with one planted defect the backend-engineer evals target: `CookingSession.advance()` never reaches DONE, and
`POST /recipes` casts its body instead of parsing it. `fixtures/mobile/EpicuraKit` (Swift package, XCTest,
`swift test`) and `fixtures/mobile/android-core` (Kotlin, JUnit 5, no Gradle wrapper on purpose) carry the same
planted defect, a BLE provisioning frame whose length byte is a character count instead of a UTF-8 byte count;
the Kotlin one has no build tool on PATH, though a Gradle cached under `~/.gradle` ran it in the first eval, so that
eval accepts a real run or an honest report that none was possible. `xcode-select` here points at
the Command Line Tools, which ship no XCTest, so `swift test` needs `DEVELOPER_DIR` set to Xcode's Developer
directory (recorded in `tools/cli/xcode-toolchain.yaml`). Installs and builds in these fixtures write
`node_modules` and `.build`, which the toolchain tools declare as `artifacts`, so run the evals through the map
(`--aspect cloud` for backend-engineer and `--aspect ios` for mobile-engineer on the Epicura map, see
`projects/epicura/README.md`) or the judge's diff is swamped. Written 2 Nov 2026.

## Recipe fixtures and tools

`tools/cli/yt_transcript.py` (standard library plus `yt-dlp` on PATH) fetches a video's caption track, manual first
then auto-generated, strips WebVTT tags and the rolling duplicate lines, and prints `[mm:ss]` lines; exit 2 means
no captions, 3 means yt-dlp failed. YouTube rate-limits caption fetches (HTTP 429 after two in a row on 2 Nov 2026),
so the recipe-author evals that hit a URL accept an honest failure report. `tools/cli/recipe_validate.py` imports
`epicura_recipe` from the real checkout (`EPICURA_RECIPE_ENGINE`) and exits 5 on an invalid file, so it doubles as a
playbook gate; it runs under `${KITBASH_PYTHON}`, which must have pydantic (on this machine, `/usr/bin/python3`). `fixtures/recipes/` holds the real Kanda
Poha caption track, a hand-written infeasible medu vada transcript, copies of the project's five recipes for the
dispenser convention (ASD boxes 1 cumin, 2 mustard, 3 turmeric, 4 chili, 5 salt, 6 urad dal; two CID trays; SLD oil
and water), and an empty `out/` the evals write into. Written 2 Nov 2026.

## Meta-agent

```
./scripts/make_agent.py "an agent that triages incoming GitHub issues"
./scripts/make_agent.py "..." --map ../projects/smart-thermostat/project-map.yaml --aspect api --register
./scripts/make_agent.py "..." --dry-run        # print the proposal, write nothing
./scripts/make_agent.py "..." --no-evals       # stop after validation
```

Four stages. One headless Claude call (`--model`, default claude-opus-5-5) reads the catalog
inventory and returns a structured proposal: traits, skills, capabilities, models, prompt, evals,
the fixtures those evals need, and at most one new skill if nothing in the catalog covers the job.
The script writes `agents/<name>.yaml`, `fixtures/<name>/…`, and any new `skills/<name>/SKILL.md`,
then runs the validator. On failure the errors go back to the model for one repair pass; if it still
fails, the generated files are removed and the last proposal is printed. On success it runs
`run_evals.py` for the new agent. With `--register` and an all-pass, the agent name is added to the
aspect's `agents` list in the map, editing only that line. Nothing is registered on a failed eval.

With `--map/--aspect`, the model may only require capabilities provided by that aspect's tools
plus `shared_tools`, the inventory shows it the map's pack base so the proposal does not repeat it,
validation includes the map with the new agent routed in (so rule 5 covers the new agent), and the
evals run through the map with the pack composed first.
Generated files are never overwritten; a name clash aborts before writing.
