"""ThemeBuilder tests: spec is values-only, map flags blanks, scaffold is
own code (hash copy-guard), compare gate is 0 on the scaffold and non-0
after tampering. Stdlib unittest. Run: python -m unittest discover -s tests -v
"""
import json, shutil, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from themebuilder.core import make_spec, make_map, scaffold, compare, check_no_copied

REF_HTML = """<!doctype html><html><head><link rel="stylesheet" href="style.css">
<script src="https://cdn.example.com/gsap.min.js"></script></head><body>
<header id="top"><a href="/">Logo</a><nav><a href="/a">A</a><a href="/b">B</a><a href="/c">C</a></nav></header>
<section id="hero"><h1>Ref headline</h1><p>Zqxj unique reference sentence that must never be stored.</p>
<p>Second ref paragraph here.</p><img src="ref-hero.jpg"><button>Go</button></section>
<section id="gallery"><h2>Ref gallery</h2><p>Ref gallery paragraph.</p>
<img src="g1.jpg"><img src="g2.jpg"><img src="g3.jpg"></section>
<footer><p>Ref footer line.</p><a href="/x">X</a><a href="/y">Y</a></footer>
<script src="app.js"></script></body></html>"""
REF_CSS = """/* REFERENCE-CODE-MARKER-12345 */
:root{--brand:#C8451B}
body{font-family:'Archivo',sans-serif;color:#17130E;background:#F4EDE1}
h1{font-size:64px;line-height:1.05}
.wrap{max-width:1240px}
#hero{min-height:100vh;padding:120px 24px}
.card{transition:all .6s cubic-bezier(.22,1,.36,1);border-radius:18px}
@keyframes rise{from{opacity:0;transform:translateY(24px)}to{opacity:1;transform:none}}
@media (max-width:768px){h1{font-size:40px}}
"""
REF_JS = 'gsap.to(".x",{duration:1.2,ease:"power3.out",scrollTrigger:{scrub:true,pin:true}});'
THEME = {"name": "Test Bakery", "business": "Bakery", "nav": ["Home", "Menu", "Visit"],
         "assets": [{"src": "cake.jpg", "label": "Cake", "provenance": "theme owner's own photo"}],
         "sections": [
             {"kind": "hero", "heading": "Fresh Bakes Daily", "text": ["Para one.", "Para two."],
              "cta": {"label": "Order"}, "images": ["Cake"]},
             {"kind": "gallery", "heading": "Our Cakes", "text": ["Gallery para."], "images": []}]}

class ThemeBuilderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        ref = cls.tmp / "ref"; ref.mkdir()
        (ref / "index.html").write_text(REF_HTML, encoding="utf-8")
        (ref / "style.css").write_text(REF_CSS, encoding="utf-8")
        (ref / "app.js").write_text(REF_JS, encoding="utf-8")
        cls.ref = ref
        (cls.tmp / "cake.jpg").write_bytes(b"jpg")
        cls.spec = make_spec(str(ref))
        cls.map = make_map(cls.spec, THEME, str(cls.tmp))
        cls.out = cls.tmp / "build"
        cls.man = scaffold(cls.map, cls.spec, str(cls.out), theme_dir=str(cls.tmp), forbid_dir=str(ref))

    @classmethod
    def tearDownClass(cls): shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_spec_values(self):
        t = self.spec["tokens"]
        vals = [c["value"] for c in t["colors"]]
        self.assertIn("#c8451b", vals); self.assertIn("#f4ede1", vals)
        self.assertEqual(t["fonts"][0]["family"], "Archivo")
        self.assertIn("max-width:768px".replace(" ", ""), json.dumps(t["breakpoints"]).replace(" ", ""))
        self.assertEqual(t["keyframes"][0]["name"], "rise")
        self.assertEqual(self.spec["motion"]["durations"], ["1.2"])
        self.assertEqual(self.spec["motion"]["eases"], ["power3.out"])
        self.assertTrue(self.spec["motion"]["pin"]); self.assertTrue(self.spec["motion"]["scrub"])
        self.assertIn("gsap", self.spec["motion"]["libraries"])
        kinds = [s["kind"] for s in self.spec["pages"][0]["slots"]]
        self.assertEqual(kinds, ["header", "nav", "hero", "gallery", "footer"])

    def test_spec_is_values_only(self):
        blob = json.dumps(self.spec)
        self.assertNotIn("REFERENCE-CODE-MARKER", blob)   # no reference code
        self.assertNotIn("Zqxj", blob)                    # no reference copy text
        self.assertNotIn("Ref headline", blob)

    def test_map_blanks(self):
        joined = " ".join(self.map["blanks"])
        self.assertIn("images 0/3", joined)               # gallery has no theme images
        self.assertEqual(self.map["warnings"], [])
        hero = [s for p in self.map["pages"] for s in p["slots"] if s["kind"] == "hero"][0]
        self.assertEqual(hero["heading"], "Fresh Bakes Daily"); self.assertEqual(hero["blanks"], [])

    def test_scaffold_own_code(self):
        html = (self.out / "index.html").read_text(encoding="utf-8")
        css = (self.out / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn("Fresh Bakes Daily", html)
        self.assertIn("#c8451b", css); self.assertIn("Archivo", css); self.assertIn("@keyframes rise", css)
        self.assertTrue((self.out / "assets" / "cake.jpg").exists())
        self.assertEqual(self.man["copy_guard"], "passed")
        self.assertNotIn("Zqxj", html)

    def test_copy_guard_catches_a_copied_file(self):
        dirty = self.tmp / "dirty"; shutil.copytree(self.out, dirty)
        shutil.copyfile(self.ref / "style.css", dirty / "stolen.css")
        self.assertTrue(check_no_copied(dirty, self.ref))

    def test_compare_gate(self):
        res = compare(self.spec, str(self.out), self.map)
        self.assertEqual(res["diff_count"], 0, res["diffs"])

    def test_compare_catches_tamper(self):
        bad = self.tmp / "bad"; shutil.copytree(self.out, bad)
        html = (bad / "index.html").read_text(encoding="utf-8")
        start = html.find('<section class="tb tb-gallery"')
        end = html.find("</section>", start) + len("</section>")
        (bad / "index.html").write_text(html[:start] + html[end:], encoding="utf-8")
        res = compare(self.spec, str(bad), self.map)
        self.assertGreater(res["diff_count"], 0)

if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------- collect
import functools, http.server, threading
from unittest import mock
from themebuilder import core
from themebuilder.core import collect_theme

BIG1 = b"\xff\xd8" + b"H" * 8000
BIG2 = b"\xff\xd8" + b"C" * 9000
SITE_HTML = """<!doctype html><html><head><title>Sunny Bakery</title>
<meta property="og:image" content="hero.jpg">
<script type="application/ld+json">{"@type":"Bakery","name":"Sunny Bakery","telephone":"+1 555-0100",
"email":"hello@sunny.example","priceRange":"$$","address":{"@type":"PostalAddress","streetAddress":"1 Main St","addressLocality":"Springfield","postalCode":"12345"},
"openingHours":"Mo-Sa 08:00-18:00"}</script></head><body>
<nav><a href="/">Home</a><a href="/menu.html">Menu</a></nav>
<h1>Sunny Bakery</h1><img src="hero.jpg" alt="Bakery front"><img src="icon.jpg" alt="icon">
<a href="menu.html">Menu</a><a href="https://instagram.com/sunnybakery">Instagram</a></body></html>"""
MENU_HTML = """<!doctype html><html><body><h1>Menu</h1><img src="hero.jpg"><img src="cake.jpg" alt="Cake"></body></html>"""

class CollectTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        site = cls.tmp / "site"; site.mkdir()
        (site / "index.html").write_text(SITE_HTML, encoding="utf-8")
        (site / "menu.html").write_text(MENU_HTML, encoding="utf-8")
        (site / "hero.jpg").write_bytes(BIG1); (site / "cake.jpg").write_bytes(BIG2); (site / "icon.jpg").write_bytes(b"x" * 100)
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(site)))
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}/"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_collect_site_facts_and_photos(self):
        out = self.tmp / "t1"; r = collect_theme(site=self.url, out_dir=str(out))
        self.assertEqual(r["facts"]["name"], "Sunny Bakery")
        self.assertEqual(r["facts"]["telephone"], "+1 555-0100")
        self.assertEqual(r["facts"]["email"], "hello@sunny.example")
        self.assertIn("1 Main St", r["facts"]["address"])
        self.assertTrue(r["facts"]["hours"])
        self.assertEqual(len(r["assets"]), 2)  # hero + cake; duplicate hero deduped, tiny icon filtered
        for a in r["assets"]:
            self.assertTrue(a["provenance"].startswith("theme website"))
            self.assertTrue((out / a["src"]).exists())
        self.assertEqual(r["instagram"]["handle"], "sunnybakery")  # discovered from the site's own link
        theme = json.loads((out / "theme.json").read_text())
        self.assertEqual(theme["name"], "Sunny Bakery")

    def test_collected_theme_feeds_map(self):
        out = self.tmp / "t2"; collect_theme(site=self.url, out_dir=str(out))
        theme = json.loads((out / "theme.json").read_text())
        ref = self.tmp / "ref2"; ref.mkdir(exist_ok=True)
        (ref / "index.html").write_text(REF_HTML, encoding="utf-8")
        (ref / "style.css").write_text(REF_CSS, encoding="utf-8")
        (ref / "app.js").write_text(REF_JS, encoding="utf-8")
        m = make_map(make_spec(str(ref)), theme, str(out))
        self.assertFalse([w for w in m["warnings"] if "provenance" in w])

    def test_collect_instagram_dir(self):
        ig = self.tmp / "ig"; ig.mkdir(); (ig / "post_one.jpg").write_bytes(BIG1); (ig / "post_two.jpg").write_bytes(BIG2)
        r = collect_theme(instagram="sunnybakery", instagram_dir=str(ig), out_dir=str(self.tmp / "t3"))
        self.assertEqual(len(r["assets"]), 2)
        self.assertTrue(all("Instagram @sunnybakery" in a["provenance"] for a in r["assets"]))

    def test_find_business_classification(self):
        ddg = ('<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.yelp.com%2Fbiz%2Fsunny">Y</a>'
               '<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fsunnybakery.example%2F">S</a>'
               '<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.instagram.com%2Fsunnybakery%2F">I</a>')
        with mock.patch.object(core, "_fetch", return_value=(200, "text/html", ddg.encode(), "")):
            site, ig, socials = core._find_business("Sunny Bakery")
        self.assertEqual(site, "https://sunnybakery.example/")
        self.assertEqual(ig, "sunnybakery")
        self.assertIn("yelp", socials)

    def test_collect_maps_link(self):
        orig = core._fetch
        maps_html = 'rated 4.8(2,345) <img src="https://lh3.googleusercontent.com/p/XYZ=w408-h306-k-no">'
        def fake(url, *a):
            if "goo.gl" in url or "google.com/maps" in url:
                return 200, "text/html", maps_html.encode(), "https://www.google.com/maps/place/Sunny+Bakery/@12.9,77.6,17z"
            if url.startswith("https://lh3."): return 200, "image/jpeg", BIG1, url
            if "duckduckgo" in url: return 404, "", b"", url
            return orig(url, *a)
        with mock.patch.object(core, "_fetch", side_effect=fake):
            r = collect_theme(maps="https://maps.app.goo.gl/abc", out_dir=str(self.tmp / "t4"))
        self.assertEqual(r["facts"]["name"], "Sunny Bakery")
        self.assertEqual(r["maps"]["rating"], "4.8")
        self.assertTrue(any("Google Maps" in a["provenance"] for a in r["assets"]))

    def test_collect_needs_an_input(self):
        with self.assertRaises(SystemExit): collect_theme(out_dir=str(self.tmp / "t5"))

if __name__ == "__main__": unittest.main()
