"""ThemeBuilder core - our reverse-engineer process as a tool. Stdlib only.

Flow: REFERENCE -> spec (VALUES ONLY) -> map (theme facts/assets into the
spec's slots) -> scaffold (fresh own code) -> compare (diff gate).

The spec never stores reference code or reference copy text: only design
values (colours, fonts, spacing, breakpoints, durations, eases, keyframe
values), section formation (order, tags, element counts, heading levels,
word counts) and library names. The deliverable is built from the spec,
never from reference files, and scaffold runs a hash guard proving no
reference file was copied into the build.
"""
import os, re, json, hashlib, shutil, urllib.request, urllib.parse, urllib.error
from html.parser import HTMLParser
from pathlib import Path
from collections import deque, Counter

VERSION = "1.0.0"
UA = {"User-Agent": "Mozilla/5.0 themebuilder/1.0"}
SECTION_TAGS = ("header", "nav", "footer", "section", "article", "aside")
VOID = {"img", "br", "link", "meta", "input", "hr", "source", "wbr", "col"}
KIND_WORDS = [("hero", "hero"), ("banner", "hero"), ("gallery", "gallery"), ("portfolio", "gallery"),
              ("work", "gallery"), ("about", "about"), ("service", "services"), ("pricing", "pricing"),
              ("price", "pricing"), ("testimonial", "testimonials"), ("review", "testimonials"),
              ("contact", "contact"), ("faq", "faq"), ("team", "team"), ("footer", "footer"),
              ("header", "header"), ("nav", "nav"), ("menu", "nav"), ("blog", "blog"),
              ("shop", "shop"), ("product", "shop"), ("book", "booking"), ("cta", "cta")]
LIB_WORDS = ["gsap", "ScrollTrigger", "lenis", "three", "swiper", "aos", "jquery", "tailwind", "IntersectionObserver", "requestAnimationFrame"]

