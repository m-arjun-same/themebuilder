"""Python <3.12 compatibility guard (regression test for the 3.10 bug).

Python 3.12 (PEP 701) relaxed f-string rules; code written on 3.12 can
silently use syntax that is a SyntaxError on 3.10/3.11, so the CLI dies
at import there. This test scans every package source with the tokenizer
and fails on the two hazards:
  1. a backslash inside an f-string expression part (incl. nested literals)
  2. a nested f-string reusing an enclosing f-string's quote character
Runs on 3.12's tokenizer (which exposes FSTRING_* tokens); the package
itself must stay importable on 3.10.
"""
import io, sys, tokenize, unittest
from pathlib import Path

PKG = Path(__file__).parent.parent / "src" / "themebuilder"

def _quote_of(start_text):
    i = start_text.lower().find("f") + 1
    rest = start_text[i:]
    for q in ('"""', "'''", '"', "'"):
        if rest.startswith(q): return q
    return '"'

def hazards(path):
    src = path.read_bytes()
    found, stack = [], []
    try: tokens = list(tokenize.tokenize(io.BytesIO(src).readline))
    except Exception as e: return [f"tokenize failed: {e}"]
    for tok in tokens:
        if tok.type == tokenize.FSTRING_START:
            q = _quote_of(tok.string)
            if any(q == frame for frame in stack):
                found.append(f"{path.name}:{tok.start[0]} nested f-string reuses quote {q!r}")
            stack.append(q)
        elif tok.type == tokenize.FSTRING_END:
            if stack: stack.pop()
        elif tok.type == tokenize.STRING and stack and "\\" in tok.string:
            found.append(f"{path.name}:{tok.start[0]} backslash inside f-string expression: {tok.string[:40]!r}")
    return found

class PyCompatTest(unittest.TestCase):
    @unittest.skipIf(sys.version_info < (3, 12), "tokenizer FSTRING tokens need 3.12 to scan with")
    def test_no_pre312_fstring_hazards(self):
        all_found = []
        for f in sorted(PKG.glob("*.py")): all_found += hazards(f)
        self.assertEqual(all_found, [])

if __name__ == "__main__":
    unittest.main()
