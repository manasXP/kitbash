#!/usr/bin/env python3
"""Runs a hook only inside the named agents. Arguments: HOOK AGENT_TYPE [AGENT_TYPE ...]

A plugin's hooks fire for the whole session, and plugin subagents ignore `hooks` in their frontmatter, so deploy.py
--plugin puts this in front of an agent's hooks. Plugin subagents report agent_type as <plugin>:<agent>.
"""
import json
import subprocess
import sys

raw = sys.stdin.buffer.read()
if json.loads(raw).get("agent_type") in sys.argv[2:]:
    sys.exit(subprocess.run([sys.argv[1]], input=raw).returncode)
