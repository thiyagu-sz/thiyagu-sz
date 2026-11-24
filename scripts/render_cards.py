#!/usr/bin/env python3
"""
Render animated SVG cards for a GitHub profile README.

  python scripts/render_cards.py            # animated cards (fetches data if GITHUB_TOKEN is set)
  STATIC=1 python scripts/render_cards.py   # end-state only (for screenshots / previews)
  DEMO=1 python scripts/render_cards.py     # fake data, no network

Outputs: cards/hero.svg, cards/tile-*.svg, cards/graph.svg, cards/monthly.svg
"""
import base64
import datetime as dt
import html
import json
import os
import random
import urllib.request
from collections import OrderedDict
from pathlib import Path

# ---------------------------------------------------------------- settings
USER = os.environ.get("GH_USER", "thiyagu-sz")
NAME = os.environ.get("DISPLAY_NAME", "Thiyagu")
TAGLINE = "AI Engineer  ·  Full-Stack Developer  ·  Founder"
SUBLINE = "RAG pipelines · agentic workflows · Next.js + FastAPI"

BG = "#0b1020"
PANEL = "#111833"
BORDER = "#1f2a4d"
TEXT = "#e6ebff"
MUTED = "#8a95b8"
ACCENT = "#4f8cff"
ACCENT_2 = "#9ad0ff"
HEAT = ["#16203f", "#1d3b7a", "#2a5bc0", "#4f8cff", "#9ad0ff"]  # 0..4

STATIC = os.environ.get("STATIC") == "1"
DEMO = os.environ.get("DEMO") == "1"

ROOT = Path(__file__).resolve().parent.parent
CARDS = ROOT / "cards"
DATA = ROOT / "data" / "contributions.json"
FONTS = ROOT / "fonts"

DISPLAY_FONT = "'Display', Georgia, 'Times New Roman', serif"
BODY_FONT = "'Body', -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"


# ---------------------------------------------------------------- data
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


