---
name: superpowers
description: Evidence-before-claims discipline from the superpowers skills library, applied to every agent in the project.
source:
  url: https://github.com/obra/superpowers
  version: v7.0.1
  commit: 2ce8aa15d05bd57213e6f746f953aafb7ded7a8b
  license: MIT
  pinned: 2026-11-01
layout:
  skills: skills/{name}/SKILL.md          # where a base skill lives in the repo; {name} is the skill name
base:
  traits: []
  skills: [verification-before-completion]
---
Nothing is copied into the catalog. `validate.py` fetches the pinned commit into `~/.cache/kitbash/packs/superpowers/`
on first use and reads the base skills from there; every other script goes through that loader. To move the pin,
change `commit` to the full SHA of the new version and re-run the evals of every agent in a map that attaches this pack.

Only `verification-before-completion` is in the base. The rest of the library is designed to be loaded on demand
through a Skill tool, which the headless runner does not give agents.
