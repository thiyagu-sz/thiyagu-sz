#!/usr/bin/env python3
"""
Render animated SVG cards for the GitHub profile README (standard library only).

  python scripts/render_cards.py                    # animated cards from the GitHub API
  STATIC=1 python scripts/render_cards.py           # end state, no animation (screenshots)
  DEMO=1 python scripts/render_cards.py             # random fake data, no network

Env: GITHUB_TOKEN (required for live data), GH_USER (default "thiyagu-sz").
Without a token the script reuses data/contributions.json, or falls back to demo data.

Outputs: cards/hero.svg, cards/tile-{total,streak,best}.svg, cards/graph.svg, cards/monthly.svg

Why everything is inside the SVGs: GitHub strips <script>/<style> from README HTML, and SVGs
shown through <img> are sandboxed (no JS, no external requests). So all motion is CSS
@keyframes + SMIL inside each file, and fonts are embedded as base64 WOFF subsets.
Fonts (Plus Jakarta Sans, OFL) and fonts/metrics.json are built once by scripts/build_fonts.py;
if they are missing, the cards fall back to system fonts and estimated text widths.

Motion rules: content never depends on animation to be visible (start states come from
keyframes with fill-mode both, count-up's final frame is visible by default). Purely
decorative loops (border light, ripples, sweeps) start at opacity 0, so with
prefers-reduced-motion or STATIC=1 they simply don't appear.
"""
import base64
import datetime as dt
import json
import os
import random
import re
import sys
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape as _xml_escape

# ------------------------------------------------------------------ settings
USER = os.environ.get("GH_USER") or "thiyagu-sz"
NAME = "Thiyagu"
TAGLINE = "AI Engineer · Full-Stack Developer · Founder"
SUBLINE = "RAG pipelines · agentic workflows · Next.js + FastAPI"
PILLS = ["LLM apps", "Agentic AI", "SaaS builder"]

BG = "#0b1020"
PANEL = "#111833"
BORDER = "#1f2a4d"
TEXT = "#e6ebff"
MUTED = "#8a95b8"
ACCENT = "#4f8cff"
ACCENT_2 = "#9ad0ff"
INDIGO = "#a5b4fc"   # portfolio gradient (indigo -> rose)
ROSE = "#fda4af"
HEAT = ["#172040", "#1d3b7a", "#2a5bc0", "#4f8cff", "#9ad0ff"]  # level 0..4

STATIC = os.environ.get("STATIC") == "1"
DEMO = os.environ.get("DEMO") == "1"
ANIM = not STATIC

ROOT = Path(__file__).resolve().parent.parent
CARDS = ROOT / "cards"
DATA = ROOT / "data" / "contributions.json"
FONTS = ROOT / "fonts"

DISPLAY_FONT = "'Display', 'Plus Jakarta Sans', -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
BODY_FONT = "'Body', 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Page choreography (seconds). All cards start when the page loads, so these offsets make
# the page play top to bottom in ~2s: hero -> tiles -> graph -> monthly. Ambient loops follow.
T_TILES = (0.3, 0.45, 0.6)
T_GRAPH = 0.75
T_MONTHLY = 1.0


# ------------------------------------------------------------------ text metrics
try:
    METRICS = json.loads((FONTS / "metrics.json").read_text(encoding="utf-8"))
except (OSError, ValueError):
    METRICS = {}


def advance(ch, nxt, face, size):
    """Advance of ch in px (incl. kerning against the next char) for the embedded font."""
    m = METRICS.get(face)
    if not m:
        return size * (0.62 if face == "display" else 0.56)
    units = m["adv"].get(ch, m["upm"] * 0.6) + (m.get("kern", {}).get(ch + nxt, 0) if nxt else 0)
    return units * size / m["upm"]


def text_width(s, face, size):
    return sum(advance(c, s[i + 1] if i + 1 < len(s) else "", face, size) for i, c in enumerate(s))


