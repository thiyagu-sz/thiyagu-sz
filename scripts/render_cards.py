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
shown through <img> are sandboxed (no JS, no external requests). So animation is CSS
@keyframes + SMIL inside each file, and fonts are embedded as base64 WOFF. To (re)build a font:

  pyftsubset Font.ttf --unicodes="U+0020-007E,U+00B7,U+2014,U+2019,U+2026" \
      --flavor=woff --layout-features='kern,liga' --no-hinting --desubroutinize \
      --output-file=fonts/display.woff

fonts/display.woff -> serif display face, fonts/body.woff -> body face. Both are optional;
missing files fall back to a system font stack.
"""
import base64
import datetime as dt
import json
import os
import random
import sys
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape as _xml_escape

# ------------------------------------------------------------------ settings
USER = os.environ.get("GH_USER") or "thiyagu-sz"
NAME = "Thiyagu"
TAGLINE = "AI Engineer · Full-Stack Developer · Founder"
SUBLINE = "RAG pipelines · agentic workflows · Next.js + FastAPI"

BG = "#0b1020"
PANEL = "#111833"
BORDER = "#1f2a4d"
TEXT = "#e6ebff"
MUTED = "#8a95b8"
ACCENT = "#4f8cff"
ACCENT_2 = "#9ad0ff"
HEAT = ["#172040", "#1d3b7a", "#2a5bc0", "#4f8cff", "#9ad0ff"]  # level 0..4

STATIC = os.environ.get("STATIC") == "1"
DEMO = os.environ.get("DEMO") == "1"

ROOT = Path(__file__).resolve().parent.parent
CARDS = ROOT / "cards"
DATA = ROOT / "data" / "contributions.json"
FONTS = ROOT / "fonts"

DISPLAY_FONT = "'Display', 'DM Serif Display', Georgia, 'Times New Roman', serif"
BODY_FONT = ("'Body', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', "
             "Helvetica, Arial, sans-serif")
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Page choreography (seconds). Every card starts playing when the page loads, so the
# offsets below make the page read top to bottom: hero -> tiles -> graph -> monthly.
T_TILES = (0.3, 0.45, 0.6)
T_GRAPH = 0.75
T_MONTHLY = 1.0


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

    busiest = max(days, key=lambda x: x[1]) if days else ("", 0)

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

    return {"total": total, "current": cur, "longest": longest,
            "busiest": busiest, "monthly": monthly}


# ------------------------------------------------------------------ svg helpers
def esc(s):
    return _xml_escape(str(s), {'"': "&quot;", "'": "&apos;"})


def font_face(family, fname):
    f = FONTS / fname
    if not f.exists():
        return ""
    b64 = base64.b64encode(f.read_bytes()).decode()
    return (f"@font-face{{font-family:'{family}';font-display:block;"
            f"src:url(data:font/woff;base64,{b64}) format('woff')}}\n")


KEYFRAMES = {
    "fadeUp": "@keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}",
    "fadeIn": "@keyframes fadeIn{from{opacity:0}to{opacity:1}}",
    "grow": "@keyframes grow{from{transform:scaleY(0)}to{transform:scaleY(1)}}",
    "pop": "@keyframes pop{0%{opacity:0;transform:scale(.3)}70%{opacity:1;transform:scale(1.12)}100%{opacity:1;transform:scale(1)}}",
    "blink": "@keyframes blink{0%,49%{opacity:1}50%,100%{opacity:0}}",
    "draw": "@keyframes draw{from{stroke-dashoffset:220}to{stroke-dashoffset:0}}",
}


def svg(width, height, body, css, label, display_font=False):
    """Wrap a card. Base styles never hide anything: every start state comes from the
    keyframes (animation-fill-mode: both), so STATIC=1 and reduced motion show the end state."""
    fonts = font_face("Display", "display.woff") if display_font else ""
    fonts += font_face("Body", "body.woff")
    anim = ""
    if not STATIC:
        used = "\n".join(k for name, k in KEYFRAMES.items() if name in css)
        anim = f"{used}\n{css.strip()}\n@media (prefers-reduced-motion: reduce){{*{{animation:none!important}}}}"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="t">
<title id="t">{esc(label)}</title>
<style>
{fonts}.d{{font-family:{DISPLAY_FONT}}}
.b{{font-family:{BODY_FONT}}}
{anim}
</style>
{body.strip()}
</svg>
"""


def panel(w, h, r=16):
    return (f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="{r}" '
            f'fill="{PANEL}" stroke="{BORDER}"/>')


def count_up(value, x, y, attrs, start, frames=18, dur=0.9):
    """Count a number up from 0. CSS can't change text, so stack one <text> per frame and
    flip visibility with SMIL <set>. The final frame is visible by default (hidden only while
    counting), so the real number shows even where SMIL never runs."""
    final = f"{value:,}"
    if STATIC or value == 0:
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


