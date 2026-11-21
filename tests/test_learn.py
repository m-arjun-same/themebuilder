"""Self-learning / evolution tests: knowledge accumulates from specs,
builds and compare diffs; evolve turns it into guidance; roles() uses it
as a prior only where the current spec is silent."""
import json, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from themebuilder.core import (load_knowledge, save_knowledge, learn_from_spec,
                               learn_from_build, learn_from_compare, evolve_report, roles)
from themebuilder.cli import main as cli_main

def spec(kinds=("hero", "gallery", "footer"), accent=True):
    colors = [{"value": "#ffffff", "count": 3, "properties": ["background"]},
              {"value": "#111111", "count": 2, "properties": ["color"]}]
    if accent: colors.append({"value": "#c8451b", "count": 1, "properties": ["border-color"]})
    return {"pages": [{"name": "index.html", "slots": [
                {"kind": k, "tag": "section", "id": "", "headings": [1], "images": 2, "videos": 0,
                 "canvas": 0, "links": 0, "buttons": 0, "paragraphs": 2, "paragraph_words": [], "list_items": 0, "forms": 0, "svgs": 0}
                for k in kinds]}],
            "tokens": {"colors": colors, "fonts": [{"family": "Archivo", "count": 4}],
                       "breakpoints": ["(max-width: 768px)"], "keyframes": [{"name": "rise", "steps": []}],
                       "containers": ["1200px"], "spacing": ["96px 24px"], "typography": []},
            "motion": {"libraries": ["gsap"], "eases": ["power3.out"], "durations": ["1.2"]}}

MAP = {"theme": {"name": "X"}, "pages": [{"name": "index.html", "slots": [
        {"kind": "gallery", "blanks": ["images 0/2"]}, {"kind": "hero", "blanks": []}]}]}

class LearnTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); self.kbfile = str(self.tmp / "kb.json")

    def test_knowledge_accumulates_and_evolves(self):
        kb = load_knowledge(self.kbfile)
        kb = learn_from_build(spec(), MAP, kb, verdict="accepted")
        kb = learn_from_build(spec(), MAP, kb)
        save_knowledge(kb, self.kbfile)
        kb2 = load_knowledge(self.kbfile)  # persisted
        self.assertEqual(kb2["builds"], 2); self.assertEqual(kb2["accepted"], 1)
        self.assertEqual(kb2["sequences"]["hero>gallery"], 2)
        self.assertEqual(kb2["blank_kinds"]["gallery"], 2)
        rep = evolve_report(kb2)
        self.assertEqual(rep["level"], "apprentice")
        self.assertTrue(any("hero>gallery" in g for g in rep["guidance"]))
        self.assertTrue(any("gallery" in g and "missing" in g for g in rep["guidance"]))

    def test_compare_diffs_become_lessons(self):
        kb = learn_from_compare({"diffs": [{"metric": "images"}, {"metric": "images"}, {"metric": "font"}]}, load_knowledge(self.kbfile))
        lessons = evolve_report(kb)["lessons"]
        self.assertTrue(any("'images' differed 2x" in l for l in lessons))

    def test_learned_prior_fills_only_silent_spec(self):
        kb = load_knowledge(self.kbfile)
        for _ in range(3): kb = learn_from_spec(spec(), kb)
        kb["colors"]["#ff0055"] = 9  # a frequent learned accent from past builds
        r = roles(spec(accent=False), kb=kb)
        self.assertEqual(r["accent"], "#ff0055"); self.assertTrue(r["learned_priors"])
        r2 = roles(spec(accent=True), kb=kb)  # spec knows its own accent: prior must NOT override
        self.assertEqual(r2["accent"], "#c8451b")

    def test_cli_auto_learn_on_spec(self):
        ref = self.tmp / "ref"; ref.mkdir()
        (ref / "index.html").write_text('<section id="hero"><h1>x</h1><p>y</p></section>', encoding="utf-8")
        out = str(self.tmp / "spec.json")
        cli_main(["spec", str(ref), "-o", out, "--knowledge", self.kbfile])
        cli_main(["spec", str(ref), "-o", out, "--knowledge", self.kbfile])
        kb = load_knowledge(self.kbfile)
        self.assertEqual(kb["specs_seen"], 2)
        self.assertEqual(kb["kinds"]["hero"]["slots"], 2)

if __name__ == "__main__":
    unittest.main()
