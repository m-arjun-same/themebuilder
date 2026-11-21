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

VERSION = "1.2.1"
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
def roles(spec, theme_colors=None, theme_font="", kb=None):
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
    r["learned_priors"] = []
    if kb:  # evolution: fill only what THIS spec does not know, from past builds
        if not t["fonts"] and kb.get("fonts"):
            r["font"] = max(kb["fonts"], key=kb["fonts"].get); r["learned_priors"].append(f"font={r['font']} (most learned)")
        if r["accent"] == r["ink"] and kb.get("colors"):
            for c in sorted(kb["colors"], key=kb["colors"].get, reverse=True):
                if c not in (r["bg"], r["ink"]): r["accent"] = c; r["learned_priors"].append(f"accent={c} (most learned)"); break
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

def scaffold(map_data, spec, out_dir, theme_dir=".", forbid_dir=None, kb=None):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    (out / "assets").mkdir(exist_ok=True)
    r = roles(spec, map_data.get("colors"), map_data.get("font", ""), kb=kb)
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
                "provenance": [i for p in map_data["pages"] for s in p["slots"] for i in s["images"]],
                "learned_priors": r["learned_priors"], "knowledge_builds": (kb or {}).get("builds", 0)}
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

# ---------------------------------------------------------------- self-learning / evolution
"""Every spec studied and every build compared teaches the tool.
Knowledge is one JSON file of COUNTS and lessons - never reference code,
never copy text (same values-only rule as spec). scaffold/compare/spec
update it automatically; `evolve` turns it into design guidance, and
roles() consults it as a prior only where the current spec is silent.
That is how the tool becomes more designer with every build."""
def knowledge_path(path=None):
    return Path(path or os.environ.get("THEMEBUILDER_KNOWLEDGE") or (Path.home() / ".themebuilder" / "knowledge.json"))
def _kb_new():
    return {"tool": "themebuilder-knowledge", "version": 1, "builds": 0, "specs_seen": 0,
            "accepted": 0, "rejected": 0, "kinds": {}, "sequences": {}, "colors": {}, "fonts": {},
            "breakpoints": {}, "keyframes": {}, "libraries": {}, "eases": {}, "durations": {},
            "diff_metrics": {}, "blank_kinds": {}}
def load_knowledge(path=None):
    p = knowledge_path(path)
    if p.exists():
        try:
            kb = json.loads(p.read_text(encoding="utf-8"))
            return {**_kb_new(), **kb}
        except Exception: pass
    return _kb_new()
def save_knowledge(kb, path=None):
    p = knowledge_path(path); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(kb, indent=2), encoding="utf-8"); return str(p)
def _bump(counter, key, n=1):
    if key: counter[key] = counter.get(key, 0) + n
def learn_from_spec(spec, kb):
    kb["specs_seen"] += 1
    for page in spec.get("pages", []):
        kinds = [s["kind"] for s in page["slots"]]
        for a, b in zip(kinds, kinds[1:]): _bump(kb["sequences"], f"{a}>{b}")
        for s in page["slots"]:
            k = kb["kinds"].setdefault(s["kind"], {"slots": 0, "images": 0, "paragraphs": 0, "headings": 0})
            k["slots"] += 1; k["images"] += s.get("images", 0); k["paragraphs"] += s.get("paragraphs", 0); k["headings"] += len(s.get("headings", []))
    t = spec.get("tokens", {})
    for c in t.get("colors", []): _bump(kb["colors"], c["value"])
    for f in t.get("fonts", []): _bump(kb["fonts"], f["family"])
    for b in t.get("breakpoints", []): _bump(kb["breakpoints"], b)
    for k in t.get("keyframes", []): _bump(kb["keyframes"], k["name"])
    m = spec.get("motion", {})
    for lib in m.get("libraries", []): _bump(kb["libraries"], lib)
    for e in m.get("eases", []): _bump(kb["eases"], e)
    for d in m.get("durations", []): _bump(kb["durations"], str(d))
    return kb
def learn_from_compare(result, kb):
    for d in result.get("diffs", []): _bump(kb["diff_metrics"], str(d.get("metric")))
    return kb
