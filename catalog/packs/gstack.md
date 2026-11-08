---
name: gstack
description: Garry Tan's opinionated Claude Code toolkit (CEO, designer, eng manager, release manager, QA roles as slash commands).
source:
  url: https://github.com/garrytan/gstack
  version: v1.91.318.0
  commit: 1bd2330350a6aa978f5c91de3c0be97004d0617b
  license: MIT
  pinned: 2026-11-01
layout:
  skills: "{name}/SKILL.md"               # skills sit at the repo root, one directory each
base:
  traits: []
  skills: []
---
Registered so a map can name it; nothing is fetched while `base` is empty.

The base is empty because no gstack skill composes as plain text: each `SKILL.md` is generated from a template
and opens with a preamble that runs `~/.claude/skills/gstack/bin/gstack-skill-start`, so it expects the gstack
install and its binaries, not a system prompt. Using gstack in a project means installing it there (`git clone`
into `~/.claude/skills/gstack`, then `./setup`) rather than composing it into agents. If a future version ships a
self-contained skill, list it under `base.skills` and the loader will fetch the pinned commit.
