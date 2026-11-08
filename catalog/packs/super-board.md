---
name: super-board
description: Autonomous GitHub Project pipeline for Claude Code; drains a board through Build, QA, and Review lanes and merges when green.
source:
  url: https://github.com/EricTechPro/super-board
  version: v3.1.2
  commit: 22b974ab4baedb4ecd9899527c6ca4ec2aa8fecc
  license: MIT
  pinned: 2026-11-01
layout:
  skills: skills/{name}/SKILL.md
base:
  traits: []
  skills: []
---
Registered so a map can name it; nothing is fetched while `base` is empty.

super-board ships eight skills: five the user types (`super-board`, `super-collect`, `ui-refine-loop`, `visual`,
`git-sync`) and three lanes the board runs (`super-build`, `super-qa`, `super-review`). All of them are workflows
over a GitHub Project board, its scripts (`super-board-merge-gate.sh`), guard hooks, and a wave workflow file, so
none composes into an agent prompt as a standing rule. The base is empty for the same reason as gstack and gsd.
Using super-board in a project means installing it there (`get.sh`, or the plugin marketplace) and running
`/super-board onboard`. If a self-contained skill appears, list it under `base.skills`.

Its lanes overlap Kitbash playbooks: Build → QA → Review with a merge gate is a three-step playbook with command
handoffs. Worth comparing when playbooks grow beyond linear.
