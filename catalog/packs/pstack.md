---
name: pstack
description: Poteto's engineering principles for rigorous AI-assisted development; the prove-it-works principle applied to every agent in the project.
source:
  url: https://github.com/backnotprop/pstack
  upstream: https://github.com/cursor/plugins/tree/main/pstack   # the original, a Cursor plugin; this mirror syncs from it
  version: main
  commit: 25abb38559ddbabec563646224d09eff9a250eca
  license: MIT
  pinned: 2026-11-01
layout:
  skills: skills/{name}/SKILL.md
base:
  traits: []
  skills: [principle-prove-it-works]
---
Fetched into `~/.cache/kitbash/packs/pstack/` at the pinned commit by `validate.py` on first use. The mirror has
no releases, so the pin is a commit on `main`.

pstack has two kinds of skill: `principle-*` files, short statements of a working rule that read as plain text,
and command skills (`tdd`, `sharpen`, `swarm`, ...) that expect to be invoked by name. Only principles suit a base
that every agent receives. `principle-prove-it-works` is the pstack counterpart of superpowers'
verification-before-completion; add other principles to `base.skills` when an eval shows an agent needs one.