# ------------------------------------------------------------------ cards
def hero():
    w, h = 900, 220
    shine = "" if STATIC else (
        '<animateTransform attributeName="gradientTransform" type="translate" '
        'values="-700 0;700 0;700 0" keyTimes="0;0.6;1" dur="4s" begin="0.8s" repeatCount="indefinite"/>'
    )
    css = """
.name{animation:fadeUp .7s cubic-bezier(.2,.8,.2,1) .05s both}
.line{stroke-dasharray:220;animation:draw .7s ease-out .35s both}
.tag{animation:fadeUp .55s ease-out .5s both}
.sub{animation:fadeUp .55s ease-out .7s both}
.cur{animation:blink 1.05s steps(1) 1.2s infinite both}
.dot{transform-box:fill-box;transform-origin:center;animation:pop .45s ease-out both}
"""
    dots = "\n".join(
        f'<circle class="dot" style="animation-delay:{0.55 + i * 0.05:.2f}s" cx="{816 + (i % 3) * 18}" '
        f'cy="{38 + (i // 3) * 18}" r="4" fill="{HEAT[(i * 2 + i // 3) % 4 + 1]}"/>'
        for i in range(9)
    )
    body = f"""
<defs>
  <linearGradient id="shine" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="900" y2="0" gradientTransform="translate(-700 0)">
    <stop offset="0" stop-color="{TEXT}"/>
    <stop offset=".40" stop-color="{TEXT}"/>
    <stop offset=".50" stop-color="{ACCENT_2}"/>
    <stop offset=".54" stop-color="#ffffff"/>
    <stop offset=".60" stop-color="{TEXT}"/>
    <stop offset="1" stop-color="{TEXT}"/>
    {shine}
  </linearGradient>
  <radialGradient id="glow" cx="78%" cy="8%" r="75%">
    <stop offset="0" stop-color="{ACCENT}" stop-opacity=".30"/>
    <stop offset=".55" stop-color="{ACCENT}" stop-opacity=".06"/>
    <stop offset="1" stop-color="{ACCENT}" stop-opacity="0"/>
  </radialGradient>
</defs>
<rect width="{w}" height="{h}" rx="18" fill="{BG}"/>
<rect width="{w}" height="{h}" rx="18" fill="url(#glow)"/>
<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="18" fill="none" stroke="{BORDER}"/>
{dots}
<text class="d name" x="46" y="100" font-size="62" fill="url(#shine)">Hi, I&apos;m {esc(NAME)}</text>
<line class="line" x1="50" y1="122" x2="270" y2="122" stroke="{ACCENT}" stroke-width="3" stroke-linecap="round"/>
<text class="b tag" x="50" y="160" font-size="20" font-weight="600" fill="{TEXT}">{esc(TAGLINE)}</text>
<text class="b sub" x="50" y="189" font-size="15" fill="{MUTED}">{esc(SUBLINE)}<tspan class="cur" fill="{ACCENT}" dx="3">▍</tspan></text>
"""
    return svg(w, h, body, css, f"Hi, I'm {NAME} — {TAGLINE}. {SUBLINE}", display_font=True)


def tile(label, value, caption, delay):
    w, h = 290, 140
    css = f".tile{{animation:fadeUp .55s ease-out {delay}s both}}"
    body = f"""
<g class="tile">
{panel(w, h)}
<circle cx="{w - 28}" cy="34" r="4" fill="{ACCENT}"/>
<text class="b" x="24" y="38" font-size="12" font-weight="600" fill="{MUTED}" letter-spacing="1.6">{esc(label.upper())}</text>
{count_up(value, 24, 94, f'class="d" font-size="48" fill="{TEXT}"', start=delay + 0.2)}
<text class="b" x="24" y="120" font-size="13" fill="{ACCENT_2}">{esc(caption)}</text>
</g>"""
    return svg(w, h, body, css, f"{label}: {value:,} ({caption})", display_font=True)


