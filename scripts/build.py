#!/usr/bin/env python3
"""Regenerate the GitHub profile: banner, project cards and live README sections.

Stdlib only, so the workflow needs nothing beyond `python`. Reads profile.toml,
pulls data from the GitHub API, the VS Code Marketplace, andi1984.dev's RSS feed
and dev.to, then writes:

  assets/banner-{light,dark}.svg
  assets/cards/<slug>-{light,dark}.svg
  README.md  (only between the <!-- NAME:START/END --> markers)

Set GITHUB_TOKEN to avoid the anonymous API rate limit.
"""

from __future__ import annotations

import base64
import html
import json
import os
import re
import sys
import time
import tomllib
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
README = ROOT / "README.md"
BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)

THEMES = {
    "light": {
        "bg": "#FBF7EF",
        "card": "#FFFDF8",
        "border": "#E8E0CF",
        "ink": "#1D2A20",
        "muted": "#5E6B60",
        "grid": "#E9E1CF",
        "soil": "#8A5A3B",
        "pot": "#C8734B",
        "accents": {
            "tomato": "#D9472F",
            "leaf": "#2F7D4F",
            "plum": "#7A4FD6",
            "sky": "#2A6FB0",
            "sun": "#E3A21A",
        },
    },
    "dark": {
        "bg": "#0F1712",
        "card": "#121B16",
        "border": "#24332A",
        "ink": "#EDEFE6",
        "muted": "#9AA89C",
        "grid": "#1B2620",
        "soil": "#6B4630",
        "pot": "#B5643F",
        "accents": {
            "tomato": "#FF7A5C",
            "leaf": "#6FD08C",
            "plum": "#B79CFF",
            "sky": "#7EB8F0",
            "sun": "#FFC857",
        },
    },
}

DISPLAY = "Fraunces:opsz,wght@9..144,600"
SANS = "Instrument Sans:wght@400"
MONO = "JetBrains Mono:wght@500"
FALLBACK = {
    "Fraunces": "Georgia, 'Times New Roman', serif",
    "Instrument Sans": "-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif",
    "JetBrains Mono": "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
}


# --------------------------------------------------------------------------- io


def fetch(url: str, *, data: bytes | None = None, headers: dict | None = None) -> bytes:
    headers = {"User-Agent": "andi1984-profile-builder", **(headers or {})}
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as res:
                return res.read()
        except Exception as exc:  # noqa: BLE001 - retry anything, re-raise the last
            if attempt == 2:
                raise
            print(f"retrying {url}: {exc}", file=sys.stderr)
            time.sleep(2 * (attempt + 1))
    raise AssertionError("unreachable")


def github(path: str):
    headers = {"Accept": "application/vnd.github+json"}
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    return json.loads(fetch(f"https://api.github.com{path}", headers=headers))


