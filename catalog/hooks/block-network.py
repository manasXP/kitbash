#!/usr/bin/env python3
"""PreToolUse hook. Blocks shell commands that reach the network.

Claude Code passes the tool call as JSON on stdin. Exit 2 blocks the call and
feeds stderr back to the model as the reason.
"""
import json
import re
import sys

NETWORK = re.compile(r"(^|[^A-Za-z])(curl|wget|nc|ssh|scp|pip install|npm install)([^A-Za-z]|$)")

try:
    call = json.load(sys.stdin)
except Exception:  # noqa: BLE001
    sys.exit(0)
if call.get("tool_name") != "Bash":
    sys.exit(0)
command = (call.get("tool_input") or {}).get("command", "")
if NETWORK.search(command):
    print("Blocked by block-network hook: this agent runs without network access.", file=sys.stderr)
    sys.exit(2)