def graph(days):
    cell, gap = 12, 3
    pitch = cell + gap
    top = 58
    first = dt.date.fromisoformat(days[0][0])
    pad = (first.weekday() + 1) % 7  # GitHub weeks start on Sunday
    grid = [None] * pad + list(days)
    cols = min(53, (len(grid) + 6) // 7)
    grid = grid[-cols * 7:] if len(grid) > cols * 7 else grid
    w = 900
    left = (w - (cols * pitch - gap)) // 2 + 12
    h = top + 7 * pitch - gap + 46

    nonzero = sorted(c for _, c in days if c)

    def level(c):  # quartiles of non-zero days, like GitHub
        if c == 0 or not nonzero:
            return 0
        q = [nonzero[int(len(nonzero) * p)] for p in (0.25, 0.5, 0.75)]
        return 1 + sum(c > t for t in q)

    css = f"""
.lbl{{animation:fadeIn .5s ease-out {T_GRAPH - 0.1:.2f}s both}}
.c{{transform-box:fill-box;transform-origin:center;animation:pop .32s ease-out both}}
"""
    rects, labels, last_month, last_x = [], [], None, -99
    for i, d in enumerate(grid):
        col, row = divmod(i, 7)
        if d is None:
            continue
        date, c = d
        x, y = left + col * pitch, top + row * pitch
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

    # legend: Less [] [] [] [] [] More  (bottom right)
    ly = top + 7 * pitch - gap + 18
    right = left + cols * pitch - gap
    lx = right - 5 * pitch + gap - 34
    legend = [f'<text class="b lbl" x="{lx - 6}" y="{ly + 10}" font-size="11" fill="{MUTED}" text-anchor="end">Less</text>']
    for k in range(5):
        legend.append(f'<rect class="lbl" x="{lx + k * pitch}" y="{ly}" width="{cell}" height="{cell}" rx="3" fill="{HEAT[k]}"/>')
    legend.append(f'<text class="b lbl" x="{lx + 5 * pitch + 3}" y="{ly + 10}" font-size="11" fill="{MUTED}">More</text>')

    total = sum(c for _, c in days)
    body = f"""
{panel(w, h)}
<text class="b lbl" x="{left - 30}" y="30" font-size="15" font-weight="600" fill="{TEXT}">{total:,} contributions in the last year</text>
{chr(10).join(labels)}
{chr(10).join(legend)}
{chr(10).join(rects)}
"""
    return svg(w, h, body, css, f"{total:,} contributions in the last year")


def monthly_chart(monthly):
    w, h = 900, 220
    left, right, bottom, top = 40, 30, 176, 62
    n = len(monthly)
    slot = (w - left - right) / max(n, 1)
    bw = slot * 0.56
    mx = max(monthly.values(), default=0) or 1
    css = f"""
.lbl{{animation:fadeIn .5s ease-out {T_MONTHLY - 0.15:.2f}s both}}
.bar{{transform-box:fill-box;transform-origin:bottom;animation:grow .5s cubic-bezier(.2,.8,.2,1) both}}
.v{{animation:fadeIn .35s ease-out both}}
"""
    bars = []
    for i, (m, v) in enumerate(monthly.items()):
        bh = max(3, (bottom - top) * v / mx)
        x = left + i * slot + (slot - bw) / 2
        y = bottom - bh
        delay = T_MONTHLY + i * 0.07
        cx = x + bw / 2
        bars.append(
            f'<rect class="bar" style="animation-delay:{delay:.2f}s" x="{x:.1f}" y="{y:.1f}" '
            f'width="{bw:.1f}" height="{bh:.1f}" rx="5" fill="url(#bar)"><title>{v:,} in {MONTHS[int(m[5:]) - 1]} {m[:4]}</title></rect>\n'
            f'<text class="b v" style="animation-delay:{delay + 0.3:.2f}s" x="{cx:.1f}" y="{y - 7:.1f}" '
            f'font-size="12" font-weight="600" fill="{ACCENT_2}" text-anchor="middle">{v:,}</text>\n'
            f'<text class="b lbl" x="{cx:.1f}" y="{bottom + 22}" font-size="11" fill="{MUTED}" '
            f'text-anchor="middle">{MONTHS[int(m[5:]) - 1]}</text>'
        )
    body = f"""
<defs><linearGradient id="bar" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="{ACCENT_2}"/><stop offset="1" stop-color="{ACCENT}"/>
</linearGradient></defs>
{panel(w, h)}
<text class="b lbl" x="{left}" y="34" font-size="15" font-weight="600" fill="{TEXT}">Contributions per month</text>
<line x1="{left}" y1="{bottom + 0.5}" x2="{w - right}" y2="{bottom + 0.5}" stroke="{BORDER}"/>
{chr(10).join(bars)}
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

    bdate, bcount = s["busiest"]
    bd = dt.date.fromisoformat(bdate)
    busiest_caption = f"on {bd.day} {MONTHS[bd.month - 1]} {bd.year}" if bcount else "no contributions yet"
    longest = s["longest"]
    out = {
        "hero.svg": hero(),
        "tile-total.svg": tile("Contributions", s["total"], "in the last 12 months", T_TILES[0]),
        "tile-streak.svg": tile("Current streak", s["current"],
                                f"day{'s' if s['current'] != 1 else ''} in a row · longest {longest} day{'s' if longest != 1 else ''}", T_TILES[1]),
        "tile-best.svg": tile("Busiest day", bcount, busiest_caption, T_TILES[2]),
        "graph.svg": graph(days),
        "monthly.svg": monthly_chart(s["monthly"]),
    }
    for name, content in out.items():
        (CARDS / name).write_text(content, encoding="utf-8", newline="\n")
    mode = "static" if STATIC else "animated"
    print(f"Rendered {len(out)} {mode} cards for @{USER}{' (DEMO)' if DEMO else ''}: "
          f"total={s['total']} streak={s['current']} longest={longest} busiest={bcount}@{bdate}")


if __name__ == "__main__":
    main()