def write_if_changed(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text() == content:
        return
    path.write_text(content)
    print(f"wrote {path.relative_to(ROOT)}")


# ------------------------------------------------------------------------ fonts

_font_cache: dict[tuple[str, str], str] = {}


def font_face(spec: str, text: str) -> str:
    """Return an inline @font-face for `spec`, subset to the glyphs in `text`.

    SVGs shown through <img> can't load external fonts, so the woff2 is
    embedded as a data URI. Google Fonts' `text=` subsetting keeps each one to a
    few KB. On any failure we fall back to the system stacks in FALLBACK.
    """
    chars = "".join(sorted(set(text)))
    key = (spec, chars)
    if key in _font_cache:
        return _font_cache[key]
    family = spec.split(":")[0]
    query = urllib.parse.urlencode({"family": spec, "text": chars, "display": "block"})
    face = ""
    try:
        css = fetch(
            f"https://fonts.googleapis.com/css2?{query}",
            headers={"User-Agent": BROWSER_UA},
        ).decode()
        url = re.search(r"url\((https://[^)]+)\)", css).group(1)
        weight = re.search(r"font-weight:\s*(\d+)", css).group(1)
        woff2 = base64.b64encode(fetch(url, headers={"User-Agent": BROWSER_UA})).decode()
        face = (
            f"@font-face{{font-family:'{family}';font-weight:{weight};"
            f"src:url(data:font/woff2;base64,{woff2}) format('woff2');}}"
        )
    except Exception as exc:  # noqa: BLE001
        print(f"font {family} unavailable, using fallback: {exc}", file=sys.stderr)
    _font_cache[key] = face
    return face


def family(name: str) -> str:
    return f"'{name}', {FALLBACK[name]}"


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def wrap(text: str, width: int, max_lines: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(".,;") + "…"
    return lines


# ----------------------------------------------------------------------- banner

BANNER_GREETING = "Salü, I'm"
BANNER_NAME = "Andreas Sander"
BANNER_LINES = [
    "Senior product engineer. React & TypeScript by day,",
    "Rust, Kotlin and tomatoes after hours.",
]
BANNER_TAG = "andi1984 · Saarbrücken, DE"


def leaf(x: float, y: float, angle: float, size: float, delay: float, color: str) -> str:
    s = size
    return (
        f'<g transform="translate({x} {y}) rotate({angle})">'
        f'<path class="leaf" style="animation-delay:{delay}s" fill="{color}" '
        f'd="M0 0 C{s * .25} {-s * .32} {s * .75} {-s * .32} {s} 0 '
        f'C{s * .75} {s * .32} {s * .25} {s * .32} 0 0Z"/></g>'
    )


def tomato(x: float, y: float, r: float, delay: float, red: str, green: str) -> str:
    return (
        f'<g class="fruit" style="animation-delay:{delay}s">'
        f'<line x1="{x}" y1="{y - r - 9}" x2="{x}" y2="{y - r + 1}" stroke="{green}" stroke-width="2.5" stroke-linecap="round"/>'
        f'<circle cx="{x}" cy="{y}" r="{r}" fill="{red}"/>'
        f'<circle cx="{x - r * .35}" cy="{y - r * .35}" r="{r * .22}" fill="#fff" opacity=".35"/>'
        f'<path d="M{x - 6} {y - r + 1} L{x} {y - r - 3} L{x + 6} {y - r + 1}" fill="none" stroke="{green}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>'
        "</g>"
    )


def banner(theme: dict) -> str:
    a = theme["accents"]
    all_text = BANNER_GREETING + BANNER_TAG + "{ }"
    fonts = (
        font_face(DISPLAY, BANNER_NAME)
        + font_face(SANS, "".join(BANNER_LINES))
        + font_face(MONO, all_text)
    )
    leaves = "".join(
        [
            leaf(1002, 214, -150, 46, 0.9, a["leaf"]),
            leaf(1004, 186, -30, 52, 1.05, a["leaf"]),
            leaf(996, 150, -160, 44, 1.2, a["leaf"]),
            leaf(1006, 118, -20, 40, 1.35, a["leaf"]),
            leaf(1003, 88, -140, 30, 1.5, a["leaf"]),
            leaf(1004, 70, -60, 24, 1.6, a["leaf"]),
        ]
    )
    fruit = (
        tomato(1066, 168, 15, 1.8, a["tomato"], a["leaf"])
        + tomato(938, 140, 12, 1.95, a["tomato"], a["leaf"])
        + tomato(1050, 106, 10, 2.1, a["tomato"], a["leaf"])
    )
    lines = "".join(
        f'<text x="72" y="{218 + i * 34}" class="sub">{esc(t)}</text>'
        for i, t in enumerate(BANNER_LINES)
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="320" viewBox="0 0 1200 320" role="img" aria-labelledby="t d">
<title id="t">{esc(BANNER_NAME)}</title>
<desc id="d">{esc(" ".join(BANNER_LINES))}</desc>
<style>
{fonts}
.hi{{font:500 20px {family("JetBrains Mono")};fill:{a["leaf"]};letter-spacing:.02em}}
.name{{font:600 84px {family("Fraunces")};fill:{theme["ink"]};letter-spacing:-.02em}}
.sub{{font:400 25px {family("Instrument Sans")};fill:{theme["muted"]}}}
.tag{{font:500 15px {family("JetBrains Mono")};fill:{theme["muted"]};letter-spacing:.06em}}
.pot{{font:500 26px {family("JetBrains Mono")};fill:{theme["bg"]}}}
.stem{{stroke-dasharray:240;animation:grow 1.4s .2s cubic-bezier(.3,.7,.3,1) both}}
.leaf{{transform-box:fill-box;transform-origin:0% 50%;animation:pop .55s cubic-bezier(.3,1.6,.5,1) both}}
.fruit{{transform-box:fill-box;transform-origin:50% 0%;animation:pop .6s cubic-bezier(.3,1.6,.5,1) both}}
.plant{{transform-origin:1000px 236px;animation:sway 7s 2.6s ease-in-out infinite alternate}}
.sun{{transform-box:fill-box;transform-origin:center;animation:spin 40s linear infinite}}
.cursor{{animation:blink 1.1s steps(1) infinite}}
@keyframes grow{{from{{stroke-dashoffset:240}}}}
@keyframes pop{{from{{transform:scale(0)}}}}
@keyframes sway{{from{{transform:rotate(-1.6deg)}}to{{transform:rotate(1.6deg)}}}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}
@keyframes blink{{50%{{opacity:0}}}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}
</style>
<defs>
<pattern id="dots" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1.4" fill="{theme["grid"]}"/></pattern>
</defs>
<rect width="1200" height="320" rx="24" fill="{theme["bg"]}"/>
<rect width="1200" height="320" rx="24" fill="url(#dots)"/>
<text x="72" y="92" class="hi">{esc(BANNER_GREETING)}<tspan class="cursor">_</tspan></text>
<text x="66" y="172" class="name">{esc(BANNER_NAME)}</text>
{lines}
<text x="72" y="288" class="tag">{esc(BANNER_TAG.upper())}</text>
<g class="sun"><circle cx="1124" cy="74" r="22" fill="{a["sun"]}"/>
{"".join(f'<line x1="1124" y1="38" x2="1124" y2="30" stroke="{a["sun"]}" stroke-width="4" stroke-linecap="round" transform="rotate({d} 1124 74)"/>' for d in range(0, 360, 45))}
</g>
<g class="plant">
<path class="stem" d="M1000 236 C 994 196, 1010 160, 1000 120 S 1004 80, 1004 62" fill="none" stroke="{a["leaf"]}" stroke-width="5" stroke-linecap="round"/>
<path class="stem" d="M1001 190 Q 1040 178 1066 150" fill="none" stroke="{a["leaf"]}" stroke-width="3" stroke-linecap="round" style="animation-delay:1s"/>
<path class="stem" d="M999 160 Q 962 150 938 125" fill="none" stroke="{a["leaf"]}" stroke-width="3" stroke-linecap="round" style="animation-delay:1.15s"/>
<path class="stem" d="M1003 116 Q 1030 110 1050 93" fill="none" stroke="{a["leaf"]}" stroke-width="3" stroke-linecap="round" style="animation-delay:1.3s"/>
{leaves}
{fruit}
</g>
<path d="M938 236 H1062 L1050 296 Q1049 302 1043 302 H957 Q951 302 950 296 Z" fill="{theme["pot"]}"/>
<rect x="930" y="226" width="140" height="18" rx="6" fill="{theme["soil"]}"/>
<text x="1000" y="282" text-anchor="middle" class="pot">{{ }}</text>
</svg>
"""


# ------------------------------------------------------------------------ cards


def format_stat(project: dict, repo: dict) -> str:
    if project.get("stat") == "vscode-installs":
        body = json.dumps(
            {"filters": [{"criteria": [{"filterType": 7, "value": project["extension"]}]}], "flags": 256}
        ).encode()
        try:
            res = json.loads(
                fetch(
                    "https://marketplace.visualstudio.com/_apis/public/gallery/extensionquery",
                    data=body,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json;api-version=3.0-preview.1",
                    },
                )
            )
            stats = res["results"][0]["extensions"][0]["statistics"]
            installs = next(s["value"] for s in stats if s["statisticName"] == "install")
            return f"{installs / 1000:.1f}k installs" if installs >= 1000 else f"{int(installs)} installs"
        except Exception as exc:  # noqa: BLE001
            print(f"marketplace stats unavailable: {exc}", file=sys.stderr)
    return f"★ {repo['stargazers_count']}"


def card(project: dict, stat: str, theme: dict) -> str:
    accent = theme["accents"][project["accent"]]
    stack = " · ".join(project["stack"]).upper()
    pitch = wrap(project["pitch"], 50, 3)
    owner_repo = project["repo"]
    fonts = (
        font_face(DISPLAY, project["name"])
        + font_face(SANS, "".join(pitch))
        + font_face(MONO, stack + project["status"] + stat + owner_repo + "●")
    )
    pitch_svg = "".join(
        f'<text x="28" y="{122 + i * 23}" class="pitch">{esc(line)}</text>' for i, line in enumerate(pitch)
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="472" height="242" viewBox="-6 -6 472 242" role="img" aria-labelledby="t d">
<title id="t">{esc(project["name"])}</title>
<desc id="d">{esc(project["pitch"])}</desc>
<style>
{fonts}
.stack{{font:500 11.5px {family("JetBrains Mono")};fill:{accent};letter-spacing:.08em}}
.name{{font:600 30px {family("Fraunces")};fill:{theme["ink"]};letter-spacing:-.01em}}
.pitch{{font:400 15px {family("Instrument Sans")};fill:{theme["muted"]}}}
.meta{{font:500 12px {family("JetBrains Mono")};fill:{theme["muted"]}}}
.stat{{font:500 13px {family("JetBrains Mono")};fill:{theme["ink"]}}}
</style>
<rect x=".5" y=".5" width="459" height="229" rx="18" fill="{theme["card"]}" stroke="{theme["border"]}"/>
<path d="M392 0.5 H441.5 Q459.5 .5 459.5 18.5 V64 C440 70 400 52 392 .5Z" fill="{accent}" opacity=".16"/>
<path d="M418 14 C426 24 436 30 448 30 C442 20 432 14 418 14Z" fill="{accent}"/>
<text x="28" y="42" class="stack">{esc(stack)}</text>
<text x="27" y="84" class="name">{esc(project["name"])}</text>
{pitch_svg}
<line x1="28" y1="186" x2="432" y2="186" stroke="{theme["border"]}"/>
<text x="28" y="208" class="meta"><tspan fill="{accent}">●</tspan> {esc(project["status"])}</text>
<text x="432" y="208" text-anchor="end" class="stat">{esc(stat)}</text>
</svg>
"""


# ---------------------------------------------------------------------- readme


def norm_url(url: str) -> str:
    url = re.sub(r"^https?://(www\.)?", "", url.strip().lower())
    return url.rstrip("/")


def writing_section(cfg: dict) -> str:
    root = ET.fromstring(fetch(cfg["feed"]))
    try:
        articles = json.loads(fetch(f"https://dev.to/api/articles?username={cfg['devto_user']}&per_page=100"))
        mirrors = {norm_url(a["canonical_url"]): a["url"] for a in articles if a.get("canonical_url")}
    except Exception as exc:  # noqa: BLE001 - dev.to links are a nice-to-have
        print(f"dev.to unavailable: {exc}", file=sys.stderr)
        mirrors = {}

    lines = []
    for item in root.findall(".//item")[: cfg["count"]]:
        title = item.findtext("title", "").strip().replace("[", "\\[").replace("]", "\\]")
        link = item.findtext("link", "").strip()
        date = parsedate_to_datetime(item.findtext("pubDate")).strftime("%b %-d, %Y")
        cats = [c.text.strip() for c in item.findall("category") if c.text]
        kind = cats[0].lower() if cats else "post"
        topics = ", ".join(c.lower() for c in cats[1:3])
        meta = " · ".join(filter(None, [date, kind, topics]))
        if mirror := mirrors.get(norm_url(link)):
            meta += f' · <a href="{mirror}">also on dev.to</a>'
        lines.append(f"- **[{title}]({link})**<br><sub>{meta}</sub>")
    return "\n".join(lines)


def activity_section(cfg: dict) -> str:
    repos = []
    for owner in cfg["owners"]:
        repos += github(f"/users/{owner}/repos?sort=pushed&per_page=30&type=owner")
    repos = [
        r
        for r in repos
        if not (r["fork"] or r["archived"] or r["private"] or r["name"] in cfg["exclude"])
    ]
    repos.sort(key=lambda r: r["pushed_at"], reverse=True)
    links = [f"[{r['name']}]({r['html_url']})" for r in repos[: cfg["count"]]]
    joined = ", ".join(links[:-1]) + f" and {links[-1]}" if len(links) > 1 else "".join(links)
    return f"- 🌱 **Recently pushed** to {joined}"


def replace_section(text: str, name: str, body: str) -> str:
    pattern = re.compile(rf"(<!-- {name}:START -->\n).*?([ \t]*<!-- {name}:END -->)", re.S)
    if not pattern.search(text):
        raise SystemExit(f"README is missing the {name} markers")
    return pattern.sub(lambda m: m.group(1) + body + "\n" + m.group(2), text)


# ------------------------------------------------------------------------ main


def main() -> None:
    cfg = tomllib.loads((ROOT / "profile.toml").read_text())

    for mode, theme in THEMES.items():
        write_if_changed(ASSETS / f"banner-{mode}.svg", banner(theme))

    for project in cfg["projects"]:
        repo = github(f"/repos/{project['repo']}")
        stat = format_stat(project, repo)
        for mode, theme in THEMES.items():
            write_if_changed(ASSETS / "cards" / f"{project['slug']}-{mode}.svg", card(project, stat, theme))

    text = README.read_text()
    text = replace_section(text, "ACTIVITY", activity_section(cfg["activity"]))
    text = replace_section(text, "WRITING", writing_section(cfg["blog"]))
    write_if_changed(README, text)


if __name__ == "__main__":
    main()
