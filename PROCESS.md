# ThemeBuilder — The Total Process

**What it is:** one tool that builds a new website for a business (the THEME) that
follows the exact UI of another website (the REFERENCE). Python 3.9+, no
dependencies (standard library only). Current version: **1.2.0**.

---

## The two sides — always kept separate

```
REFERENCE side                          THEME side
(the site whose UI we copy)             (the business the new site is FOR)

reference URL or mirror folder          ANY ONE of:
        │                               • its own website
        ▼                               • its Google Maps link
   [1] spec                             • its business / shop name alone
        │                               • its Instagram
        ▼                                       │
   spec.json                                    ▼
 (design values only,                   [2] collect
  never its code or text)                       │
        │                                       ▼
        │                               themes/<business>/
        │                               theme.json + collected.json
        │                               (real facts + own photos,
        │                                provenance on every photo)
        └──────────────┬────────────────────────┘
                       ▼
                  [3] map        → map.json (slots filled / blanks flagged)
                       ▼
                  [4] scaffold   → the new site, built in our OWN code
                       ▼
                  [5] compare    → diff list must be EMPTY
                       ▼
                  [6] visual probe (desktop + 390px) → deliver
```

Every `spec`, `scaffold` and `compare` also teaches the tool (see Self-learning).

---

## Install

The GitHub repo is **private**, so a plain `pip install git+https://...` fails
without a GitHub login. Use one of these:

**Route A — clone, then install (recommended on your own machine)**
```
git clone https://github.com/m-arjun-same/themebuilder.git
cd themebuilder
pip install .
```

**Route B — pip with your GitHub login (token)**
```
pip install git+https://<YOUR_GITHUB_TOKEN>@github.com/m-arjun-same/themebuilder.git@v1.2.0
```

**Route C — no install, run from the cloned folder**
```
cd themebuilder
set PYTHONPATH=src        (Windows)   /   export PYTHONPATH=src   (Mac/Linux)
python -m themebuilder.cli --help
```

**Check the install worked:**
```
themebuilder --help
pip show themebuilder        → Version must say 1.2.0
```
If `themebuilder` is "not recognized" on Windows but pip said success, the
Scripts folder is not on PATH — use Route C, or run `py -m pip install .` and
restart the terminal.

**Upgrading:** pip silently keeps the old version if the version looks the
same. Always force it:
```
pip install --force-reinstall git+https://github.com/m-arjun-same/themebuilder.git@v1.2.0
```
Symptom of an old version: `themebuilder collect ...` answers
`invalid choice: 'collect'` — that means v1.0/v1.1 is installed. Upgrade.

For AI agents (Muse / Claude Code / ChatGPT / OpenCode): inside any
project folder run `themebuilder init-agent` — it drops AGENTS.md / CLAUDE.md /
CHATGPT.md / Copilot instructions that teach the agent this exact process.
MCP server: `python -m themebuilder.mcp_server`.

---

## Step 1 — spec (REFERENCE side)

```
themebuilder spec <reference URL or local mirror folder> -o spec.json
```

Reads the reference and writes **spec.json**: colours, fonts, CSS variables,
spacing, breakpoints, transitions, keyframe values, GSAP/Lenis durations,
eases, scrub/pin settings, libraries — plus each page's section sequence
(section kinds, element counts, word counts only).

**Rule:** values only. The reference's code and copy text are never stored
and never reused. The new site is built in our own code from these values.

## Step 2 — collect (THEME side)

Give **any one** input (or combine them). Output is a theme folder:

```
themebuilder collect --site https://theme-business.example          -o themes/theme-business
themebuilder collect --maps "https://maps.app.goo.gl/xxxx"          -o themes/theme-business
themebuilder collect --business "Theme Business, City"              -o themes/theme-business
themebuilder collect --instagram themehandle                        -o themes/theme-business
themebuilder collect --instagram themehandle --instagram-dir ./ig-photos -o themes/theme-business
```
Without `-o`, the folder defaults to `themes/<business-name>`.

What each input does:

| Input | What it collects |
|---|---|
| `--site` | Crawls the business's own website: name, phone, email, address, hours, price range (from its structured data + pages), its social links, and **its own photos** (duplicates removed, tiny icons skipped) |
| `--maps` | From the Google Maps link: business name, location coordinates, rating, review count, and the listing's photos. It then searches the name to find the website + Instagram too |
| `--business` | Just the name: a free web search finds the business's own website and Instagram. Directory sites (Yelp, JustDial…) are recorded as socials, never mistaken for the website |
| `--instagram` | The handle (also auto-discovered from the website's own links). Takes what the public profile page exposes: bio, followers, profile photo |

**Instagram truth:** Instagram login-walls its media on the public page, so
photo posts cannot be pulled from the handle alone. `collect` says so in the
gaps list instead of pretending. Photos collected through a connected
Instagram account go in with `--instagram-dir <folder>` and are recorded with
Instagram provenance.

**Output of collect:**
- `theme.json` — ready to feed into `map`: name, business description, nav,
  and the asset pool (every photo with a `provenance`: exactly where it came from).
- `collected.json` — the full evidence: all facts found, per-page headings and
  text, socials, Maps data, and the **gaps list**.
- `assets/` — the downloaded photos.

**Rule:** missing facts are named in the gaps list — never invented. Sections
in theme.json are left empty on purpose; `map` flags what is still missing.

## Step 3 — map

```
themebuilder map spec.json --theme themes/theme-business/theme.json -o map.json
```

Fits the theme's facts and photos into the reference spec's slots (matched by
slot key/kind). Output **map.json** lists: filled slots, **blanks** (content
nobody supplied — must be provided or consciously dropped), and **warnings**
(e.g. a photo with no provenance — not allowed in a build).

Optional: an API key can assist the mapping pass —
`--provider openai|anthropic|custom --api-key <key> [--base-url <url>] [--model <name>]`.
Without a key the tool is fully standalone.

## Step 4 — scaffold

```
themebuilder scaffold map.json --spec spec.json -o <new-project-folder>
```

Writes the new site — fresh HTML/CSS/JS in **our own code**, built from the
spec values + mapped theme content, theme photos copied in. A hash guard
checks every built file against the reference folder: if any file is a copy
of reference code, scaffold fails. That is by design.

## Step 5 — compare (the gate)

```
themebuilder compare spec.json <new-project-folder>
```

Diffs the built site's structure and design tokens against the spec.
**The build is not done until the diff count is 0.**

## Step 6 — visual probe (human/agent gate)

`compare` is a static probe. Before delivery, the built site must still pass
the visual check: screenshots at identical scroll stops, desktop **and**
390px phone width, side by side against the reference. Only a picture match
counts as "exact".

Preview any build locally:
```
themebuilder serve <new-project-folder> --port 8000
```

---

## Self-learning (evolution)

- Knowledge file: `~/.themebuilder/knowledge.json` — counts and lessons only,
  never code. Updated automatically by `spec`, `scaffold`, `compare`
  (`--no-learn` opts out of a run).
- `themebuilder learn spec.json --map map.json --verdict accepted|rejected` —
  record your verdict on a build; rejections teach what to avoid.
- `themebuilder evolve` — the report: its level (apprentice → designer →
  senior → studio lead, by builds completed), top section flows, per-section
  content expectations, and pre-flight lessons from past diffs and blanks.
- When a new spec is silent on something (e.g. no accent colour), scaffold
  may use a learned prior — always recorded as `learned_priors` in the build
  manifest. Spec values always win over learned ones.

---

## Troubleshooting — "installed locally, not working properly"

| Symptom | Cause | Fix |
|---|---|---|
| `Repository not found` / 403 / asks for password on pip install | Repo is private | Use Install Route A (clone while logged in) or Route B (token) |
| `invalid choice: 'collect'` (or collect missing from `--help`) | Old version (v1.0/v1.1) still installed | `pip show themebuilder`, then upgrade with `--force-reinstall` (above) |
| `'themebuilder' is not recognized` (Windows) | Scripts folder not on PATH, or installed for a different Python | Reinstall with `py -m pip install .` from the clone; restart terminal; or use Route C |
| `ModuleNotFoundError: themebuilder` | Not installed in this Python/env | `pip show themebuilder` in the same terminal you run it; reinstall there |
| collect prints many GAP lines | Working correctly — those facts/photos were not found at the source | Read `collected.json` gaps; supply the missing fact in theme.json by hand, or give another input (e.g. add `--instagram-dir`) |
| collect found 0 photos from Instagram | Instagram login wall (expected) | Collect the photos via the connected Instagram account into a folder, re-run with `--instagram-dir` |
| collect found no website from `--business` | Search found no clear own-website | Give `--site` or `--maps` directly |
| Maps collect missing address/hours | The Maps page payload did not expose them | Add `--site` as a second input — the website usually carries them |
| scaffold fails the copy guard | A built file is byte-identical to a reference file | Rebuild that file in own code — never copy reference files in |

Still stuck? Copy the **exact error text** and the **exact command** you ran —
that is enough to pinpoint it.
