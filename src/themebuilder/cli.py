import argparse, json, sys, urllib.parse
from pathlib import Path
from .core import (make_spec, make_map, scaffold, compare, VERSION,
                   load_knowledge, save_knowledge, learn_from_spec, learn_from_build,
                   learn_from_compare, evolve_report, collect_theme, _slug)
from .providers import get_provider
# ASCII-only agent files + explicit encoding="utf-8" on every write (Mirror100 v1.1 lesson).
AGENT_FILES = {
 "AGENTS.md": "# themebuilder - for Muse / Codex / ChatGPT / OpenCode agents\nRULE: whichever reference website is given, the finished build must match its UI 100% exactly - layout, sections and their order/formation, fonts, colours, spacing, transitions, animations and scrolling. Only the theme content changes. No simplification, no interpretation, no 'close enough.' A build is not done until `compare` shows 0 diffs AND the visual scroll-stop probe (desktop + 390px) matches the reference side by side. Self-learning: every spec/scaffold/compare updates its knowledge file (see `themebuilder evolve`). Flow: `themebuilder spec <reference URL or mirror dir> -o spec.json`, then `themebuilder collect` (ANY of --site/--maps/--business/--instagram) gathers the THEME business's own facts + photos into theme.json (provenance on every photo, gaps named never invented), `themebuilder map spec.json --theme theme.json -o map.json`, `themebuilder scaffold map.json --spec spec.json -o <project>`, `themebuilder compare spec.json <project>`. Spec is values only - never copy reference code or copy text into a build. Never call it done until compare diff_count is 0 AND a visual scroll-stop probe (desktop + 390px) passes.\n",
 "CLAUDE.md": "# themebuilder - for Claude Code\nSame flow as AGENTS.md. Use --provider anthropic --api-key $ANTHROPIC_API_KEY for an AI-assisted map pass, or no key for standalone.\n",
 ".github/muse-instructions.md": "Use themebuilder CLI for reference-to-theme rebuilds: spec, map, scaffold, compare. See README.md.\n",
 "CHATGPT.md": "# themebuilder - for ChatGPT\nInstall repo, then run the themebuilder CLI, or use the MCP server: `python -m themebuilder.mcp_server`. Extra key: --provider custom --base-url <url> --api-key <key> --model <model>.\n",
}
def _load(p): return json.loads(Path(p).read_text(encoding="utf-8"))
def main(argv=None):
    ap = argparse.ArgumentParser(prog="themebuilder", description="Reference -> spec (values only) -> theme map -> own-code scaffold -> compare gate")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("spec"); s.add_argument("source", help="reference URL or local mirror/study dir"); s.add_argument("-o", "--out", required=True); s.add_argument("--max-pages", type=int, default=20); s.add_argument("--knowledge"); s.add_argument("--no-learn", action="store_true")
    m = sub.add_parser("map"); m.add_argument("spec"); m.add_argument("--theme", required=True); m.add_argument("-o", "--out", required=True)
    m.add_argument("--provider", default="none"); m.add_argument("--api-key"); m.add_argument("--base-url"); m.add_argument("--model")
    sc = sub.add_parser("scaffold"); sc.add_argument("map"); sc.add_argument("--spec", required=True); sc.add_argument("-o", "--out", required=True); sc.add_argument("--forbid", help="reference dir to hash-guard against (default: spec source when it is a local dir)"); sc.add_argument("--knowledge"); sc.add_argument("--no-learn", action="store_true")
    c = sub.add_parser("compare"); c.add_argument("spec"); c.add_argument("built"); c.add_argument("--map"); c.add_argument("--knowledge"); c.add_argument("--no-learn", action="store_true")
    co = sub.add_parser("collect"); co.add_argument("--site", help="THEME business's own website (not the reference)"); co.add_argument("--maps", help="theme's Google Maps link"); co.add_argument("--business", help="theme's business/shop name only - its website + Instagram are found by search"); co.add_argument("--instagram", help="theme's Instagram handle or profile URL"); co.add_argument("--instagram-dir", help="folder of the theme's photos already collected (e.g. via a connected Instagram account)"); co.add_argument("--name", help="business name override"); co.add_argument("-o", "--out", help="theme folder (default: themes/<business name>)"); co.add_argument("--max-pages", type=int, default=10); co.add_argument("--min-bytes", type=int, default=6000); co.add_argument("--max-images", type=int, default=60)
    ln = sub.add_parser("learn"); ln.add_argument("spec"); ln.add_argument("--map"); ln.add_argument("--verdict", choices=("accepted", "rejected")); ln.add_argument("--knowledge")
    ev = sub.add_parser("evolve"); ev.add_argument("--knowledge")
    sv = sub.add_parser("serve"); sv.add_argument("out"); sv.add_argument("--port", type=int, default=8000); sv.add_argument("--bind", default="127.0.0.1")
    ia = sub.add_parser("init-agent"); ia.add_argument("--target", default=".")
    a = ap.parse_args(argv)
    if a.cmd == "collect":
        out = a.out or ("themes/" + _slug(a.name or a.business or (urllib.parse.urlparse(a.site).netloc if a.site else "") or (a.instagram or "theme").lstrip("@")))
        r = collect_theme(site=a.site, instagram=a.instagram, instagram_dir=a.instagram_dir, out_dir=out, name=a.name, maps=a.maps, business=a.business, max_pages=a.max_pages, min_bytes=a.min_bytes, max_images=a.max_images)
        a.out = out
        print(f"theme: {r['facts'].get('name', '')} | facts: {', '.join(sorted(r['facts'])) or 'none'} | photos: {len(r['assets'])} (provenance on every one) | socials: {', '.join(sorted(r['socials'])) or 'none'}")
        for g in r["gaps"]: print("GAP:", g)
        print(f"theme.json + collected.json -> {a.out}  (feed theme.json into: themebuilder map spec.json --theme {a.out}/theme.json -o map.json)")
        return
    if a.cmd == "spec":
        spec = make_spec(a.source, a.max_pages)
        Path(a.out).write_text(json.dumps(spec, indent=2), encoding="utf-8")
        slots = sum(len(p["slots"]) for p in spec["pages"])
        print(f"spec: {len(spec['pages'])} pages, {slots} slots, {len(spec['tokens']['colors'])} colours, {len(spec['tokens']['fonts'])} fonts, libraries: {', '.join(spec['motion']['libraries']) or 'none'} -> {a.out}")
        if not a.no_learn:
            kb = learn_from_spec(spec, load_knowledge(a.knowledge)); save_knowledge(kb, a.knowledge)
            print(f"learned: {kb['specs_seen']} specs studied, level: {evolve_report(kb)['level']}")
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
        kb = load_knowledge(a.knowledge)
        man = scaffold(mp, spec, a.out, forbid_dir=forbid, kb=kb)
        print(f"scaffold: {len(man['files'])} files, copy-guard {man['copy_guard']}, {len(man['blanks'])} blanks -> {a.out}")
        if man["learned_priors"]: print("learned priors used:", "; ".join(man["learned_priors"]))
        if not a.no_learn:
            kb = learn_from_build(spec, mp, kb); save_knowledge(kb, a.knowledge)
            print(f"learned: build #{kb['builds']}, level: {evolve_report(kb)['level']}")
    elif a.cmd == "compare":
        spec = _load(a.spec); mp = _load(a.map) if a.map else None
        res = compare(spec, a.built, mp)
        print(json.dumps(res, indent=2))
        if not a.no_learn:
            kb = learn_from_compare(res, load_knowledge(a.knowledge)); save_knowledge(kb, a.knowledge)
            for lesson in evolve_report(kb)["lessons"]: print("LESSON:", lesson)
        if res["diff_count"]: sys.exit(1)
    elif a.cmd == "learn":
        spec = _load(a.spec); kb = load_knowledge(a.knowledge)
        if a.map: kb = learn_from_build(spec, _load(a.map), kb, verdict=a.verdict)
        else: kb = learn_from_spec(spec, kb)
        path = save_knowledge(kb, a.knowledge)
        rep = evolve_report(kb); print(f"learned -> {path}: {rep['builds']} builds, {rep['specs_seen']} specs, level: {rep['level']}")
    elif a.cmd == "evolve":
        rep = evolve_report(load_knowledge(a.knowledge)); print(json.dumps(rep, indent=2))
        for g in rep["guidance"]: print("GUIDE:", g)
    elif a.cmd == "serve":
        import functools, http.server
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=a.out)
        print(f"Serving {a.out} at http://{a.bind}:{a.port}/  (Ctrl+C to stop)")
        http.server.ThreadingHTTPServer((a.bind, a.port), handler).serve_forever()
    elif a.cmd == "init-agent":
        for name, content in AGENT_FILES.items():
            p = Path(a.target) / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(content, encoding="utf-8"); print("wrote", p)
if __name__ == "__main__": main()