def learn_from_build(spec, map_data, kb, verdict=None):
    kb["builds"] += 1
    if verdict in ("accepted", "rejected"): kb[verdict] += 1
    for page in (map_data or {}).get("pages", []):
        for s in page["slots"]:
            for b in s.get("blanks", []): _bump(kb["blank_kinds"], s["kind"])
    return learn_from_spec(spec, kb)
def _lessons(kb):
    out = []
    for metric, n in sorted(kb["diff_metrics"].items(), key=lambda kv: -kv[1])[:5]:
        out.append(f"Pre-flight: '{metric}' differed {n}x in past compares - check it before running compare.")
    for kind, n in sorted(kb["blank_kinds"].items(), key=lambda kv: -kv[1])[:5]:
        out.append(f"Theme content most often missing for '{kind}' slots ({n}x) - collect it before mapping.")
    return out
def evolve_report(kb):
    builds = kb["builds"]
    level = "apprentice" if builds < 3 else "designer" if builds < 8 else "senior designer" if builds < 20 else "studio lead"
    top_seq = sorted(kb["sequences"].items(), key=lambda kv: -kv[1])[:5]
    guidance = []
    if top_seq: guidance.append("Most learned section flow: " + " | ".join(f"{a} ({n}x)" for a, n in top_seq[:3]))
    for kind, k in sorted(kb["kinds"].items(), key=lambda kv: -kv[1]["slots"])[:4]:
        if k["slots"]: guidance.append(f"'{kind}' slots usually carry ~{k['images'] / k['slots']:.1f} images and ~{k['paragraphs'] / k['slots']:.1f} paragraphs - pre-collect that much theme content.")
    if kb["fonts"]: guidance.append(f"Most learned font: {max(kb['fonts'], key=kb['fonts'].get)} - use as prior only when a spec has no font of its own.")
    if kb["eases"]: guidance.append(f"Most learned motion ease: {max(kb['eases'], key=kb['eases'].get)}; durations seen: {', '.join(sorted(kb['durations'])[:6])}.")
    guidance += _lessons(kb)
    return {"builds": builds, "specs_seen": kb["specs_seen"], "accepted": kb["accepted"], "rejected": kb["rejected"],
            "level": level, "top_sequences": dict(top_seq),
            "palette": dict(sorted(kb["colors"].items(), key=lambda kv: -kv[1])[:10]),
            "fonts": kb["fonts"], "libraries": kb["libraries"], "lessons": _lessons(kb), "guidance": guidance}

# ---------------------------------------------------------------- collect
# The THEME side, kept separate from the reference side: `spec` learns the
# REFERENCE site's design; `collect` gathers the THEME business's own data -
# facts + photos from its own website and its Instagram - into a theme.json
# that `map` can consume. Provenance is recorded for every single asset.
class _Collect(HTMLParser):
    CAPTURE = ("title", "h1", "h2", "h3", "p", "a")
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""; self.metas = {}; self.headings = []; self.paragraphs = []
        self.images = []; self.links = []; self.jsonld = []; self.nav = []
        self._stack = []; self._script = False; self._buf = []; self._in_nav = 0
    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "meta":
            k = d.get("property") or d.get("name")
            if k and d.get("content"): self.metas[k.lower()] = d["content"]
        if tag == "img":
            u = d.get("src") or d.get("data-src") or ""
            if d.get("srcset"): u = d["srcset"].split(",")[0].strip().split()[0] or u
            if u: self.images.append((u, d.get("alt") or ""))
        if tag == "nav": self._in_nav += 1
        if tag == "script" and (d.get("type") or "") == "application/ld+json": self._script = True; self._buf = []
        if tag in self.CAPTURE: self._stack.append((tag, [], d.get("href") or ""))
    def handle_data(self, data):
        if self._script: self._buf.append(data); return
        for _, buf, _ in self._stack: buf.append(data)
    def handle_endtag(self, tag):
        if tag == "script" and self._script: self.jsonld.append("".join(self._buf)); self._script = False
        if tag == "nav": self._in_nav = max(0, self._in_nav - 1)
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                t, buf, href = self._stack.pop(i); text = " ".join("".join(buf).split())
                if not text: break
                if t == "title": self.title = text
                elif t in ("h1", "h2", "h3"): self.headings.append((int(t[1]), text))
                elif t == "p":
                    if len(text) > 1: self.paragraphs.append(text)
                elif t == "a":
                    self.links.append((href, text))
                    if self._in_nav: self.nav.append(text)
                break

