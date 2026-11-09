# Kitbash

Kitbash assembles AI agents from a catalog of reusable parts, validates them, and runs their evals before they can join a project.

It implements the design in the paper [A Composable Agent Taxonomy](docs/Composable-Agent-Taxonomy.pdf), which refers to it as the AgentTaxonomy project. The paper's argument is that LLM agents behave like documents, not classes, so they should be composed from flat parts with explicit merge rules and have to prove they work before they're used.

**Status:** early. The catalog, validator, eval runner, playbook runner, meta-agent, deploy script and release pipeline all exist. Generating a project map automatically is not built yet, so maps are written by hand. See [GOAL.md](GOAL.md) for the build order.

## What's here

| Path | Contents |
|---|---|
| `catalog/traits/`, `skills/`, `tools/`, `agents/`, `packs/` | The parts agents are composed from |
| `catalog/fixtures/` | Test material the evals run against |
| `catalog/scripts/` | The validator, eval runner, playbook runner, meta-agent, deploy and release scripts, and registry |
| `projects/` | Project maps, which bind tools and agents to parts of a project, plus playbooks |

## Try it

You need Python 3 with PyYAML (`python3 -m pip install pyyaml`).

These commands are free. They check the catalog and print what an agent would be composed from, without calling a model:

```sh
cd catalog
./scripts/validate.py
./scripts/run_evals.py security-reviewer --dry-run
```

Running evals needs the [Claude Code](https://code.claude.com/docs/) CLI and **bills your account**, usually under a few dollars per agent. Each eval is capped at $1 by default:

```sh
./scripts/run_evals.py security-reviewer
```

Some agents also need their own tools, such as KiCad, the Pen desktop app or an STM32 toolchain.

**Not portable yet:** some tool files and skills contain absolute paths from the author's machine. Edit them before using those tools elsewhere.

See [catalog/README.md](catalog/README.md) for the merge order, validator rules and every command.

## License

MIT, see [LICENSE](LICENSE). Vendor firmware code in the fixtures keeps its own licenses, listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