# ------------------------------------------------------------------ data
QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}"""


def days_from_weeks(weeks):
    return [(d["date"], d["contributionCount"]) for w in weeks for d in w["contributionDays"]]


def fetch_days():
    """Return [(iso_date, count), ...] oldest first."""
    if DEMO:
        return demo_days()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        if DATA.exists():
            print("GITHUB_TOKEN not set - using cached data/contributions.json", file=sys.stderr)
            cached = json.loads(DATA.read_text(encoding="utf-8"))
            if "weeks" in cached:
                return days_from_weeks(cached["weeks"])
            return [tuple(d) for d in cached["days"]]  # older cache format
        print("WARNING: GITHUB_TOKEN not set and no cached data - rendering DEMO data",
              file=sys.stderr)
        return demo_days()

    body = json.dumps({"query": QUERY, "variables": {"login": USER}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "readme-cards",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    if payload.get("errors"):
        raise SystemExit(f"GraphQL error: {payload['errors']}")
    user = (payload.get("data") or {}).get("user")
    if not user:
        raise SystemExit(f"GitHub user {USER!r} not found")
    weeks = user["contributionsCollection"]["contributionCalendar"]["weeks"]

    DATA.parent.mkdir(exist_ok=True)
    DATA.write_text(json.dumps({"user": USER, "weeks": weeks}, indent=1) + "\n", encoding="utf-8")
    return days_from_weeks(weeks)


def demo_days():
    rng = random.Random()
    today = dt.date.today()
    start = today - dt.timedelta(days=364 + (today.weekday() + 1) % 7)  # a Sunday
    out, d = [], start
    while d <= today:
        busy = rng.random() < (0.55 if d.weekday() >= 5 else 0.78)
        out.append((d.isoformat(), rng.choice([1, 1, 2, 3, 4, 5, 7, 9, 12, 18]) if busy else 0))
        d += dt.timedelta(days=1)
    return out


def stats(days):
    counts = [c for _, c in days]
    total = sum(counts)

    # current streak: if today is still 0, start counting from yesterday
    cur, i = 0, len(counts) - 1
    if i >= 0 and counts[i] == 0:
        i -= 1
    while i >= 0 and counts[i] > 0:
        cur += 1
        i -= 1

    longest = run = 0
    for c in counts:
        run = run + 1 if c else 0
        longest = max(longest, run)

    bi = max(range(len(days)), key=lambda k: days[k][1]) if days else 0

    # monthly totals for the last 12 calendar months (including the current one)
    last = dt.date.fromisoformat(days[-1][0]) if days else dt.date.today()
    keys = []
    y, m = last.year, last.month
    for _ in range(12):
        keys.append(f"{y:04d}-{m:02d}")
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    keys.reverse()
    monthly = {k: 0 for k in keys}
    for date, c in days:
        if date[:7] in monthly:
            monthly[date[:7]] += c

    return {"total": total, "current": cur, "longest": longest, "busiest_index": bi,
            "busiest": days[bi] if days else ("", 0), "monthly": monthly}


# ------------------------------------------------------------------ svg helpers
def esc(s):
    return _xml_escape(str(s), {'"': "&quot;", "'": "&apos;"})


def font_face(family, fname, weight):
    f = FONTS / fname
    if not f.exists():
        return ""
    b64 = base64.b64encode(f.read_bytes()).decode()
    return (f"@font-face{{font-family:'{family}';font-weight:{weight};font-display:block;"
            f"src:url(data:font/woff;base64,{b64}) format('woff')}}\n")


KEYFRAMES = {
    "fadeUp": "{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}",
    "fadeIn": "{from{opacity:0}to{opacity:1}}",
    "rise": "{from{opacity:0;transform:translateY(26px) scale(.9)}to{opacity:1;transform:translateY(0) scale(1)}}",
    "grow": "{from{transform:scaleY(0)}to{transform:scaleY(1)}}",
    "pop": "{0%{opacity:0;transform:scale(.3)}70%{opacity:1;transform:scale(1.15)}100%{opacity:1;transform:scale(1)}}",
    "blink": "{0%,49%{opacity:1}50%,100%{opacity:0}}",
    "draw": "{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}",
    "orbit": "{from{stroke-dashoffset:0;opacity:1}to{stroke-dashoffset:-1;opacity:1}}",
    "drift": "{0%,100%{transform:translate(0,0)}50%{transform:translate(-46px,18px)}}",
    "drift2": "{0%,100%{transform:translate(0,0)}50%{transform:translate(40px,-14px)}}",
    "twinkle": "{0%,100%{opacity:.15}50%{opacity:1}}",
    "wave": "{0%,100%{transform:scale(1);opacity:1}50%{transform:scale(1.45);opacity:.55}}",
    "ripple": "{from{transform:scale(1);opacity:.75}to{transform:scale(3.4);opacity:0}}",
    "floaty": "{0%,100%{transform:translateY(0)}50%{transform:translateY(-5px)}}",
    "sweep": "{0%{transform:translateX(0);opacity:1}45%,100%{transform:translateX(var(--sweep));opacity:1}}",
    "comet": "{0%{transform:translateX(0);opacity:0}8%{opacity:1}42%{transform:translateX(var(--run));opacity:1}50%,100%{transform:translateX(var(--run));opacity:0}}",
    "glow": "{0%,100%{opacity:.35}50%{opacity:1}}",
}


def svg(width, height, body, css, label, display_font=False):
    fonts = font_face("Display", "display.woff", "100 900") if display_font else ""
    fonts += font_face("Body", "body.woff", "100 599") + font_face("Body", "body-bold.woff", "600 900")
    anim = ""
    if ANIM:
        used = "\n".join(f"@keyframes {n}{k}" for n, k in KEYFRAMES.items() if re.search(rf"\b{n}\b", css))
        anim = (f"{used}\n{css.strip()}\n"
                "@media (prefers-reduced-motion: reduce){*{animation:none!important}}")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="t">
<title id="t">{esc(label)}</title>
<style>
{fonts}.d{{font-family:{DISPLAY_FONT}}}
.b{{font-family:{BODY_FONT}}}
.fb{{transform-box:fill-box;transform-origin:center}}
{anim}
</style>
{body.strip()}
</svg>
"""