def _jsonld_facts(scripts):
    facts = {}
    def walk(node):
        if isinstance(node, list):
            for x in node: walk(x)
        elif isinstance(node, dict):
            t = str(node.get("@type", ""))
            if any(k in t for k in ("Business", "Organization", "Store", "Restaurant", "Bakery", "Salon", "Shop")) or "name" in node:
                for key in ("name", "description", "telephone", "email", "priceRange", "url"):
                    if node.get(key) and key not in facts: facts[key] = str(node[key])
                addr = node.get("address")
                if isinstance(addr, dict) and "address" not in facts:
                    facts["address"] = ", ".join(str(addr[k]) for k in ("streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry") if addr.get(k))
                elif isinstance(addr, str) and "address" not in facts: facts["address"] = addr
                oh = node.get("openingHours")
                if oh and "hours" not in facts: facts["hours"] = oh if isinstance(oh, list) else [oh]
                spec = node.get("openingHoursSpecification")
                if spec and "hours" not in facts:
                    spec = spec if isinstance(spec, list) else [spec]
                    facts["hours"] = [f"{s.get('dayOfWeek', '')} {s.get('opens', '')}-{s.get('closes', '')}".strip() for s in spec if isinstance(s, dict)]
                if node.get("sameAs") and "sameAs" not in facts: facts["sameAs"] = node["sameAs"]
            for v in node.values(): walk(v)
    for s in scripts:
        try: walk(json.loads(s))
        except Exception: pass
    return facts

