# AGENTS.md

This repo is Andreas Sander's (andi1984) GitHub profile README. GitHub renders `README.md` from `main` on https://github.com/andi1984, so every push to `main` is public right away.

## How it works

- `README.md` is mostly hand-written. Two sections are generated between markers and must not be edited by hand:
  - `<!-- ACTIVITY:START/END -->` — "Recently pushed" bullet (latest public repos across `andi1984` + `viberfasend`).
  - `<!-- WRITING:START/END -->` — latest posts from https://andi1984.dev/rss.xml, with "also on dev.to" links matched via each dev.to article's `canonical_url`.
- `scripts/build.py` (Python 3.12, stdlib only) regenerates those sections plus `assets/banner-{light,dark}.svg` and `assets/cards/<slug>-{light,dark}.svg`. Set `GITHUB_TOKEN` (`GITHUB_TOKEN=$(gh auth token) python3 scripts/build.py`). It only writes files whose content changed, so a no-op run leaves git clean.
- `profile.toml` is the config: featured project cards (`[[projects]]`), feed settings, repos excluded from the activity line. Edit this rather than the script.
- `.github/workflows/profile.yml` runs every 6h, on dispatch, and on pushes touching `scripts/**` / `profile.toml`:
  - `readme` job: runs the build, commits `chore: refresh profile` if anything changed.
  - `snake` job: Platane/snk draws the contribution snake into the `output` branch (`snake-light.svg` / `snake-dark.svg`).
  - `keepalive` job: `gh api -X PUT .../actions/workflows/profile.yml/enable` so GitHub doesn't pause the schedule after 60 quiet days. No dummy commits.

## Design

Garden theme from andi1984.dev ("hand-built, watered regularly"): cream paper / leaf green / tomato red / sun yellow, dark variants for dark mode. Fonts: Fraunces (display), Instrument Sans (text), JetBrains Mono (meta). Palettes live in `THEMES` in `scripts/build.py`. Voice: personal and specific, not corporate; borrow from https://andi1984.dev/about.

## Gotchas (learned the hard way)

- SVGs embedded via `<img>` can't load external fonts. `font_face()` inlines a woff2 subset from Google Fonts (`text=` param, browser User-Agent needed to get woff2) and falls back to system stacks if that fails.
- Animate *from* hidden (`@keyframes x { from { transform: scale(0) } }` + `animation-fill-mode: both`), never set the hidden state as the base style; otherwise anything that doesn't run animations shows an empty banner.
- GitHub's sanitizer splits `srcset` on commas. Any URL with commas inside `<source srcset>` must encode them as `%2C` (see the skillicons row).
- Use `<picture><source media="(prefers-color-scheme: dark)">` for light/dark images; it follows the GitHub theme.
- An HTML comment line ends a markdown list unless indented to the list item's content (the ACTIVITY markers are indented by two spaces on purpose). `replace_section()` keeps that indentation.
- `gautamkrishnar/keepalive-workflow` is blocked on GitHub ("Repository access blocked"); don't reintroduce it.
- The public github-readme-stats instance is rate-limited and unreliable; keep stats self-generated.
- Previewing locally: render with `gh api markdown` (mode `gfm`, context `andi1984/andi1984`) and screenshot with headless Chromium. The snap Chromium can't read `/tmp`; work under `~/snap/chromium/common/`. Headless screenshots of `<img>` SVGs freeze at t=0; open the SVG directly with `--virtual-time-budget` to see the end state.

## Agent memory

`.claude/memory/` holds the agent's persistent memory for this project (index in `MEMORY.md`). The local memory directory is a symlink to it, so new memories show up here as normal file changes. Remember the repo is public: no secrets or private details in memory files.