def _fetch(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
            return r.status, r.headers.get_content_type() or "", r.read(), r.geturl()
    except urllib.error.HTTPError as e: return e.code, "", b"", url
    except Exception: return 0, "", b"", url

# ---------------------------------------------------------------- structure
class _Structure(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.slots = []; self.stack = []; self.open_slots = []
        self.script_srcs = []; self.css_hrefs = []; self.style_blocks = []; self.inline_scripts = []
        self._style = False; self._script = False; self._buf = []
    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "script":
            if d.get("src"): self.script_srcs.append(d["src"])
            else: self._script = True; self._buf = []
        if tag == "style": self._style = True; self._buf = []
        if tag == "link" and "stylesheet" in (d.get("rel") or "") and d.get("href"): self.css_hrefs.append(d["href"])
        slot = None
        if tag in SECTION_TAGS:
            slot = {"tag": tag, "id": d.get("id") or "", "kind": _kind(tag, d.get("id") or "", d.get("class") or ""),
                    "depth": len(self.open_slots), "headings": [], "images": 0, "videos": 0, "canvas": 0,
                    "links": 0, "buttons": 0, "paragraphs": 0, "paragraph_words": [], "list_items": 0, "forms": 0, "svgs": 0}
            self.slots.append(slot); self.open_slots.append(slot)
        # counts go to the INNERMOST open slot only, so a nav inside a
        # header does not inflate the header's counts (keeps spec and
        # scaffold - which emits slots flat - directly comparable)
        s = self.open_slots[-1] if self.open_slots else None
        if s is not None and slot is None:
            if tag == "img": s["images"] += 1
            elif tag == "video": s["videos"] += 1
            elif tag == "canvas": s["canvas"] += 1
            elif tag == "a": s["links"] += 1
            elif tag == "button" or (tag == "input" and d.get("type") in ("submit", "button")): s["buttons"] += 1
            elif tag == "li": s["list_items"] += 1
            elif tag == "form": s["forms"] += 1
            elif tag == "svg": s["svgs"] += 1
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            if s is not None: s["headings"].append(int(tag[1]))
            self.stack.append((tag, "heading"))
        elif tag == "p":
            if s is not None: s["paragraphs"] += 1
            self.stack.append((tag, "p"))
        if tag not in VOID: self.stack.append((tag, slot))
    def handle_data(self, data):
        if self._style: self._buf.append(data); return
        if self._script: self._buf.append(data); return
        words = len(data.split())
        if not words: return
        # word COUNTS only - reference copy text is never stored in a spec
        for tag, marker in reversed(self.stack):
            if marker == "p":
                if self.open_slots: self.open_slots[-1]["paragraph_words"].append(words)
                break
            if marker == "heading": break
    def handle_endtag(self, tag):
        if tag == "style" and self._style: self.style_blocks.append("".join(self._buf)); self._style = False
        if tag == "script" and self._script: self.inline_scripts.append("".join(self._buf)); self._script = False
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                popped = self.stack[i:]; del self.stack[i:]
                for _, slot in popped:
                    if slot is not None and slot in self.open_slots: self.open_slots.remove(slot)
                break

def _kind(tag, idv, cls):
    hay = (idv + " " + cls).lower()
    for word, kind in KIND_WORDS:
        if word in hay: return kind
    return {"header": "header", "footer": "footer", "nav": "nav"}.get(tag, "block")

# ---------------------------------------------------------------- CSS values
RULE_RE = re.compile(r"([^{}]+)\{([^{}]*)\}")
COLOR_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\)")
def _css_values(css_texts):
    css = "\n".join(css_texts)
    colors = Counter(); color_props = {}
    fonts = Counter(); typography = []; transitions = []; animations = []
    spacing = Counter(); radii = Counter(); containers = Counter(); breakpoints = Counter()
    css_vars = {}; sticky = []; scroll_behavior = []
    for sel, body in RULE_RE.findall(css):
        sel = sel.strip()
        if sel.startswith("@"): continue
        decls = {}
        for part in body.split(";"):
            if ":" in part:
                k, v = part.split(":", 1); decls[k.strip().lower()] = v.strip()
        for k, v in decls.items():
            for c in COLOR_RE.findall(v):
                colors[c.lower()] += 1; color_props.setdefault(c.lower(), set()).add(k)
            if k == "font-family":
                fam = v.split(",")[0].strip().strip("'\""); fonts[fam] += 1
            if k in ("padding", "margin", "gap"): spacing[v] += 1
            if k == "border-radius": radii[v] += 1
            if k == "max-width": containers[v] += 1
            if k == "transition": transitions.append(v)
            if k == "animation": animations.append(v)
            if k == "position" and v in ("sticky", "fixed"): sticky.append(sel)
            if k == "scroll-behavior": scroll_behavior.append(v)
        if any(k in decls for k in ("font-family", "font-size", "font-weight", "line-height")) and len(typography) < 80:
            typography.append({"selector": sel[:80], **{k: decls[k] for k in ("font-family", "font-size", "font-weight", "line-height") if k in decls}})
        for name, val in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", body): css_vars[name] = val.strip()
    for mq in re.findall(r"@media\s*([^{}]+)\{", css): breakpoints[mq.strip()] += 1
    keyframes = []
    for name, inner in re.findall(r"@keyframes\s+([\w-]+)\s*\{((?:[^{}]|\{[^{}]*\})*)\}", css):
        steps = []
        for at, body in RULE_RE.findall(inner):
            props = {}
            for part in body.split(";"):
                if ":" in part:
                    k, v = part.split(":", 1)
                    if k.strip() in ("opacity", "transform"): props[k.strip()] = v.strip()
            if props: steps.append({"at": at.strip(), "props": props})
        keyframes.append({"name": name, "steps": steps})
    return {"colors": [{"value": c, "count": n, "properties": sorted(color_props.get(c, ()))} for c, n in colors.most_common(40)],
            "fonts": [{"family": f, "count": n} for f, n in fonts.most_common(20)],
            "css_vars": css_vars, "typography": typography,
            "breakpoints": [b for b, _ in breakpoints.most_common()],
            "spacing": [s for s, _ in spacing.most_common(24)], "radii": [r for r, _ in radii.most_common(12)],
            "containers": [c for c, _ in containers.most_common(12)],
            "transitions": sorted(set(transitions))[:24], "animations": sorted(set(animations))[:24],
            "keyframes": keyframes, "scroll_behavior": sorted(set(scroll_behavior)), "sticky_selectors": sticky[:12]}

def _js_values(js_texts, script_srcs):
    js = "\n".join(js_texts)
    libs = sorted({w for w in LIB_WORDS if w.lower() in js.lower() or any(w.lower() in s.lower() for s in script_srcs)})
    return {"libraries": libs,
            "durations": sorted(set(re.findall(r"duration\s*[:=]\s*([\d.]+)", js))),
            "eases": sorted(set(re.findall(r"ease\s*[:=]\s*[\"']([^\"']+)[\"']", js))),
            "staggers": sorted(set(re.findall(r"stagger\s*[:=]\s*([\d.]+)", js))),
            "lerp": sorted(set(re.findall(r"lerp\s*[:=]\s*([\d.]+)", js))),
            "scrub": bool(re.search(r"scrub\s*[:=]", js)), "pin": bool(re.search(r"pin\s*[:=]\s*true", js)),
            "scroll_listener": "addEventListener" in js and "scroll" in js}

def _spec_from_sources(source, source_type, pages):
    """pages: [{name, html, css:[], js:[], script_srcs:[]}]"""
    all_css, all_js, srcs, out_pages, assets = [], [], [], [], Counter()
    for p in pages:
        st = _Structure()
        try: st.feed(p["html"])
        except Exception: pass
        for s in st.slots:  # declared heights from CSS rules aimed at #id
            if s["id"]:
                for css in p["css"]:
                    m = re.search(r"#" + re.escape(s["id"]) + r"\s*\{([^{}]*)\}", css)
                    if m:
                        for part in m.group(1).split(";"):
                            if ":" in part:
                                k, v = part.split(":", 1)
                                if k.strip() in ("height", "min-height", "padding"): s.setdefault("declared", {})[k.strip()] = v.strip()
                        break
        out_pages.append({"name": p["name"], "slots": st.slots})
        all_css += p["css"]; all_js += p["js"] + st.inline_scripts; srcs += p["script_srcs"]
        for a in re.findall(r"(?:src|href)=[\"']([^\"']+)[\"']", p["html"]):
            ext = Path(urllib.parse.urlparse(a).path).suffix.lower()
            if ext: assets[ext] += 1
    return {"tool": "themebuilder", "version": VERSION, "source": source, "source_type": source_type,
            "values_only": True,
            "note": "Spec holds design values + section formation only. No reference code and no reference copy text is stored. Rendered heights, pin runways and screenshot truth need the compare step + a visual probe.",
            "pages": out_pages, "tokens": _css_values(all_css), "motion": _js_values(all_js, srcs),
            "asset_counts": dict(assets)}

def spec_from_dir(path):
    root = Path(path); pages = []
    for f in sorted(root.rglob("*.html")):
        pages.append({"name": str(f.relative_to(root)), "html": f.read_text(encoding="utf-8", errors="ignore"),
                      "css": [], "js": [], "script_srcs": []})
    css = [f.read_text(encoding="utf-8", errors="ignore") for f in sorted(root.rglob("*.css"))]
    js = [f.read_text(encoding="utf-8", errors="ignore") for f in sorted(root.rglob("*.js"))]
    srcs = [f.name for f in sorted(root.rglob("*.js"))]
    for p in pages: p["css"] = css; p["js"] = js; p["script_srcs"] = srcs
    return _spec_from_sources(str(root), "dir", pages)

def spec_from_url(url, max_pages=20):
    base = urllib.parse.urlparse(url); origin = f"{base.scheme}://{base.netloc}"
    seen, queue, pages = {url}, deque([url]), []
    while queue and len(pages) < max_pages:
        u = queue.popleft(); status, ctype, data, final = _fetch(u)
        if status >= 400 or not data or "html" not in ctype and not final.endswith((".html", "/")): continue
        html = data.decode("utf-8", "ignore"); st = _Structure()
        try: st.feed(html)
        except Exception: pass
        css, js = list(st.style_blocks), []
        for href in st.css_hrefs[:8]:
            s2, _, d2, _ = _fetch(urllib.parse.urljoin(final, href))
            if s2 < 400 and d2: css.append(d2[:512000].decode("utf-8", "ignore"))
        for src in st.script_srcs[:5]:
            s2, _, d2, _ = _fetch(urllib.parse.urljoin(final, src))
            if s2 < 400 and d2: js.append(d2[:512000].decode("utf-8", "ignore"))
        name = urllib.parse.urlparse(final).path.strip("/")
        pages.append({"name": (name.replace("/", "-") + ".html") if name else "index.html",
                      "html": html, "css": css, "js": js, "script_srcs": st.script_srcs})
        for a in re.findall(r"<a[^>]+href=[\"']([^\"']+)[\"']", html):
            au = urllib.parse.urldefrag(urllib.parse.urljoin(final, a))[0]
            if au.startswith(origin) and au not in seen: seen.add(au); queue.append(au)
    return _spec_from_sources(url, "url", pages)

def make_spec(source, max_pages=20):
    return spec_from_url(source, max_pages) if source.startswith(("http://", "https://")) else spec_from_dir(source)

# ---------------------------------------------------------------- map
def make_map(spec, theme, theme_dir="."):
    theme_dir = Path(theme_dir); pages_out, blanks, warnings = [], [], []
    assets = theme.get("assets", [])
    for a in assets:
        if not a.get("provenance"): warnings.append(f"asset '{a.get('label') or a.get('src')}' has no provenance")
        src = a.get("src", "")
        if src and not src.startswith(("http://", "https://")) and not (theme_dir / src).exists():
            warnings.append(f"asset file not found: {src}")
    entries = list(theme.get("sections", []))
    used = [False] * len(entries)
    def find_entry(slot, key):
        for i, e in enumerate(entries):
            if used[i]: continue
            if e.get("slot") == key or (e.get("kind") and e["kind"] == slot["kind"] and not e.get("slot")):
                used[i] = True; return e
        return {}
    for page in spec["pages"]:
        slots_out = []
        for idx, slot in enumerate(page["slots"]):
            key = f"{page['name']}#{idx}"
            e = find_entry(slot, key)
            texts = e.get("text", []); texts = [texts] if isinstance(texts, str) else list(texts)
            imgs = []
            for ref in e.get("images", []):
                a = assets[ref] if isinstance(ref, int) and ref < len(assets) else next((x for x in assets if x.get("label") == ref), None)
                if a: imgs.append({"src": a.get("src", ""), "label": a.get("label", ""), "provenance": a.get("provenance", "")})
                else: warnings.append(f"{key}: image ref {ref!r} not in theme assets")
            slot_blanks = []
            if slot["headings"] and not e.get("heading"): slot_blanks.append("heading")
            if slot["images"] > len(imgs): slot_blanks.append(f"images {len(imgs)}/{slot['images']}")
            if slot["paragraphs"] > len(texts): slot_blanks.append(f"paragraphs {len(texts)}/{slot['paragraphs']}")
            blanks += [f"{key}: {b}" for b in slot_blanks]
            slots_out.append({"key": key, "tag": slot["tag"], "kind": slot["kind"], "id": slot.get("id", ""),
                              "headings": slot["headings"], "heading": e.get("heading", ""),
                              "paragraphs": texts, "paragraph_count": slot["paragraphs"],
                              "images": imgs, "image_count": slot["images"], "videos": slot["videos"], "canvas": slot["canvas"],
                              "links": slot["links"], "link_labels": e.get("links", []),
                              "buttons": slot["buttons"], "cta": e.get("cta", {}), "blanks": slot_blanks})
        pages_out.append({"name": page["name"], "slots": slots_out})
    for i, e in enumerate(entries):
        if not used[i]: warnings.append(f"theme section {i} (kind={e.get('kind')}, slot={e.get('slot')}) matched no reference slot")
    return {"tool": "themebuilder", "version": VERSION, "theme": {k: theme.get(k) for k in ("name", "business", "tagline") if k in theme},
            "colors": theme.get("colors", {}), "font": theme.get("font", ""), "nav": theme.get("nav", []),
            "pages": pages_out, "blanks": blanks, "warnings": warnings}

# ---------------------------------------------------------------- scaffold
def roles(spec, theme_colors=None, theme_font=""):
    t = spec["tokens"]; colors = t["colors"]
    def by_prop(props, fallback=None):
        if isinstance(props, str): props = (props,)
        for c in colors:
            if any(p in c["properties"] for p in props): return c["value"]
        return fallback
    r = {"bg": by_prop(("background-color", "background"), colors[0]["value"] if colors else "#ffffff"),
         "ink": by_prop("color", colors[1]["value"] if len(colors) > 1 else "#111111"),
         "accent": None, "font": theme_font or (t["fonts"][0]["family"] if t["fonts"] else "sans-serif"),
         "container": t["containers"][0] if t["containers"] else "1200px",
         "breakpoint": None, "h1": "3rem", "section_pad": t["spacing"][0] if t["spacing"] else "96px 24px"}
    for c in colors:
        if c["value"] not in (r["bg"], r["ink"]): r["accent"] = c["value"]; break
    r["accent"] = r["accent"] or r["ink"]
    for b in t["breakpoints"]:
        m = re.search(r"max-width:\s*([\d.]+px)", b)
        if m: r["breakpoint"] = m.group(1); break
    for ty in t["typography"]:
        if ty["selector"].strip() == "h1" and "font-size" in ty: r["h1"] = ty["font-size"]
    if theme_colors: r.update({k: v for k, v in theme_colors.items() if v})
    return r

def _hashes(root):
    out = {}
    for f in Path(root).rglob("*"):
        if f.is_file() and f.stat().st_size: out[hashlib.sha256(f.read_bytes()).hexdigest()] = str(f)
    return out

def check_no_copied(build_dir, forbid_dir):
    if not forbid_dir or not Path(forbid_dir).exists(): return []
    ref = _hashes(forbid_dir); copied = []
    for f in Path(build_dir).rglob("*"):
        if f.is_file() and f.stat().st_size and hashlib.sha256(f.read_bytes()).hexdigest() in ref:
            copied.append(str(f))
    return copied

def scaffold(map_data, spec, out_dir, theme_dir=".", forbid_dir=None):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    (out / "assets").mkdir(exist_ok=True)
    r = roles(spec, map_data.get("colors"), map_data.get("font", ""))
    copied_assets = {}
    def asset_file(img):
        src = img["src"]
        if src in copied_assets: return copied_assets[src]
        name = "assets/" + re.sub(r"[^\w.\-]", "_", Path(urllib.parse.urlparse(src).path).name or "img")
        dest = out / name
        if src.startswith(("http://", "https://")):
            s, _, d, _ = _fetch(src)
            if s < 400 and d: dest.write_bytes(d)
        else:
            p = Path(theme_dir) / src
            if p.exists(): shutil.copyfile(p, dest)
        copied_assets[src] = name; return name
    files = []
    for page in map_data["pages"]:
        parts = ["<!doctype html>", '<html lang="en"><head><meta charset="utf-8">',
                 '<meta name="viewport" content="width=device-width, initial-scale=1">',
                 f"<title>{map_data['theme'].get('name','Site')}</title>",
                 '<link rel="stylesheet" href="css/style.css"></head><body>']
        main_open = False
        for slot in page["slots"]:
            if slot["tag"] in ("section", "article", "aside") and not main_open: parts.append("<main>"); main_open = True
            if slot["tag"] == "footer" and main_open: parts.append("</main>"); main_open = False
            tag = slot["tag"]; cls = f"tb tb-{slot['kind']}"
            inner = []
            for li, level in enumerate(slot["headings"]):
                txt = slot["heading"] if li == 0 else ""
                inner.append(f"<h{level}{'' if txt else ' data-tb-blank=\"heading\"'}>{txt}</h{level}>")
            for i in range(slot["paragraph_count"]):
                txt = slot["paragraphs"][i] if i < len(slot["paragraphs"]) else ""
                inner.append(f"<p{'' if txt else ' data-tb-blank=\"paragraph\"'}>{txt}</p>")
            for i in range(slot["image_count"]):
                if i < len(slot["images"]):
                    inner.append(f'<img src="{asset_file(slot["images"][i])}" alt="{slot["images"][i].get("label","")}">')
                else: inner.append('<img data-tb-blank="image" alt="">')
            for i in range(slot["videos"]): inner.append('<video data-tb-blank="video" controls></video>')
            for i in range(slot["canvas"]): inner.append("<canvas></canvas>")
            labels = slot["link_labels"] or (map_data.get("nav", []) if slot["kind"] in ("nav", "header") else [])
            for i in range(slot["links"]):
                lab = labels[i] if i < len(labels) else ""
                inner.append(f'<a href="#"{"" if lab else " data-tb-blank=\"link\""}>{lab}</a>')
            for i in range(slot["buttons"]):
                lab = slot["cta"].get("label", "") if i == 0 else ""
                inner.append(f"<button{'' if lab else ' data-tb-blank=\"button\"'}>{lab}</button>")
            parts.append(f'<{tag} class="{cls}">{"".join(inner)}</{tag}>')
        if main_open: parts.append("</main>")
        parts.append('<script src="js/main.js"></script></body></html>')
        name = Path(page["name"]).name
        (out / name).write_text("\n".join(parts), encoding="utf-8"); files.append(name)
    t = spec["tokens"]; dur = (t["transitions"][0] if t["transitions"] else "all .6s ease")
    kf = "\n".join(f"@keyframes {k['name']} {{{' '.join(f'{s['at']} {{{'; '.join(f'{pk}: {pv}' for pk, pv in s['props'].items())}}}' for s in k['steps'])}}}" for k in t["keyframes"])
    bp = r["breakpoint"] or "768px"
    css = f""":root{{--bg:{r['bg']};--ink:{r['ink']};--accent:{r['accent']};--font:{r['font']}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:var(--font),sans-serif}}
.tb{{padding:{r['section_pad']};max-width:{r['container']};margin:0 auto}}
h1{{font-size:{r['h1']}}}a{{color:var(--accent)}}button{{background:var(--accent);color:var(--bg);border:0;padding:12px 20px;cursor:pointer}}
.tb img,.tb video{{max-width:100%}}.tb{{opacity:0;transform:translateY(24px);transition:{dur}}}
.tb.in{{opacity:1;transform:none}}header.tb{{{'position:sticky;top:0;' if t['sticky_selectors'] else ''}background:var(--bg)}}
{kf}
@media (max-width:{bp}){{.tb{{padding:48px 16px}}h1{{font-size:2rem}}}}
"""
    (out / "css").mkdir(exist_ok=True); (out / "css" / "style.css").write_text(css, encoding="utf-8"); files.append("css/style.css")
    js = """// ThemeBuilder own-code scaffold: reveal on scroll, nothing copied.
const io=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target)}}),{threshold:.15});
document.querySelectorAll('.tb').forEach(el=>io.observe(el));
"""
    if "smooth" in t["scroll_behavior"]: js += "document.documentElement.style.scrollBehavior='smooth';\n"
    (out / "js").mkdir(exist_ok=True); (out / "js" / "main.js").write_text(js, encoding="utf-8"); files.append("js/main.js")
    copied = check_no_copied(out, forbid_dir)
    manifest = {"tool": "themebuilder", "version": VERSION, "theme": map_data["theme"], "files": files,
                "blanks": map_data["blanks"], "copy_guard": "FAILED" if copied else "passed", "copied_files": copied,
                "provenance": [i for p in map_data["pages"] for s in p["slots"] for i in s["images"]]}
    (out / "_themebuilder.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if copied: raise SystemExit(f"copy-guard FAILED - scaffold files identical to reference files: {copied}")
    return manifest

# ---------------------------------------------------------------- compare
def compare(spec, built_dir, map_data=None):
    built = spec_from_dir(built_dir)
    theme_colors = map_data.get("colors", {}) if map_data else {}
    theme_font = map_data.get("font", "") if map_data else ""
    r = roles(spec, theme_colors, theme_font)
    diffs = []
    bpages = {p["name"].split("/")[-1]: p for p in built["pages"]}
    for page in spec["pages"]:
        bp = bpages.get(page["name"].split("/")[-1])
        if not bp: diffs.append({"page": page["name"], "metric": "page", "expected": "present", "actual": "missing"}); continue
        if len(bp["slots"]) != len(page["slots"]):
            diffs.append({"page": page["name"], "metric": "slot_count", "expected": len(page["slots"]), "actual": len(bp["slots"])}); continue
        for i, (a, b) in enumerate(zip(page["slots"], bp["slots"])):
            for metric in ("tag", "kind", "headings", "images", "videos", "canvas", "links", "buttons", "paragraphs"):
                if a[metric] != b[metric]: diffs.append({"page": page["name"], "slot": i, "metric": metric, "expected": a[metric], "actual": b[metric]})
    built_css = "\n".join(f.read_text(encoding="utf-8", errors="ignore") for f in Path(built_dir).rglob("*.css"))
    for metric, needle in (("font", r["font"]), ("bg", r["bg"]), ("ink", r["ink"]), ("accent", r["accent"]), ("container", r["container"])):
        if needle and needle.lower() not in built_css.lower(): diffs.append({"metric": metric, "expected": needle, "actual": "absent from built CSS"})
    if r["breakpoint"] and r["breakpoint"] not in built_css: diffs.append({"metric": "breakpoint", "expected": r["breakpoint"], "actual": "absent from built CSS"})
    for k in spec["tokens"]["keyframes"]:
        if f"@keyframes {k['name']}" not in built_css: diffs.append({"metric": "keyframes", "expected": k["name"], "actual": "absent from built CSS"})
    return {"diffs": diffs, "diff_count": len(diffs),
            "note": "Static probe: structure + tokens at spec level. A match also needs the visual scroll-stop probe (desktop + 390px) from the reference_exact_rebuild skill before delivery."}
