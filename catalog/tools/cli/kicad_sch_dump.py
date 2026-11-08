#!/usr/bin/env python3
"""Summarize a KiCAD schematic for a human or a judge: components, ERC result, and net connectivity.

    kicad_sch_dump.py FILE.kicad_sch

Runs kicad-cli ERC and netlist export into a temp directory, then prints:
    COMPONENTS  ref  value  lib_id
    ERC         severity type | description   (or "clean")
    NETS        name -> [ref.pin, ...]
Used by run_evals.py as the `inspect` command for .kicad_sch fixtures and by the schematic-engineer
skill as its verification step. Needs only the system Python.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

KICAD_CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"


def parse_sexpr(text):
    """Minimal s-expression reader: returns nested lists of str."""
    tokens = re.findall(r'"(?:[^"\\]|\\.)*"|\(|\)|[^\s()]+', text)
    stack = [[]]
    for tok in tokens:
        if tok == "(":
            stack.append([])
        elif tok == ")":
            node = stack.pop()
            stack[-1].append(node)
        else:
            stack[-1].append(tok[1:-1] if tok.startswith('"') else tok)
    return stack[0]


def find_all(node, head):
    """Yield every sub-list whose first element is `head`."""
    if isinstance(node, list):
        if node and node[0] == head:
            yield node
        for child in node:
            yield from find_all(child, head)


def field(node, key, default=""):
    for child in node:
        if isinstance(child, list) and child and child[0] == key:
            return child[1] if len(child) > 1 else default
    return default


def main(path):
    if not os.path.exists(path):
        print(f"{path}: file does not exist")
        return 1
    tmp = tempfile.mkdtemp(prefix="sch-dump-")
    erc_path, net_path = os.path.join(tmp, "erc.json"), os.path.join(tmp, "netlist.net")

    # components straight from the schematic file
    doc = parse_sexpr(open(path).read())
    print("COMPONENTS")
    comps = []
    for sym in find_all(doc, "symbol"):
        lib = field(sym, "lib_id")
        if not lib:
            continue
        props = {p[1]: p[2] for p in sym if isinstance(p, list) and p and p[0] == "property" and len(p) > 2}
        comps.append((props.get("Reference", "?"), props.get("Value", ""), lib))
    for ref, val, lib in sorted(comps):
        print(f"  {ref:8s} {val:16s} {lib}")
    if not comps:
        print("  (none)")

    # ERC
    print("ERC")
    r = subprocess.run([KICAD_CLI, "sch", "erc", "--format", "json", "--severity-all", "--output", erc_path, path],
                       capture_output=True, text=True)
    if os.path.exists(erc_path):
        d = json.load(open(erc_path))
        viol = [v for s in d.get("sheets", []) for v in s.get("violations", [])]
        for v in viol:
            who = ", ".join(i.get("description", "")[:40] for i in v.get("items", []))
            print(f"  {v['severity']:7s} {v['type']:28s} | {v['description'][:80]} | {who}")
        if not viol:
            print("  clean")
    else:
        print("  erc failed:", (r.stdout + r.stderr).strip()[-200:])

    # nets from the exported netlist
    print("NETS")
    r = subprocess.run([KICAD_CLI, "sch", "export", "netlist", "--output", net_path, path], capture_output=True, text=True)
    if os.path.exists(net_path):
        nl = parse_sexpr(open(net_path).read())
        nets = []
        for net in find_all(nl, "net"):
            name = field(net, "name")
            nodes = [f"{field(n, 'ref')}.{field(n, 'pin')}" for n in net if isinstance(n, list) and n and n[0] == "node"]
            if name:
                nets.append((name, sorted(nodes)))
        for name, nodes in sorted(nets):
            print(f"  {name:20s} -> {', '.join(nodes)}")
        if not nets:
            print("  (no nets)")
    else:
        print("  netlist export failed:", (r.stdout + r.stderr).strip()[-200:])
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1]))
