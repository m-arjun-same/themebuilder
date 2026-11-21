import argparse, json, sys
from pathlib import Path
from .core import make_spec, make_map, scaffold, compare, VERSION
from .providers import get_provider
# ASCII-only agent files + explicit encoding="utf-8" on every write (Mirror100 v1.1 lesson).
AGENT_FILES = {
 "AGENTS.md": "# themebuilder - for Muse / Codex / ChatGPT / OpenCode agents\nFlow: `themebuilder spec <reference URL or mirror dir> -o spec.json`, then write theme.json (facts + own assets with provenance), `themebuilder map spec.json --theme theme.json -o map.json`, `themebuilder scaffold map.json --spec spec.json -o <project>`, `themebuilder compare spec.json <project>`. Spec is values only - never copy reference code or copy text into a build. Never call it done until compare diff_count is 0 AND a visual scroll-stop probe (desktop + 390px) passes.\n",
 "CLAUDE.md": "# themebuilder - for Claude Code\nSame flow as AGENTS.md. Use --provider anthropic --api-key $ANTHROPIC_API_KEY for an AI-assisted map pass, or no key for standalone.\n",
 ".github/muse-instructions.md": "Use themebuilder CLI for reference-to-theme rebuilds: spec, map, scaffold, compare. See README.md.\n",
 "CHATGPT.md": "# themebuilder - for ChatGPT\nInstall repo, then run the themebuilder CLI, or use the MCP server: `python -m themebuilder.mcp_server`. Extra key: --provider custom --base-url <url> --api-key <key> --model <model>.\n",
}
def _load(p): return json.loads(Path(p).read_text(encoding="utf-8"))
def main(argv=None):
    ap = argparse.ArgumentParser(prog="themebuilder", description="Reference -> spec (values only) -> theme map -> own-code scaffold -> compare gate")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("spec"); s.add_argument("source", help="reference URL or local mirror/study dir"); s.add_argument("-o", "--out", required=True); s.add_argument("--max-pages", type=int, default=20)
    m = sub.add_parser("map"); m.add_argument("spec"); m.add_argument("--theme", required=True); m.add_argument("-o", "--out", required=True)
    m.add_argument("--provider", default="none"); m.add_argument("--api-key"); m.add_argument("--base-url"); m.add_argument("--model")
    sc = sub.add_parser("scaffold"); sc.add_argument("map"); sc.add_argument("--spec", required=True); sc.add_argument("-o", "--out", required=True); sc.add_argument("--forbid", help="reference dir to hash-guard against (default: spec source when it is a local dir)")
    c = sub.add_parser("compare"); c.add_argument("spec"); c.add_argument("built"); c.add_argument("--map")
    sv = sub.add_parser("serve"); sv.add_argument("out"); sv.add_argument("--port", type=int, default=8000); sv.add_argument("--bind", default="127.0.0.1")
    ia = sub.add_parser("init-agent"); ia.add_argument("--target", default=".")
    a = ap.parse_args(argv)
    if a.cmd == "spec":
        spec = make_spec(a.source, a.max_pages)
        Path(a.out).write_text(json.dumps(spec, indent=2), encoding="utf-8")
        slots = sum(len(p["slots"]) for p in spec["pages"])
        print(f"spec: {len(spec['pages'])} pages, {slots} slots, {len(spec['tokens']['colors'])} colours, {len(spec['tokens']['fonts'])} fonts, libraries: {', '.join(spec['motion']['libraries']) or 'none'} -> {a.out}")
    elif a.cmd == "map":
        spec = _load(a.spec); theme = _load(a.theme)
        mp = make_map(spec, theme, str(Path(a.theme).parent))
        Path(a.out).write_text(json.dumps(mp, indent=2), encoding="utf-8")
        print(f"map: {len(mp['blanks'])} blanks, {len(mp['warnings'])} warnings -> {a.out}")
        for b in mp["blanks"]: print("BLANK:", b)
        for w in mp["warnings"]: print("WARN:", w)
        prov = get_provider(a.provider, a.api_key, a.base_url, a.model)
        if prov:
            (Path(a.out).parent / "MAP_AI.md").write_text(prov.analyse(f"Suggest factual theme copy for these blank slots (leave a slot empty rather than inventing facts):\n{json.dumps(mp['blanks'])}"), encoding="utf-8")
    elif a.cmd == "scaffold":
        spec = _load(a.spec); mp = _load(a.map)
        forbid = a.forbid or (spec["source"] if spec.get("source_type") == "dir" else None)
        man = scaffold(mp, spec, a.out, forbid_dir=forbid)
        print(f"scaffold: {len(man['files'])} files, copy-guard {man['copy_guard']}, {len(man['blanks'])} blanks -> {a.out}")
    elif a.cmd == "compare":
        spec = _load(a.spec); mp = _load(a.map) if a.map else None
        res = compare(spec, a.built, mp)
        print(json.dumps(res, indent=2))
        if res["diff_count"]: sys.exit(1)
    elif a.cmd == "serve":
        import functools, http.server
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=a.out)
        print(f"Serving {a.out} at http://{a.bind}:{a.port}/  (Ctrl+C to stop)")
        http.server.ThreadingHTTPServer((a.bind, a.port), handler).serve_forever()
    elif a.cmd == "init-agent":
        for name, content in AGENT_FILES.items():
            p = Path(a.target) / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(content, encoding="utf-8"); print("wrote", p)
if __name__ == "__main__": main()