def _og(html, prop):
    for pat in (r'<meta[^>]+property=["\']' + re.escape(prop) + r'["\'][^>]+content=["\']([^"\']*)["\']',
                r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+property=["\']' + re.escape(prop) + r'["\']'):
        m = re.search(pat, html, re.I)
        if m: return m.group(1)
    return ""

def collect_theme(site=None, instagram=None, instagram_dir=None, out_dir="theme-out",
                  name=None, maps=None, business=None, max_pages=10, min_bytes=6000, max_images=60):
    if not site and not instagram and not instagram_dir and not maps and not business:
        raise SystemExit("collect needs at least one theme input: --site, --maps, --business, --instagram or --instagram-dir")
    out = Path(out_dir); assets_dir = out / "assets"; assets_dir.mkdir(parents=True, exist_ok=True)
    facts, pages, gaps, socials = {}, [], [], {}
    seen_hashes, assets, img_candidates = set(), [], []
    def add_asset(data, ext, label, provenance):
        h = hashlib.sha256(data).hexdigest()
        if h in seen_hashes or len(assets) >= max_images: return
        seen_hashes.add(h)
        fname = f"photo-{len(assets) + 1:03d}.{ext}"
        (assets_dir / fname).write_bytes(data)
        assets.append({"src": f"assets/{fname}", "label": label or f"Photo {len(assets) + 1}", "provenance": provenance})
    def add_image_url(u, page_url, alt="", provenance=None):
        if len(assets) >= max_images: return
        au = urllib.parse.urljoin(page_url, u)
        if au in [c[0] for c in img_candidates]: return
        img_candidates.append((au, page_url, alt, provenance))
    # --- resolve a bare business name or a Google Maps link into site + socials ---
    if business and not site:
        found_site, found_ig, extra = _find_business(business)
        if found_site: site = found_site
        if found_ig and not instagram: instagram = found_ig
        socials.update(extra)
        if not site and not instagram: gaps.append(f"business search for '{business}' found no website or Instagram - give --site, --maps or --instagram directly")
    if maps:
        s, _, d, final = _fetch(maps)
        mhtml = d.decode("utf-8", "ignore") if d else ""
        mfacts, mphotos = _maps_facts(final or maps, mhtml)
        for k, v in mfacts.items(): facts.setdefault(k, v)
        if mfacts.get("name") and not site and not business:
            found_site, found_ig, extra = _find_business(mfacts["name"])
            if found_site: site = found_site
            if found_ig and not instagram: instagram = found_ig
            socials.update(extra)
        for pu in mphotos: add_image_url(pu, final or maps, facts.get("name", ""), "Google Maps listing of the theme business")
    # --- theme website ---
    if site:
        base = urllib.parse.urlparse(site); origin = f"{base.scheme}://{base.netloc}"
        seen, queue = {site}, deque([site])
        while queue and len(pages) < max_pages:
            u = queue.popleft(); status, ctype, data, final = _fetch(u)
            if status >= 400 or not data: continue
            html = data.decode("utf-8", "ignore"); p = _Collect()
            try: p.feed(html)
            except Exception: pass
            pages.append({"url": final, "title": p.title, "headings": [t for _, t in p.headings][:20], "paragraphs": p.paragraphs[:12]})
            for k, v in _jsonld_facts(p.jsonld).items(): facts.setdefault(k, v)
            if not facts.get("description") and p.metas.get("description"): facts["description"] = p.metas["description"]
            if not facts.get("name") and (p.metas.get("og:site_name") or p.title): facts["name"] = p.metas.get("og:site_name") or p.title
            if p.metas.get("og:image"): add_image_url(p.metas["og:image"], final, "Main photo")
            for iu, alt in p.images: add_image_url(iu, final, alt)
            for href, text in p.links:
                if href.startswith("mailto:"): facts.setdefault("email", href[7:].split("?")[0])
                if href.startswith("tel:"): facts.setdefault("telephone", href[4:])
                for plat in ("instagram.com", "facebook.com", "twitter.com", "x.com", "youtube.com", "linkedin.com"):
                    if plat in href: socials.setdefault(plat.split(".")[0], urllib.parse.urljoin(final, href))
                au = urllib.parse.urldefrag(urllib.parse.urljoin(final, href))[0]
                if au.startswith(origin) and au not in seen and Path(urllib.parse.urlparse(au).path).suffix in ("", ".html", ".htm"):
                    seen.add(au); queue.append(au)
            if not facts.get("nav") and p.nav: facts["nav"] = list(dict.fromkeys(p.nav))[:8]
            blob = html
            for em in re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", blob):
                if "email" not in facts and not em.endswith((".png", ".jpg")): facts["email"] = em
    for au, page_url, alt, prov in img_candidates:
        if len(assets) >= max_images: break
        s, ct, d, _ = _fetch(au)
        ext = Path(urllib.parse.urlparse(au).path).suffix.lower().lstrip(".")
        if s >= 400 or not d or len(d) < min_bytes: continue
        if not (ct.startswith("image/") or ext in ("jpg", "jpeg", "png", "webp", "avif")): continue
        add_asset(d, ext if ext in ("jpg", "jpeg", "png", "webp", "avif") else "jpg", alt, prov or f"theme website {page_url}")
    # --- Instagram handle discovered from the site's own links, if not given ---
    if not instagram and socials.get("instagram"):
        instagram = socials["instagram"].rstrip("/").split("/")[-1]
    ig_facts = {}
    if instagram:
        handle = instagram.strip().lstrip("@")
        if "instagram.com/" in handle: handle = handle.split("instagram.com/")[-1].strip("/").split("/")[0]
        ig_facts["handle"] = handle
        s, _, d, _ = _fetch(f"https://www.instagram.com/{handle}/")
        html = d.decode("utf-8", "ignore") if d else ""
        desc, img = _og(html, "og:description"), _og(html, "og:image")
        if desc:
            ig_facts["description"] = desc
            m = re.search(r"([\d.,]+\s*[KM]?)\s+Followers", desc)
            if m: ig_facts["followers"] = m.group(1)
            m = re.search(r"on Instagram:\s*[\"“](.+?)[\"”]\s*$", desc)
            if m: ig_facts["bio"] = m.group(1)
        if img:
            s2, _, d2, _ = _fetch(img)
            if s2 < 400 and d2: add_asset(d2, "jpg", f"Instagram @{handle} profile photo", f"Instagram @{handle} public profile page")
        if not desc and not img:
            gaps.append(f"Instagram @{handle}: public page exposed no data (login wall). Collect its photos via the connected Instagram account into a folder and re-run with --instagram-dir, or add assets manually.")
    # --- Instagram / media folder provided by the user or the agent ---
    if instagram_dir:
        src_dir = Path(instagram_dir)
        if not src_dir.exists(): gaps.append(f"instagram-dir not found: {instagram_dir}")
        else:
            prov = f"Instagram @{ig_facts.get('handle')} (provided folder)" if ig_facts.get("handle") else "provided media folder"
            for f in sorted(src_dir.rglob("*")):
                if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                    add_asset(f.read_bytes(), f.suffix.lower().lstrip("."), f.stem.replace("_", " "), prov)
    for field, label in (("name", "business name"), ("telephone", "phone"), ("email", "email"), ("address", "address")):
        if not facts.get(field) and not (field == "name" and name): gaps.append(f"no {label} found - supply it in theme.json by hand")
    if not assets: gaps.append("no photos collected - add the business's own photos to theme assets by hand")
    theme = {"name": name or facts.get("name", ""), "business": facts.get("description", ""),
             "tagline": "", "nav": facts.get("nav", []), "colors": {}, "font": "",
             "assets": assets, "sections": []}
    collected = {"tool": "themebuilder", "version": VERSION, "theme_site": site, "maps": facts.pop("maps", None), "business_query": business, "instagram": ig_facts,
                 "socials": socials, "facts": {k: v for k, v in facts.items() if k != "nav"},
                 "pages": pages, "assets": assets, "gaps": gaps,
                 "note": "Facts + photos collected from the THEME business's own website/Instagram only. Sections are left empty on purpose: map flags what is still missing instead of inventing it."}
    (out / "theme.json").write_text(json.dumps(theme, indent=2), encoding="utf-8")
    (out / "collected.json").write_text(json.dumps(collected, indent=2), encoding="utf-8")
    return collected

def _slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-") or "theme"

def _ddg_results(html):
    urls = []
    for href in re.findall(r'href="([^"]+)"', html or ""):
        if "uddg=" in href:
            href = urllib.parse.unquote(href.split("uddg=")[-1].split("&")[0])
        if href.startswith("http") and "duckduckgo.com" not in href: urls.append(href)
    return list(dict.fromkeys(urls))

def _find_business(query):
    """Best-effort free search (DuckDuckGo HTML) for a bare business name:
    returns (website, instagram_handle, socials). Directories/socials are
    never mistaken for the business's own website."""
    socials, website, ig = {}, None, None
    skip = ("facebook.com", "instagram.com", "yelp.", "tripadvisor.", "youtube.com", "twitter.com", "x.com", "linkedin.com", "google.", "zomato.", "swiggy.", "justdial.", "indiamart.", "pinterest.")
    for q in (query, query + " instagram"):
        s, _, d, _ = _fetch("https://html.duckduckgo.com/html/?q=" + urllib.parse.quote_plus(q))
        for u in _ddg_results(d.decode("utf-8", "ignore") if d else ""):
            host = urllib.parse.urlparse(u).netloc.lower()
            if "instagram.com" in host:
                handle = u.rstrip("/").split("/")[-1]
                if handle and handle not in ("p", "reel", "explore"): ig = ig or handle; socials.setdefault("instagram", u)
            elif any(k in host for k in skip): socials.setdefault(host.split(".")[-2], u)
            elif website is None: website = u
    return website, ig, socials

def _maps_facts(final_url, html):
    """Parse what a Google Maps place link exposes without a browser:
    name + coordinates from the resolved URL, rating/reviews and photos
    from the page payload. Anything not found is left for the gaps list."""
    facts, photos = {}, []
    u = urllib.parse.unquote(final_url or "")
    m = re.search(r"/place/([^/]+)/", u)
    if m: facts["name"] = m.group(1).replace("+", " ")
    elif "query=" in u: facts["name"] = urllib.parse.parse_qs(urllib.parse.urlparse(u).query).get("query", [""])[0]
    m = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", u)
    if m: facts["maps"] = {"url": final_url, "lat": m.group(1), "lng": m.group(2)}
    if html:
        m = re.search(r"([0-5]\.\d)\s*\(([\d,]+)\)", html)
        if m: facts.setdefault("maps", {}) .update({"rating": m.group(1), "reviews": m.group(2)})
        for pu in re.findall(r"https://lh[345]\.googleusercontent\.com/[^\s\"'\\]+", html):
            pu = re.sub(r"=w\d+-h\d+[^\"']*$", "=w1200-h900-k-no", pu)
            if pu not in photos: photos.append(pu)
        m = re.search(r"(\+?\d[\d\s().-]{8,}\d)", html)
        if m: facts.setdefault("telephone", m.group(1).strip())
    return facts, photos[:30]
