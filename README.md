# ThemeBuilder — Reference → Theme Rebuild Tool (v1.0.0)

Our reverse-engineer process as a tool, separate from Mirror100: Mirror100 copies a site; ThemeBuilder **learns** a reference and rebuilds it in fresh own code with a new theme. The reference's code is never downloaded into the build and never reused.

## The flow
```bash
themebuilder spec <reference URL | local mirror/study dir> -o spec.json
# write theme.json: the new business's verified facts + its OWN assets (see theme.example.json)
themebuilder map spec.json --theme theme.json -o map.json
themebuilder scaffold map.json --spec spec.json -o ./project
themebuilder compare spec.json ./project     # gate: exit 0 only when diff_count is 0
themebuilder serve ./project                 # preview at http://127.0.0.1:8000/
```

1. **spec** — values only. Learns design, animation, scrolling, section formation/placement and fonts into `spec.json`: colours (with the properties they paint), font families + per-selector type scale, CSS variables, spacing, radii, container widths, breakpoints, transitions, `@keyframes` values, GSAP/Lenis motion values (durations, eases, staggers, lerp, scrub, pin), libraries present, and per page the section sequence — tag, kind, heading levels, image/video/canvas/link/button/paragraph counts, paragraph word counts, declared heights. **No reference code and no reference copy text is stored** — structure and values, nothing else.
2. **map** — fits your theme to the slots. Theme sections match slots by `slot` key (`page#index`) or by `kind`. Every unfilled element is flagged as a **blank** (never invented), every asset needs a **provenance** or it is warned, and theme sections that match no slot are warned.
3. **scaffold** — generates a fresh own-code project (HTML/CSS/JS written by the tool from spec + map): spec tokens as CSS variables, keyframes recreated from their values, reveal-on-scroll, sticky header when the reference had one, theme assets copied into `assets/`. A **hash copy-guard** then proves no generated file is identical to any reference file (when the spec came from a local dir it is guarded automatically; `--forbid <dir>` sets it explicitly) and fails the build if one is.
4. **compare** — the probe gate: re-extracts the built project and diffs section sequence + counts + tokens (font, bg/ink/accent, container, breakpoint, keyframes) against the spec. Prints the diff list; done means the list is empty. Static probe only — a real delivery still needs the visual scroll-stop probe (desktop + 390px) from the `reference_exact_rebuild` skill.

Works 3 ways, same family as Mirror100:
1. **Standalone, no key** — pure Python stdlib, zero dependencies
2. **Inside any agent** — Muse, Claude Code, ChatGPT/Codex, OpenCode: `themebuilder init-agent --target .`, or the MCP server `python -m themebuilder.mcp_server`
3. **With any API key** — `map --provider openai|anthropic|custom --api-key ... --base-url ... --model ...` adds an AI pass that suggests copy for blank slots (it is told to leave a slot empty rather than invent facts). Keys can come from env: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `MIRROR100_API_KEY`.

## Install
```bash
pip install -e .
# or from the repo once pushed:
pip install git+https://github.com/m-arjun-same/themebuilder.git
```

## theme.json
```json
{
  "name": "Business Name", "business": "What it is", "nav": ["Home", "Menu"],
  "colors": {"bg": "", "ink": "", "accent": ""},
  "font": "",
  "assets": [{"src": "photo.jpg", "label": "Front", "provenance": "owner's own photo"}],
  "sections": [{"kind": "hero", "heading": "Verified headline", "text": ["Fact one."],
                "cta": {"label": "Visit", "href": "#"}, "images": ["Front"]}]
}
```
Empty `colors`/`font` = take the reference's tokens. Only verified theme facts — a missing fact stays a blank in the map.

## Tests
```bash
python -m unittest discover -s tests -v   # values-only spec, blanks, copy-guard, compare gate + tamper
```

Ponytail: stdlib only, smallest complete implementation.