def panel(w, h, r=16, orbit_delay=None, orbit_dur=7):
    """Rounded panel; in animated mode a small light runs around the border forever."""
    out = (f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="{r}" '
           f'fill="{PANEL}" stroke="{BORDER}"/>')
    if ANIM and orbit_delay is not None:
        out += (f'\n<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="{r}" fill="none" '
                f'stroke="url(#edge)" stroke-width="1.6" pathLength="1" stroke-dasharray=".07 .93" '
                f'opacity="0" style="animation:orbit {orbit_dur}s linear {orbit_delay:.2f}s infinite"/>')
    return out


def edge_gradient(w, h):
    return (f'<linearGradient id="edge" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="{w}" y2="{h}">'
            f'<stop offset="0" stop-color="{ACCENT_2}"/><stop offset=".5" stop-color="{INDIGO}"/>'
            f'<stop offset="1" stop-color="{ROSE}"/></linearGradient>')


def ripple(cx, cy, r, color, delay, period=2.4):
    if not ANIM:
        return ""
    return (f'<circle class="fb" cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="none" stroke="{color}" '
            f'stroke-width="1.5" opacity="0" style="animation:ripple {period}s ease-out {delay:.2f}s infinite"/>')


def count_up(value, x, y, attrs, start, frames=18, dur=0.9):
    """Count a number up from 0. CSS can't change text, so stack one <text> per frame and
    flip visibility with SMIL <set>. The final frame is visible by default (hidden only while
    counting), so the real number shows even where SMIL never runs."""
    final = f"{value:,}"
    if not ANIM or value == 0:
        return f'<text x="{x}" y="{y}" {attrs}>{final}</text>'
    step = dur / frames
    out = []
    for i in range(1, frames):
        v = round(value * (1 - (1 - i / frames) ** 3))  # ease-out cubic
        begin = start + (i - 1) * step
        out.append(f'<text x="{x}" y="{y}" {attrs} visibility="hidden">{v:,}'
                   f'<set attributeName="visibility" to="visible" begin="{begin:.3f}s" dur="{step:.3f}s"/></text>')
    last = start + (frames - 1) * step
    out.append(f'<text x="{x}" y="{y}" {attrs}>{final}'
               f'<set attributeName="visibility" to="hidden" begin="0s" end="{last:.3f}s"/>'
               f'<set attributeName="visibility" to="visible" begin="{last:.3f}s" fill="freeze"/></text>')
    return "\n".join(out)


