"""Minimal MCP stdio server (JSON-RPC) exposing themebuilder - Claude/ChatGPT/Muse can call it after installing the repo."""
import sys, json
from pathlib import Path
from .core import make_spec, make_map, scaffold, compare, load_knowledge, save_knowledge, learn_from_spec, evolve_report
def _load(p): return json.loads(Path(p).read_text(encoding="utf-8"))
def handle(req):
    if req.get("method") == "tools/call":
        p = req["params"]; name = p["name"]; args = p.get("arguments", {})
        if name == "spec": result = make_spec(args["source"])
        elif name == "map": result = make_map(_load(args["spec"]), _load(args["theme"]), str(Path(args["theme"]).parent))
        elif name == "scaffold":
            spec = _load(args["spec"])
            result = scaffold(_load(args["map"]), spec, args["out"], forbid_dir=spec["source"] if spec.get("source_type") == "dir" else None)
        elif name == "compare": result = compare(_load(args["spec"]), args["built"])
        elif name == "learn":
            kb = learn_from_spec(_load(args["spec"]), load_knowledge(args.get("knowledge"))); save_knowledge(kb, args.get("knowledge")); result = evolve_report(kb)
        elif name == "evolve": result = evolve_report(load_knowledge(args.get("knowledge")))
        else: result = {"error": "unknown tool"}
        return {"jsonrpc": "2.0", "id": req.get("id"), "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2)[:8000]}]}}
    if req.get("method") == "tools/list":
        tools = [{"name": n, "description": d, "inputSchema": {"type": "object", "properties": {}, "required": []}} for n, d in
                 (("spec", "Extract a values-only design spec from a reference URL or dir"),
                  ("map", "Map theme facts/assets into spec slots"),
                  ("scaffold", "Generate a fresh own-code project from spec+map"),
                  ("compare", "Diff a built project against the spec"),
                  ("learn", "Teach the knowledge file from a spec"),
                  ("evolve", "Report what the tool has learned + design guidance"))]
        return {"jsonrpc": "2.0", "id": req.get("id"), "result": {"tools": tools}}
    return {"jsonrpc": "2.0", "id": req.get("id"), "result": {}}
def main():
    for line in sys.stdin:
        if line.strip(): print(json.dumps(handle(json.loads(line))), flush=True)
if __name__ == "__main__": main()