def fetch_days():
    """Return [(date, count), ...] for the last ~year, oldest first."""
    token = os.environ.get("GITHUB_TOKEN")
    if DEMO or not token:
        if DATA.exists() and not DEMO:
            return [tuple(d) for d in json.loads(DATA.read_text())["days"]]
        return demo_days()

    body = json.dumps({"query": QUERY, "variables": {"login": USER}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    if "errors" in payload:
        raise SystemExit(f"GraphQL error: {payload['errors']}")
    weeks = payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    days = [(d["date"], d["contributionCount"]) for w in weeks for d in w["contributionDays"]]

    DATA.parent.mkdir(exist_ok=True)
    DATA.write_text(json.dumps({"user": USER, "updated": dt.date.today().isoformat(), "days": days}))
    return days


def demo_days():
    rng = random.Random(7)
    today = dt.date.today()
    start = today - dt.timedelta(days=364 + (today.weekday() + 1) % 7)
    out, d = [], start
    while d <= today:
        busy = rng.random() < 0.72
        out.append((d.isoformat(), rng.choice([1, 2, 3, 4, 6, 9, 14]) if busy else 0))
        d += dt.timedelta(days=1)
    return out


def stats(days):
    counts = [c for _, c in days]
    total = sum(counts)

    # current streak: walk back from today (today may still be 0)
    cur, i = 0, len(counts) - 1
    if i >= 0 and counts[i] == 0:
        i -= 1
    while i >= 0 and counts[i] > 0:
        cur += 1
        i -= 1

    best = run = 0
    for c in counts:
        run = run + 1 if c else 0
        best = max(best, run)

    busiest = max(days, key=lambda x: x[1]) if days else ("-", 0)

    monthly = OrderedDict()
    for date, c in days:
        key = date[:7]
        monthly[key] = monthly.get(key, 0) + c
    monthly = OrderedDict(list(monthly.items())[-12:])

    return {"total": total, "current": cur, "best": best, "busiest": busiest, "monthly": monthly}


# ---------------------------------------------------------------- svg helpers
def esc(s):
    return html.escape(str(s), quote=True)


def font_css():
    """Embed fonts/display.woff and fonts/body.woff as base64 if present.
    GitHub blocks external requests from SVGs, so Google Fonts URLs won't load."""
    css = []
    for family, fname in (("Display", "display.woff"), ("Body", "body.woff")):
        f = FONTS / fname
        if f.exists():
            b64 = base64.b64encode(f.read_bytes()).decode()
            css.append(
                f"@font-face{{font-family:'{family}';"
                f"src:url(data:font/woff;base64,{b64}) format('woff');font-display:block}}"
            )
    return "".join(css)


BASE_KEYFRAMES = """
@keyframes fadeUp { from { opacity:0; transform:translateY(10px) } to { opacity:1; transform:none } }
@keyframes fadeIn { from { opacity:0 } to { opacity:1 } }
@keyframes grow   { from { transform:scaleY(0) } to { transform:scaleY(1) } }
@keyframes pop    { from { opacity:0; transform:scale(.4) } to { opacity:1; transform:none } }
@keyframes blink  { 50% { opacity:0 } }
@keyframes draw   { to { stroke-dashoffset:0 } }
"""


def svg(width, height, body, css, label):
    """Wrap content. Animations only exist in non-static mode; elements are fully
    visible without them, so STATIC=1 and prefers-reduced-motion show the end state."""
    anim = "" if STATIC else BASE_KEYFRAMES + css
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(label)}">
<title>{esc(label)}</title>
<style>
{font_css()}
.d {{ font-family:{DISPLAY_FONT}; }}
.b {{ font-family:{BODY_FONT}; }}
{anim}
@media (prefers-reduced-motion: reduce) {{ * {{ animation:none !important; }} }}
</style>
{body}
</svg>
"""


def panel(w, h, r=16):
    return (f'<rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="{r}" '
            f'fill="{PANEL}" stroke="{BORDER}"/>')


def count_up(value, x, y, cls, attrs, start=0.6, frames=18, dur=0.9):
    """SMIL count-up: CSS can't change text, so show one <text> per frame with <set>."""
    if STATIC or value == 0:
        return f'<text x="{x}" y="{y}" class="{cls}" {attrs}>{value:,}</text>'
    out, step = [], dur / frames
    for i in range(1, frames + 1):
        v = round(value * (1 - (1 - i / frames) ** 3))  # ease-out
        begin = start + (i - 1) * step
        last = i == frames
        timing = f'begin="{begin:.3f}s" fill="freeze"' if last else f'begin="{begin:.3f}s" dur="{step:.3f}s"'
        out.append(
            f'<text x="{x}" y="{y}" class="{cls}" {attrs} visibility="hidden">{v:,}'
            f'<set attributeName="visibility" to="visible" {timing}/></text>'
        )
    return "".join(out)


# ---------------------------------------------------------------- cards
def hero():
    w, h = 900, 220
    shine = "" if STATIC else (
        '<animateTransform attributeName="gradientTransform" type="translate" '
        'from="-900 0" to="900 0" dur="3.2s" begin="0.4s" repeatCount="indefinite"/>'
    )
    css = """
.name { animation: fadeUp .7s ease-out .1s both; }
.tag  { animation: fadeUp .6s ease-out .45s both; }
.sub  { animation: fadeUp .6s ease-out .7s both; }
.line { stroke-dasharray:240; stroke-dashoffset:240; animation: draw .8s ease-out .35s forwards; }
.cur  { animation: blink 1s steps(1) infinite; }
.dot  { animation: pop .4s ease-out both; transform-box:fill-box; transform-origin:center; }
"""
    dots = "".join(
        f'<circle class="dot" style="animation-delay:{0.8 + i*0.06:.2f}s" cx="{820 + (i%3)*16}" '
        f'cy="{40 + (i//3)*16}" r="3" fill="{HEAT[1 + i % 4]}"/>'
        for i in range(9)
    )
    body = f"""
<defs>
  <linearGradient id="shine" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="900" y2="0">
    <stop offset="0" stop-color="{TEXT}"/>
    <stop offset=".42" stop-color="{TEXT}"/>
    <stop offset=".5" stop-color="{ACCENT_2}"/>
    <stop offset=".58" stop-color="{TEXT}"/>
    <stop offset="1" stop-color="{TEXT}"/>
    {shine}
  </linearGradient>
  <radialGradient id="glow" cx="85%" cy="0%" r="70%">
    <stop offset="0" stop-color="{ACCENT}" stop-opacity=".28"/>
    <stop offset="1" stop-color="{ACCENT}" stop-opacity="0"/>
  </radialGradient>
</defs>
<rect width="{w}" height="{h}" rx="18" fill="{BG}"/>
<rect width="{w}" height="{h}" rx="18" fill="url(#glow)"/>
<rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="18" fill="none" stroke="{BORDER}"/>
{dots}
<text class="d name" x="48" y="104" font-size="64" fill="{TEXT if STATIC else 'url(#shine)'}">Hi, I'm {esc(NAME)}</text>
<line class="line" x1="50" y1="126" x2="290" y2="126" stroke="{ACCENT}" stroke-width="3" stroke-linecap="round"/>
<text class="b tag" x="50" y="160" font-size="20" fill="{TEXT}">{esc(TAGLINE)}</text>
<text class="b sub" x="50" y="190" font-size="15" fill="{MUTED}">{esc(SUBLINE)}<tspan class="cur" fill="{ACCENT}"> ▍</tspan></text>
"""
    return svg(w, h, body, css, f"{NAME} — {TAGLINE}")


def tile(label, value, unit, delay):
    w, h = 290, 140
    css = f".tile {{ animation: fadeUp .6s ease-out {delay}s both; }}"
    body = f"""
<g class="tile">
{panel(w, h)}
<text class="b" x="24" y="40" font-size="14" fill="{MUTED}" letter-spacing="1.5">{esc(label.upper())}</text>
{count_up(value, 24, 96, "d", f'font-size="48" fill="{TEXT}"', start=delay + 0.2)}
<text class="b" x="24" y="122" font-size="13" fill="{ACCENT_2}">{esc(unit)}</text>
</g>"""
    return svg(w, h, body, css, f"{label}: {value} {unit}")


def graph(days):
    cell, gap = 12, 3
    left, top = 40, 56
    # pad to start on Sunday
    first = dt.date.fromisoformat(days[0][0])
    pad = (first.weekday() + 1) % 7
    grid = [None] * pad + days
    cols = (len(grid) + 6) // 7
    w = 900
    left = (w - cols * (cell + gap) + gap) // 2 + 8
    h = top + 7 * (cell + gap) + 34

    mx = max((c for _, c in days), default=0) or 1

    def level(c):
        if c == 0:
            return 0
        return min(4, 1 + int(3 * c / mx + 0.5))

    css = """
.title { animation: fadeIn .5s ease-out .2s both; }
.c { animation: pop .35s ease-out both; transform-box:fill-box; transform-origin:center; }
"""
    rects, months, last_month, last_x = [], [], None, -99
    for i, d in enumerate(grid):
        col, row = divmod(i, 7)
        if d is None:
            continue
        date, c = d
        x, y = left + col * (cell + gap), top + row * (cell + gap)
        delay = 0.4 + col * 0.018
        rects.append(
            f'<rect class="c" style="animation-delay:{delay:.3f}s" x="{x}" y="{y}" '
            f'width="{cell}" height="{cell}" rx="3" fill="{HEAT[level(c)]}">'
            f'<title>{c} on {date}</title></rect>'
        )
        m = date[:7]
        if row == 0 and m != last_month and (not months or x - last_x > 28):
            last_month, last_x = m, x
            months.append(f'<text class="b title" x="{x}" y="{top - 10}" font-size="11" fill="{MUTED}">'
                          f'{dt.date.fromisoformat(date).strftime("%b")}</text>')
    for r, lbl in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        months.append(f'<text class="b title" x="{left - 30}" y="{top + r*(cell+gap) + 10}" font-size="10" fill="{MUTED}">{lbl}</text>')

    total = sum(c for _, c in days)
    body = f"""
{panel(w, h)}
<text class="b title" x="{left}" y="28" font-size="14" fill="{TEXT}">{total:,} contributions in the last year</text>
{''.join(months)}
{''.join(rects)}
"""
    return svg(w, h, body, css, f"{total} contributions in the last year")


def monthly_chart(monthly):
    w, h = 900, 220
    left, bottom, top = 40, 180, 50
    n = len(monthly)
    slot = (w - left - 30) / max(n, 1)
    bw = slot * 0.56
    mx = max(monthly.values(), default=0) or 1
    css = """
.title { animation: fadeIn .5s ease-out .2s both; }
.bar { transform-box:fill-box; transform-origin:bottom; animation: grow .7s cubic-bezier(.2,.8,.2,1) both; }
.v   { animation: fadeIn .4s ease-out both; }
"""
    bars = []
    for i, (m, v) in enumerate(monthly.items()):
        bh = max(2, (bottom - top) * v / mx)
        x = left + i * slot + (slot - bw) / 2
        y = bottom - bh
        delay = 0.4 + i * 0.07
        label = dt.date.fromisoformat(m + "-01").strftime("%b")
        bars.append(
            f'<rect class="bar" style="animation-delay:{delay:.2f}s" x="{x:.1f}" y="{y:.1f}" '
            f'width="{bw:.1f}" height="{bh:.1f}" rx="5" fill="url(#bar)"/>'
            f'<text class="b v" style="animation-delay:{delay + .5:.2f}s" x="{x + bw/2:.1f}" y="{y - 7:.1f}" '
            f'font-size="11" fill="{ACCENT_2}" text-anchor="middle">{v}</text>'
            f'<text class="b" x="{x + bw/2:.1f}" y="{bottom + 20}" font-size="11" fill="{MUTED}" text-anchor="middle">{label}</text>'
        )
    body = f"""
<defs><linearGradient id="bar" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="{ACCENT_2}"/><stop offset="1" stop-color="{ACCENT}"/>
</linearGradient></defs>
{panel(w, h)}
<text class="b title" x="{left}" y="30" font-size="14" fill="{TEXT}">Contributions per month</text>
<line x1="{left}" y1="{bottom}" x2="{w-30}" y2="{bottom}" stroke="{BORDER}"/>
{''.join(bars)}
"""
    return svg(w, h, body, css, "Contributions per month")


# ---------------------------------------------------------------- main
def main():
    days = fetch_days()
    s = stats(days)
    CARDS.mkdir(exist_ok=True)
    busiest_date = dt.date.fromisoformat(s["busiest"][0]).strftime("%d %b %Y") if days else "-"
    out = {
        "hero.svg": hero(),
        "tile-total.svg": tile("Contributions", s["total"], "in the last 12 months", 0.3),
        "tile-streak.svg": tile("Current streak", s["current"], "days in a row", 0.45),
        "tile-best.svg": tile("Busiest day", s["busiest"][1], f"on {busiest_date}", 0.6),
        "graph.svg": graph(days),
        "monthly.svg": monthly_chart(s["monthly"]),
    }
    for name, content in out.items():
        (CARDS / name).write_text(content, encoding="utf-8")
    print(f"Rendered {len(out)} cards for @{USER}: total={s['total']} "
          f"streak={s['current']} longest={s['best']}")


if __name__ == "__main__":
    main()
