#!/usr/bin/env python3
"""Talk to the Pen.dev MCP server over stdio without a model in the loop.

    pen_dump.py dump FILE.pen          # print variables and the node tree (names, types, fills, refs)
    pen_dump.py exec FILE.pen SNIPPET  # run an execute snippet against the file; SNIPPET may be a path to a .js file
    pen_dump.py tools                  # list the server's tools

The server command comes from tools/pencil.yaml next to this script. Used by run_evals.py as the
`inspect` command for .pen fixtures, so the judge sees the document state rather than a binary diff.
"""
import json
import os
import subprocess
import sys
import time

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))

DUMP_JS = r"""
const v = GetVariables().variables || {};
Print("VARIABLES");
for (const [k, d] of Object.entries(v)) Print(" ", k, "=", JSON.stringify(d.value));
Print("NODES  (depth name [type] reusable? fill | ref | size)");
Get((n, c) => {
  const fill = n.fill === undefined ? "" : (typeof n.fill === "string" ? n.fill : JSON.stringify(n.fill));
  const size = (n.width !== undefined || n.height !== undefined) ? ` ${n.width ?? "-"}x${n.height ?? "-"}` : "";
  const lay = ["gap", "padding", "cornerRadius", "strokeWidth"].filter(k => n[k] !== undefined).map(k => k + "=" + JSON.stringify(n[k])).join(" ");
  const stroke = n.stroke === undefined ? "" : "stroke=" + (typeof n.stroke === "string" ? n.stroke : JSON.stringify(n.stroke));
  const font = n.type === "text" ? ["fontFamily", "fontSize"].filter(k => n[k] !== undefined).map(k => k + "=" + JSON.stringify(n[k])).join(" ") : "";
  Print(" ".repeat(c.depth * 2) + (n.name || "(unnamed)"), "[" + n.type + "]", n.reusable ? "COMPONENT" : "", fill, stroke, n.ref ? "ref=" + n.ref : "", size, lay, font,
        n.type === "text" ? JSON.stringify((n.content || "").slice(0, 40)) : "");
  if (c.problems) Print(" ".repeat(c.depth * 2) + "  !! " + c.problems);
});
"""


class Pen:
    def __init__(self):
        cfg = yaml.safe_load(open(os.path.join(HERE, "pencil.yaml")))["server"]
        self.p = subprocess.Popen([cfg["command"], *(cfg.get("args") or [])],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        self.n = 0
        self.call("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                 "clientInfo": {"name": "pen_dump", "version": "0.1"}})
        self.notify("notifications/initialized", {})
        # The server forwards a tool call before the app has assigned it a client id if the call
        # arrives immediately after initialize; the app then drops the request. Listing tools and
        # pausing briefly lets the handshake with the app finish first.
        self.call("tools/list", {})
        time.sleep(1.0)

    def _send(self, msg):
        self.p.stdin.write(json.dumps(msg) + "\n")
        self.p.stdin.flush()

    def notify(self, method, params):
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def call(self, method, params, timeout=120):
        self.n += 1
        self._send({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params})
        while True:
            line = self.p.stdout.readline()
            if not line:
                raise RuntimeError("server closed the connection")
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == self.n:
                if "error" in msg:
                    raise RuntimeError(json.dumps(msg["error"]))
                return msg["result"]

    def tool(self, name, args):
        res = self.call("tools/call", {"name": name, "arguments": args}, timeout=600)
        text = "\n".join(c.get("text", "") for c in res.get("content", []) if c.get("type") == "text")
        if res.get("isError"):
            raise RuntimeError(text)
        return text

    def execute(self, path, snippet, description="pen_dump"):
        return self.tool("execute", {"filePath": os.path.abspath(path), "input": snippet, "description": description})

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(timeout=5)
        except Exception:  # noqa: BLE001
            self.p.kill()


def main(argv):
    if not argv or argv[0] not in ("dump", "exec", "tools"):
        sys.exit(__doc__)
    pen = Pen()
    try:
        if argv[0] == "tools":
            res = pen.call("tools/list", {})
            for t in res.get("tools", []):
                print(t["name"], "-", (t.get("description") or "")[:90].replace("\n", " "))
        elif argv[0] == "dump":
            print(pen.execute(argv[1], DUMP_JS, "Dump document for eval judge"))
        else:
            snippet = argv[2]
            if os.path.exists(snippet):
                snippet = open(snippet).read()
            print(pen.execute(argv[1], snippet, "Build eval fixture"))
    finally:
        pen.close()


if __name__ == "__main__":
    main(sys.argv[1:])
