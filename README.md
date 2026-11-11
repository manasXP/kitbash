# Kitbash

Kitbash assembles AI agents from a catalog of reusable parts, validates them, and runs their evals before they can join a project.

It implements the design in the paper [A Composable Agent Taxonomy](docs/Composable-Agent-Taxonomy.pdf), which refers to it as the AgentTaxonomy project. The paper's argument is that LLM agents behave like documents, not classes, so they should be composed from flat parts with explicit merge rules and have to prove they work before they're used.

**Status:** early. The catalog, validator, eval runner, playbook runner, meta-agent, deploy script, release pipeline and a Claude Code plugin all exist. The scripts don't generate project maps: you write one, or the plugin's skill has Claude draft one for you to confirm. See [GOAL.md](GOAL.md) for the build order.

## Install

Kitbash installs as a [Claude Code](https://code.claude.com/docs/) plugin. With Claude Code 2.1.275 or later:

```sh
claude plugin install kitbash --marketplace manasXP/kitbash
```

On an older Claude Code, add the marketplace first:

```sh
claude plugin marketplace add manasXP/kitbash
claude plugin install kitbash@kitbash
```

Inside a session, the same commands work as `/plugin ...`. You need Python 3.9 or later. PyYAML is bundled.

## Use it

Start Claude Code at your project's root and run:

```
/kitbash:kitbash set up agents for this repo
```

The skill proposes aspects of your project and the catalog agents for each. It asks which pack to attach, whether the project spans other repositories, and whether the aspects are right. Then it writes `.kitbash/project-map.yaml` and validates it. Evals run only after you say yes to each run, because they **bill your Claude account**: each eval is capped at $1 for the agent plus $0.20 for the judge. The skill deploys to `.claude/agents/` only agents with a current pass. Commit `.kitbash/` and the written `.claude/` files.

Some agents also need their own tools, such as KiCad, the Pen desktop app or an STM32 toolchain.

## Work on the catalog

Clone the repo to run the scripts yourself or to change the catalog. These commands are free. They check the catalog and print what an agent would be composed from, without calling a model:

```sh
git clone https://github.com/manasXP/kitbash.git
cd kitbash/catalog
python3 scripts/validate.py
python3 scripts/run_evals.py security-reviewer --dry-run
```

Running an agent's evals bills your account:

```sh
python3 scripts/run_evals.py security-reviewer
```

Run inside a project, the same scripts find its `.kitbash/` folder. The [user guide](docs/Kitbash-User-Guide.pdf) covers both ways in, and [catalog/README.md](catalog/README.md) has the merge order, validator rules and every command.

## What's here

| Path | Contents |
|---|---|
| `catalog/traits/`, `skills/`, `tools/`, `agents/`, `packs/` | The parts agents are composed from |
| `catalog/fixtures/` | Test material the evals run against |
| `catalog/scripts/` | The validator, eval runner, playbook runner, meta-agent, deploy and release scripts, and registry |
| `examples/` | Example project maps, which bind tools and agents to parts of a project, plus playbooks |
| `.claude-plugin/`, `skills/kitbash/` | The plugin manifest, its marketplace entry and the `/kitbash` skill |

## License

MIT, see [LICENSE](LICENSE). Vendor firmware code in the fixtures and the bundled PyYAML keep their own licenses, listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