def smooth_path(pts):
    """Catmull-Rom spline through pts as a cubic Bezier path."""
    if len(pts) < 2:
        return ""
    d = [f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"]
    for i in range(len(pts) - 1):
        p0 = pts[i - 1] if i else pts[i]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[i + 2] if i + 2 < len(pts) else p2
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d.append(f"C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}")
    return " ".join(d)


# ------------------------------------------------------------------ hero
def hero():
    w, h = 900, 220
    rng = random.Random(42)  # fixed layout, so the file only changes when content does
    name = f"Hi, I'm {NAME}"
    nsize, nx, ny = 64, 46, 102
    name_w = text_width(name, "display", nsize)

    # name: one <text> per letter so each can rise in on its own beat
    letters, shine_letters, x = [], [], nx
    for i, ch in enumerate(name):
        adv = advance(ch, name[i + 1] if i + 1 < len(name) else "", "display", nsize)
        if ch != " ":
            style = f' style="animation-delay:{0.05 + i * 0.035:.3f}s"' if ANIM else ""
            letters.append(f'<text class="d ch fb" x="{x:.1f}" y="{ny}"{style}>{esc(ch)}</text>')
            shine_letters.append(f'<text class="d" x="{x:.1f}" y="{ny}">{esc(ch)}</text>')
        x += adv

    # subline typed character by character, with a cursor that follows the text
    ssize, sx, sy = 15, 50, 190
    sub_w = text_width(SUBLINE, "body", ssize)
    t0, per = 1.0, 0.022
    typing = cursor_anim = ""
    if ANIM:
        n = len(SUBLINE)
        dur = t0 + n * per
        widths = [0.0] + [text_width(SUBLINE[:k], "body", ssize) for k in range(1, n + 1)]
        times = [0.0] + [(t0 + (k - 1) * per) / dur for k in range(1, n + 1)]
        kt = ";".join(f"{t:.4f}" for t in times)
        typing = (f'<animate attributeName="width" calcMode="discrete" dur="{dur:.3f}s" fill="freeze" '
                  f'keyTimes="{kt}" values="{";".join(f"{v + 2:.1f}" for v in widths)}"/>')
        cursor_anim = (f'<animate attributeName="x" calcMode="discrete" dur="{dur:.3f}s" fill="freeze" '
                       f'keyTimes="{kt}" values="{";".join(f"{sx + v + 3:.1f}" for v in widths)}"/>')

    # floating "pills" on the right
    pills, py = [], (98, 136, 174)
    for i, (label, right) in enumerate(zip(PILLS, (856, 812, 862))):
        pw = text_width(label, "body-bold", 13) + 28
        px = right - pw
        anim = (f' style="animation:pop .5s ease-out {1.05 + i * .12:.2f}s both, '
                f'floaty {3.2 + i * .6:.1f}s ease-in-out {1.6 + i * .3:.1f}s infinite"') if ANIM else ""
        pills.append(
            f'<g class="fb"{anim}>'
            f'<rect x="{px:.1f}" y="{py[i] - 15}" width="{pw:.1f}" height="28" rx="14" fill="{PANEL}" '
            f'fill-opacity=".85" stroke="{BORDER}"/>'
            f'<circle cx="{px + 13:.1f}" cy="{py[i] - 1}" r="3" fill="{(ACCENT_2, INDIGO, ROSE)[i]}"/>'
            f'<text class="b" x="{px + 21:.1f}" y="{py[i] + 3.5}" font-size="13" font-weight="700" fill="{TEXT}">{esc(label)}</text></g>'
        )

    stars = []
    for i in range(18):
        cx, cy = rng.uniform(520, 885), rng.uniform(14, 206)
        r = rng.choice([0.8, 1, 1.2, 1.6])
        anim = f' style="animation:twinkle {rng.uniform(1.8, 3.6):.1f}s ease-in-out {rng.uniform(0, 3):.1f}s infinite"' if ANIM else ""
        stars.append(f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="{r}" fill="#ffffff" opacity=".55"{anim}/>')

    dots = "\n".join(
        f'<circle class="dot fb" style="animation-delay:{0.55 + i * 0.05:.2f}s, {1.6 + (i % 3 + i // 3) * 0.18:.2f}s" '
        f'cx="{816 + (i % 3) * 18}" cy="{36 + (i // 3) * 18}" r="4" fill="{HEAT[(i * 2 + i // 3) % 4 + 1]}"/>'
        for i in range(9)
    )

    under_w = min(name_w * 0.55, 260)
    css = f"""
.ch{{animation:rise .65s cubic-bezier(.2,1.3,.4,1) both}}
.shine{{animation:fadeIn .4s ease-out 1s both}}
.line{{stroke-dasharray:1;animation:draw .7s cubic-bezier(.6,0,.2,1) .55s both}}
.comet{{--run:{under_w:.0f}px;animation:comet 5s ease-in-out 2s infinite}}
.tag{{animation:fadeUp .55s ease-out .7s both}}
.cur{{animation:blink 1.05s steps(1) {t0 + len(SUBLINE) * per:.2f}s infinite both}}
.dot{{animation-name:pop,wave;animation-duration:.45s,2.6s;animation-timing-function:ease-out,ease-in-out;animation-iteration-count:1,infinite;animation-fill-mode:both,none}}
.orb1{{animation:drift 9s ease-in-out infinite}}
.orb2{{animation:drift2 11s ease-in-out infinite}}
"""
    shine = ""
    if ANIM:
        shine = f"""<g class="shine" fill="url(#shine)" font-size="{nsize}" aria-hidden="true">{''.join(shine_letters)}</g>"""
    comet = ""
    if ANIM:
        comet = (f'<circle class="comet" cx="{nx + 4}" cy="124" r="3" fill="#fff" opacity="0"/>'
                 f'<circle class="comet" cx="{nx + 4}" cy="124" r="7" fill="{ACCENT_2}" fill-opacity=".35" opacity="0"/>')
    shine_anim = ('<animateTransform attributeName="gradientTransform" type="translate" '
                  'values="-260 0;760 0;760 0" keyTimes="0;0.45;1" dur="4.5s" begin="1.2s" repeatCount="indefinite"/>') if ANIM else ""

    body = f"""
<defs>
  <clipPath id="card"><rect width="{w}" height="{h}" rx="18"/></clipPath>
  <clipPath id="typed"><rect x="{sx - 2}" y="{sy - 18}" width="{sub_w + 4:.1f}" height="26">{typing}</rect></clipPath>
  <linearGradient id="nameGrad" gradientUnits="userSpaceOnUse" x1="{nx}" y1="0" x2="{nx + name_w:.0f}" y2="0">
    <stop offset="0" stop-color="#ffffff"/>
    <stop offset=".45" stop-color="{TEXT}"/>
    <stop offset=".75" stop-color="{INDIGO}"/>
    <stop offset="1" stop-color="{ROSE}"/>
  </linearGradient>
  <linearGradient id="shine" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="160" y2="0" gradientTransform="translate(-260 0)">
    <stop offset="0" stop-color="#fff" stop-opacity="0"/>
    <stop offset=".5" stop-color="#fff" stop-opacity=".9"/>
    <stop offset="1" stop-color="#fff" stop-opacity="0"/>
    {shine_anim}
  </linearGradient>
  <linearGradient id="uline" gradientUnits="userSpaceOnUse" x1="{nx + 4}" y1="0" x2="{nx + 4 + under_w:.0f}" y2="0">
    <stop offset="0" stop-color="{ACCENT}"/><stop offset=".6" stop-color="{INDIGO}"/><stop offset="1" stop-color="{ROSE}"/>
  </linearGradient>
  <radialGradient id="glow1"><stop offset="0" stop-color="{ACCENT}" stop-opacity=".42"/><stop offset="1" stop-color="{ACCENT}" stop-opacity="0"/></radialGradient>
  <radialGradient id="glow2"><stop offset="0" stop-color="{INDIGO}" stop-opacity=".22"/><stop offset=".5" stop-color="{ROSE}" stop-opacity=".07"/><stop offset="1" stop-color="{ROSE}" stop-opacity="0"/></radialGradient>
  {edge_gradient(w, h)}
</defs>
<g clip-path="url(#card)">
  <rect width="{w}" height="{h}" fill="{BG}"/>
  <circle class="orb1" cx="740" cy="20" r="260" fill="url(#glow1)"/>
  <circle class="orb2" cx="430" cy="240" r="230" fill="url(#glow2)"/>
  {chr(10).join(stars)}
</g>
{panel(w, h, 18, orbit_delay=1.4, orbit_dur=8).replace(f'fill="{PANEL}"', 'fill="none"')}
{dots}
{chr(10).join(pills)}
<g fill="url(#nameGrad)" font-size="{nsize}">{''.join(letters)}</g>
{shine}
<path class="line" d="M{nx + 4},124 H{nx + 4 + under_w:.0f}" pathLength="1" stroke="url(#uline)" stroke-width="3.5" stroke-linecap="round" fill="none"/>
{comet}
<text class="b tag" x="{sx}" y="160" font-size="19" font-weight="700" fill="{TEXT}">{esc(TAGLINE)}</text>
<text class="b" x="{sx}" y="{sy}" font-size="{ssize}" fill="{MUTED}" clip-path="url(#typed)">{esc(SUBLINE)}</text>
<rect class="cur" x="{sx + sub_w + 3:.1f}" y="{sy - 13}" width="8" height="16" rx="1.5" fill="{ACCENT}">{cursor_anim}</rect>
"""
    return svg(w, h, body, css, f"Hi, I'm {NAME}. {TAGLINE}. {SUBLINE}", display_font=True)


# ------------------------------------------------------------------ tiles
TILE_W, TILE_H = 290, 140


def tile(label, value, caption, delay, viz, viz_label):
    """viz(x0, x1, start) -> svg for the mini chart on the right side of the tile."""
    w, h = TILE_W, TILE_H
    num_w = text_width(f"{value:,}", "display", 46)
    x0 = max(24 + num_w + 18, 176)
    css = f"""
.tile{{animation:fadeUp .55s ease-out {delay}s both}}
.vz{{animation:fadeIn .4s ease-out {delay + 0.35:.2f}s both}}
.ln{{stroke-dasharray:1;animation:draw .9s ease-out {delay + 0.45:.2f}s both}}
.pp{{animation:pop .35s ease-out both}}
.gr{{transform-box:fill-box;transform-origin:bottom;animation:grow .5s cubic-bezier(.2,.8,.2,1) both}}
.tw{{animation:twinkle 1.8s ease-in-out {delay + 1.2:.2f}s infinite}}
"""
    body = f"""
<defs>{edge_gradient(w, h)}
<linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{ACCENT}" stop-opacity=".45"/><stop offset="1" stop-color="{ACCENT}" stop-opacity="0"/></linearGradient>
<linearGradient id="spark" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{ACCENT}"/><stop offset=".7" stop-color="{INDIGO}"/><stop offset="1" stop-color="{ROSE}"/></linearGradient>
</defs>
<g class="tile">
{panel(w, h, orbit_delay=delay + 1.3, orbit_dur=6 + delay * 4)}
<circle cx="{w - 28}" cy="34" r="4" fill="{ACCENT}"/>
{ripple(w - 28, 34, 4, ACCENT, delay + 1.0, 2.6)}
<text class="b" x="24" y="38" font-size="12" font-weight="700" fill="{MUTED}" letter-spacing="1.6">{esc(label.upper())}</text>
{count_up(value, 24, 94, f'class="d" font-size="46" fill="{TEXT}"', start=delay + 0.2)}
<text class="b" x="24" y="120" font-size="13" fill="{ACCENT_2}">{esc(caption)}</text>
<g aria-label="{esc(viz_label)}">{viz(x0, w - 24, delay + 0.35)}</g>
</g>"""
    return svg(w, h, body, css, f"{label}: {value:,} ({caption})", display_font=True)


def viz_sparkline(values):
    def make(x0, x1, start):
        top, bot = 58, 102
        mx = max(values) or 1
        n = len(values)
        pts = [(x0 + (x1 - x0) * i / (n - 1), bot - (bot - top) * v / mx) for i, v in enumerate(values)]
        line = smooth_path(pts)
        area = f"{line} L{x1:.1f},{bot} L{x0:.1f},{bot} Z"
        ex, ey = pts[-1]
        return (f'<path class="vz" d="{area}" fill="url(#area)"/>'
                f'<path class="ln" d="{line}" pathLength="1" fill="none" stroke="url(#spark)" stroke-width="2.2" stroke-linecap="round"/>'
                f'<circle class="pp fb" style="animation-delay:{start + 1.0:.2f}s" cx="{ex:.1f}" cy="{ey:.1f}" r="3.5" fill="{ROSE}"/>'
                + ripple(ex, ey, 3.5, ROSE, start + 1.4, 2.2))
    return make


def viz_days(counts):
    """Last 14 days as 2 x 7 squares; days in the current streak are highlighted."""
    streak_from = len(counts)
    i = len(counts) - 1
    if i >= 0 and counts[i] == 0:
        i -= 1
    while i >= 0 and counts[i] > 0:
        streak_from = i
        i -= 1

    def make(x0, x1, start):
        cell, gap = 10, 3
        pitch = cell + gap
        gx = x1 - (7 * pitch - gap)
        out = []
        for k, c in enumerate(counts):
            col, row = k % 7, k // 7
            in_streak = k >= streak_from and c > 0
            fill = ACCENT_2 if in_streak else (HEAT[2] if c else HEAT[0])
            out.append(f'<rect class="pp fb" style="animation-delay:{start + k * 0.04:.2f}s" x="{gx + col * pitch}" '
                       f'y="{62 + row * pitch}" width="{cell}" height="{cell}" rx="2.5" fill="{fill}">'
                       f'<title>{c} contribution{"s" if c != 1 else ""}</title></rect>')
        lx, ly = gx + 6 * pitch + cell / 2, 62 + pitch + cell / 2
        if counts and counts[-1] > 0:
            out.append(ripple(lx, ly, 5, ACCENT_2, start + 1.2, 2.0))
        out.append(f'<text class="b vz" x="{gx}" y="{62 + 2 * pitch + 12}" font-size="10" fill="{MUTED}">last 14 days</text>')
        return "".join(out)
    return make


def viz_week(counts, hi):
    """Seven bars around the busiest day, busiest highlighted, with a twinkling spark."""
    def make(x0, x1, start):
        bw, gap = 8, 4
        gx = x1 - (7 * (bw + gap) - gap)
        top, bot = 60, 102
        mx = max(counts) or 1
        out = []
        for k, c in enumerate(counts):
            bh = max(2, (bot - top) * c / mx)
            x = gx + k * (bw + gap)
            fill = ROSE if k == hi else HEAT[2]
            out.append(f'<rect class="gr" style="animation-delay:{start + k * 0.06:.2f}s" x="{x}" y="{bot - bh:.1f}" '
                       f'width="{bw}" height="{bh:.1f}" rx="2" fill="{fill}"/>')
        sx = gx + hi * (bw + gap) + bw / 2
        sy = top - 8
        out.append(f'<path class="tw" d="M{sx},{sy - 5} L{sx + 1.4},{sy - 1.4} L{sx + 5},{sy} L{sx + 1.4},{sy + 1.4} '
                   f'L{sx},{sy + 5} L{sx - 1.4},{sy + 1.4} L{sx - 5},{sy} L{sx - 1.4},{sy - 1.4} Z" fill="{ROSE}"/>')
        return "".join(out)
    return make


# ------------------------------------------------------------------ graph
def graph(days, busiest_index):
    cell, gap = 12, 3
    pitch = cell + gap
    top = 58
    first = dt.date.fromisoformat(days[0][0])
    pad = (first.weekday() + 1) % 7  # GitHub weeks start on Sunday
    grid = [None] * pad + list(days)
    cols = min(53, (len(grid) + 6) // 7)
    drop = max(0, len(grid) - cols * 7)
    grid = grid[drop:]
    busiest_index += pad - drop
    w = 900
    left = (w - (cols * pitch - gap)) // 2 + 12
    grid_h = 7 * pitch - gap
    h = top + grid_h + 46

    nonzero = sorted(c for _, c in days if c)

    def level(c):  # quartiles of non-zero days, like GitHub
        if c == 0 or not nonzero:
            return 0
        q = [nonzero[int(len(nonzero) * p)] for p in (0.25, 0.5, 0.75)]
        return 1 + sum(c > t for t in q)

    sweep_len = cols * pitch + 160
    css = f"""
.lbl{{animation:fadeIn .5s ease-out {T_GRAPH - 0.1:.2f}s both}}
.c{{transform-box:fill-box;transform-origin:center;animation:pop .32s ease-out both}}
.sw{{--sweep:{sweep_len}px;animation:sweep 7s ease-in-out 2.4s infinite}}
"""
    rects, labels, last_month, last_x = [], [], None, -99
    hot = None
    for i, d in enumerate(grid):
        col, row = divmod(i, 7)
        if d is None:
            continue
        date, c = d
        x, y = left + col * pitch, top + row * pitch
        if i == busiest_index and c:
            hot = (x + cell / 2, y + cell / 2)
        rects.append(
            f'<rect class="c" style="animation-delay:{T_GRAPH + col * 0.018:.3f}s" x="{x}" y="{y}" '
            f'width="{cell}" height="{cell}" rx="3" fill="{HEAT[level(c)]}">'
            f'<title>{c} on {date}</title></rect>'
        )
        if date[:7] != last_month and dt.date.fromisoformat(date).day <= 7:
            if x - last_x >= 30 and x < left + cols * pitch - 20:
                labels.append(f'<text class="b lbl" x="{x}" y="{top - 9}" font-size="11" fill="{MUTED}">'
                              f'{MONTHS[int(date[5:7]) - 1]}</text>')
                last_x = x
            last_month = date[:7]
    for r, lbl in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        labels.append(f'<text class="b lbl" x="{left - 8}" y="{top + r * pitch + 10}" font-size="10" '
                      f'fill="{MUTED}" text-anchor="end">{lbl}</text>')

    ly = top + grid_h + 18
    right = left + cols * pitch - gap
    lx = right - 5 * pitch + gap - 34
    legend = [f'<text class="b lbl" x="{lx - 6}" y="{ly + 10}" font-size="11" fill="{MUTED}" text-anchor="end">Less</text>']
    for k in range(5):
        legend.append(f'<rect class="lbl" x="{lx + k * pitch}" y="{ly}" width="{cell}" height="{cell}" rx="3" fill="{HEAT[k]}"/>')
    legend.append(f'<text class="b lbl" x="{lx + 5 * pitch + 3}" y="{ly + 10}" font-size="11" fill="{MUTED}">More</text>')
    if hot:
        legend.append(f'<rect class="lbl" x="{left}" y="{ly + 1}" width="10" height="10" rx="5" fill="none" stroke="{ROSE}" stroke-width="2"/>'
                      f'<text class="b lbl" x="{left + 16}" y="{ly + 10}" font-size="11" fill="{MUTED}">busiest day</text>')

    extra = ""
    if hot:
        hx, hy = hot
        extra = (f'<rect class="c" style="animation-delay:{T_GRAPH + 1.0:.2f}s" x="{hx - 8:.1f}" y="{hy - 8:.1f}" width="16" height="16" rx="5" '
                 f'fill="none" stroke="{ROSE}" stroke-width="2"/>')
        if ANIM:
            extra += (f'<rect class="fb" x="{hx - 8:.1f}" y="{hy - 8:.1f}" width="16" height="16" rx="5" fill="none" stroke="{ROSE}" '
                      f'stroke-width="1.5" opacity="0" style="animation:ripple 2.4s ease-out {T_GRAPH + 1.4:.2f}s infinite"/>')
    sweep = ""
    if ANIM:
        sweep = (f'<g clip-path="url(#gridclip)"><rect class="sw" x="{left - 140}" y="{top}" width="120" height="{grid_h}" '
                 f'fill="url(#band)" opacity="0"/></g>')

    total = sum(c for _, c in days)
    body = f"""
<defs>{edge_gradient(w, h)}
<clipPath id="gridclip"><rect x="{left}" y="{top}" width="{cols * pitch - gap}" height="{grid_h}"/></clipPath>
<linearGradient id="band" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity=".16"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
</defs>
{panel(w, h, orbit_delay=2.0, orbit_dur=12)}
<text class="b lbl" x="{left - 30}" y="30" font-size="15" font-weight="700" fill="{TEXT}">{total:,} contributions in the last year</text>
{chr(10).join(labels)}
{chr(10).join(legend)}
{chr(10).join(rects)}
{extra}
{sweep}
"""
    return svg(w, h, body, css, f"{total:,} contributions in the last year")


# ------------------------------------------------------------------ monthly
def monthly_chart(monthly):
    w, h = 900, 220
    left, right, bottom, top = 40, 30, 176, 66
    n = len(monthly)
    slot = (w - left - right) / max(n, 1)
    bw = slot * 0.56
    mx = max(monthly.values(), default=0) or 1
    peak = max(range(n), key=lambda i: list(monthly.values())[i]) if n else -1
    t_line = T_MONTHLY + n * 0.07 + 0.25
    css = f"""
.lbl{{animation:fadeIn .5s ease-out {T_MONTHLY - 0.15:.2f}s both}}
.bar{{transform-box:fill-box;transform-origin:bottom;animation:grow .5s cubic-bezier(.2,.8,.2,1) both}}
.v{{animation:fadeIn .35s ease-out both}}
.trend{{stroke-dasharray:1;animation:draw .9s ease-in-out {t_line:.2f}s both}}
.pt{{animation:pop .3s ease-out both}}
.peak{{animation:glow 2.2s ease-in-out {t_line + 1:.2f}s infinite}}
"""
    bars, labels, pts = [], [], []
    for i, (m, v) in enumerate(monthly.items()):
        bh = max(3, (bottom - top) * v / mx)
        x = left + i * slot + (slot - bw) / 2
        y = bottom - bh
        delay = T_MONTHLY + i * 0.07
        cx = x + bw / 2
        pts.append((cx, y))
        mname = MONTHS[int(m[5:]) - 1]
        fill = "url(#barPeak)" if i == peak and v else "url(#bar)"
        bars.append(
            f'<rect class="bar" style="animation-delay:{delay:.2f}s" x="{x:.1f}" y="{y:.1f}" '
            f'width="{bw:.1f}" height="{bh:.1f}" rx="5" fill="{fill}"><title>{v:,} in {mname} {m[:4]}</title></rect>'
        )
        labels.append(
            f'<text class="b v" style="animation-delay:{delay + 0.3:.2f}s" x="{cx:.1f}" y="{y - 10:.1f}" '
            f'font-size="12" font-weight="700" fill="{ROSE if i == peak and v else ACCENT_2}" text-anchor="middle" '
            f'stroke="{PANEL}" stroke-width="4" paint-order="stroke">{v:,}</text>\n'
            f'<text class="b lbl" x="{cx:.1f}" y="{bottom + 22}" font-size="11" fill="{MUTED}" text-anchor="middle">{mname}</text>'
        )
    dots = "".join(
        f'<circle class="pt fb" style="animation-delay:{t_line + 0.9 * i / max(n - 1, 1):.2f}s" cx="{px:.1f}" cy="{py:.1f}" '
        f'r="3" fill="{BG}" stroke="{ROSE if i == peak else INDIGO}" stroke-width="2"/>'
        for i, (px, py) in enumerate(pts)
    )
    peak_glow = ""
    if 0 <= peak and ANIM:
        px, py = pts[peak]
        peak_glow = f'<circle class="peak" cx="{px:.1f}" cy="{py:.1f}" r="9" fill="{ROSE}" fill-opacity=".25" opacity="0"/>' + ripple(px, py, 4, ROSE, t_line + 1.2, 2.4)
    body = f"""
<defs>{edge_gradient(w, h)}
<linearGradient id="bar" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{ACCENT_2}"/><stop offset="1" stop-color="{ACCENT}"/></linearGradient>
<linearGradient id="barPeak" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{ROSE}"/><stop offset="1" stop-color="{INDIGO}"/></linearGradient>
<linearGradient id="trendGrad" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{INDIGO}"/><stop offset="1" stop-color="{ROSE}"/></linearGradient>
</defs>
{panel(w, h, orbit_delay=2.6, orbit_dur=12)}
<text class="b lbl" x="{left}" y="34" font-size="15" font-weight="700" fill="{TEXT}">Contributions per month</text>
<text class="b lbl" x="{w - right}" y="34" font-size="12" fill="{MUTED}" text-anchor="end">last 12 months</text>
<line x1="{left}" y1="{bottom + 0.5}" x2="{w - right}" y2="{bottom + 0.5}" stroke="{BORDER}"/>
{chr(10).join(bars)}
<path class="trend" d="{smooth_path(pts)}" pathLength="1" fill="none" stroke="url(#trendGrad)" stroke-width="2" stroke-opacity=".85" stroke-linecap="round"/>
{peak_glow}
{dots}
{chr(10).join(labels)}
"""
    return svg(w, h, body, css, "Contributions per month, last 12 months: " +
               ", ".join(f"{MONTHS[int(m[5:]) - 1]} {v}" for m, v in monthly.items()))


# ------------------------------------------------------------------ main
def main():
    days = fetch_days()
    if not days:
        raise SystemExit("No contribution data")
    s = stats(days)
    CARDS.mkdir(exist_ok=True)
    counts = [c for _, c in days]

    bdate, bcount = s["busiest"]
    bd = dt.date.fromisoformat(bdate)
    busiest_caption = f"on {bd.day} {MONTHS[bd.month - 1]} {bd.year}" if bcount else "no contributions yet"
    bi = s["busiest_index"]
    ws = min(max(0, bi - 3), max(0, len(counts) - 7))
    cur, longest = s["current"], s["longest"]
    plural = lambda n: "s" if n != 1 else ""  # noqa: E731

    out = {
        "hero.svg": hero(),
        "tile-total.svg": tile("Contributions", s["total"], "in the last 12 months", T_TILES[0],
                               viz_sparkline(list(s["monthly"].values())), "monthly trend"),
        "tile-streak.svg": tile("Current streak", cur,
                                f"day{plural(cur)} in a row · longest {longest} day{plural(longest)}",
                                T_TILES[1], viz_days(counts[-14:]), "last 14 days"),
        "tile-best.svg": tile("Busiest day", bcount, busiest_caption, T_TILES[2],
                              viz_week(counts[ws:ws + 7], bi - ws), "week around the busiest day"),
        "graph.svg": graph(days, bi),
        "monthly.svg": monthly_chart(s["monthly"]),
    }
    for name, content in out.items():
        (CARDS / name).write_text(content, encoding="utf-8", newline="\n")
    mode = "static" if STATIC else "animated"
    print(f"Rendered {len(out)} {mode} cards for @{USER}{' (DEMO)' if DEMO else ''}: "
          f"total={s['total']} streak={cur} longest={longest} busiest={bcount}@{bdate}")


if __name__ == "__main__":
    main()
