---
name: gsd
description: Get Shit Done, a meta-prompting and spec-driven development system for Claude Code (phases, plans, milestones).
source:
  url: https://github.com/open-gsd/gsd-core
  upstream: https://github.com/gsd-build/get-shit-done   # the original by glittercowboy, archived; development moved here
  version: v1.19.0
  commit: 9dc57a772195de423ab788e4d0d8734b162db35d
  license: MIT
  pinned: 2026-11-01
layout:
  skills: skills/{name}/SKILL.md
base:
  traits: []
  skills: []
---
Registered so a map can name it; nothing is fetched while `base` is empty.

The base is empty because every GSD skill is a slash-command workflow: it takes `$ARGUMENTS`, reads and writes
GSD's own planning directories, and spawns GSD's agents. None of them is a rule that applies to every agent as
text. Using GSD in a project means installing it there (`npx get-shit-done-cc --claude`, or the `@opengsd/gsd-core`
package) rather than composing it into agents. If a self-contained skill appears, list it under `base.skills`.
