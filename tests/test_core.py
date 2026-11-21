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
