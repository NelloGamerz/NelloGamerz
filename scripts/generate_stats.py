#!/usr/bin/env python3
"""Builds animated, self-hosted stat cards (SVG, SMIL animations) for a GitHub profile README.

Data sources
  - github.com contributions calendar (public HTML, no token needed): contributions, streaks, weekly activity
  - GitHub REST API (GITHUB_TOKEN from the workflow): repos, stars, followers, PRs, languages

Usage:  GH_USER=NelloGamerz GITHUB_TOKEN=... python scripts/generate_stats.py dist
Only the standard library is used.
"""
import datetime as dt
import html
import json
import math
import os
import re
import sys
import urllib.request
from collections import defaultdict

USER = os.environ.get("GH_USER", "NelloGamerz")
TOKEN = os.environ.get("GITHUB_TOKEN")
OUT = sys.argv[1] if len(sys.argv) > 1 else "dist"

CYAN, VIOLET, PINK = "#22d3ee", "#8b5cf6", "#f64f59"
SANS = "'Segoe UI', 'Helvetica Neue', Arial, sans-serif"
MONO = "'Fira Code', 'SF Mono', Consolas, 'Courier New', monospace"


# ───────────────────────── data ─────────────────────────
def http(url, headers=None):
    h = {"User-Agent": "profile-readme-stats"}
    h.update(headers or {})
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def api(path):
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    return json.loads(http("https://api.github.com" + path, h))


def rest_data():
    user = api(f"/users/{USER}")
    repos = []
    for page in range(1, 4):
        chunk = api(f"/users/{USER}/repos?per_page=100&type=owner&page={page}")
        repos += chunk
        if len(chunk) < 100:
            break
    own = [r for r in repos if not r.get("fork")]
    langs = defaultdict(int)
    for r in own[:80]:
        try:
            for k, v in api(f"/repos/{USER}/{r['name']}/languages").items():
                langs[k] += v
        except Exception:
            continue
    try:
        prs = api(f"/search/issues?q=author:{USER}+type:pr&per_page=1")["total_count"]
    except Exception:
        prs = None
    return {
        "created": user["created_at"],
        "repos": user["public_repos"],
        "followers": user["followers"],
        "stars": sum(r.get("stargazers_count", 0) for r in own),
        "prs": prs,
        "langs": dict(langs),
        "own": len(own),
    }


DAY_RE = re.compile(r'<td\b[^>]*\bdata-date="(\d{4}-\d{2}-\d{2})"[^>]*>', re.S)
ID_RE = re.compile(r'\bid="([^"]+)"')
TIP_RE = re.compile(r'<tool-tip\b[^>]*\bfor="([^"]+)"[^>]*>\s*([^<]*?)\s*</tool-tip>', re.S)


def fetch_calendar(start_year, today):
    days = {}
    for y in range(start_year, today.year + 1):
        end = today.isoformat() if y == today.year else f"{y}-12-31"
        body = http(f"https://github.com/users/{USER}/contributions?from={y}-01-01&to={end}", {"Accept": "text/html"})
        tips = {m.group(1): m.group(2) for m in TIP_RE.finditer(body)}
        for m in DAY_RE.finditer(body):
            idm = ID_RE.search(m.group(0))
            n = 0
            if idm and idm.group(1) in tips:
                t = re.match(r"(\d+)\s+contribution", tips[idm.group(1)])
                n = int(t.group(1)) if t else 0
            days[dt.date.fromisoformat(m.group(1))] = n
    return days


def streaks(days, today):
    first = next((d for d in sorted(days) if days[d] > 0 and d <= today), None)
    if not first:
        return 0, None, (0, None, None), (0, None, None)
    total = sum(v for d, v in days.items() if d <= today)
    best, cur_len, cur_start, d = (0, None, None), 0, None, first
    while d <= today:
        if days.get(d, 0) > 0:
            if cur_len == 0:
                cur_start = d
            cur_len += 1
            if cur_len > best[0]:
                best = (cur_len, cur_start, d)
        else:
            cur_len = 0
        d += dt.timedelta(days=1)
    d = today if days.get(today, 0) > 0 else today - dt.timedelta(days=1)
    end, run = d, 0
    while days.get(d, 0) > 0:
        run += 1
        d -= dt.timedelta(days=1)
    cur = (run, d + dt.timedelta(days=1), end) if run else (0, None, None)
    return total, first, cur, best


def weekly(days, today):
    vals, starts = [], []
    for w in range(52):
        end = today - dt.timedelta(days=7 * (51 - w))
        vals.append(sum(days.get(end - dt.timedelta(days=k), 0) for k in range(7)))
        starts.append(end - dt.timedelta(days=6))
    return vals, starts


# ───────────────────────── svg helpers ─────────────────────────
def esc(s):
    return html.escape(str(s), quote=True)


def fmt(n):
    return "–" if n is None else f"{n:,}"


def short_date(d):
    return f"{d:%b} {d.day}" if d else ""


def rng(t):
    return f"{short_date(t[1])} – {short_date(t[2])}" if t[0] else "no active streak"


def mix(t):
    def h(c):
        return [int(c[i:i + 2], 16) for i in (1, 3, 5)]
    a, b = (h(CYAN), h(VIOLET)) if t < .5 else (h(VIOLET), h(PINK))
    u = t * 2 if t < .5 else (t - .5) * 2
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * u) for i in range(3))


def frame(W, H, body, title, chart=None):
    cx0, cx1 = (chart or (0, W))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{esc(title)}">
<title>{esc(title)}</title>
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#070b16"/><stop offset="1" stop-color="#0f172a"/></linearGradient>
  <pattern id="dots" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r=".9" fill="#1e293b"/></pattern>
  <linearGradient id="scan" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{CYAN}" stop-opacity="0"/><stop offset=".85" stop-color="{CYAN}" stop-opacity=".12"/><stop offset="1" stop-color="{CYAN}" stop-opacity=".4"/></linearGradient>
  <linearGradient id="spectrum" gradientUnits="userSpaceOnUse" x1="{cx0}" y1="0" x2="{cx1}" y2="0"><stop offset="0" stop-color="{CYAN}"/><stop offset=".5" stop-color="{VIOLET}"/><stop offset="1" stop-color="{PINK}"/></linearGradient>
  <linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{VIOLET}" stop-opacity=".45"/><stop offset="1" stop-color="{VIOLET}" stop-opacity="0"/></linearGradient>
  <filter id="glow" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="2.2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  <clipPath id="round"><rect width="{W}" height="{H}" rx="18"/></clipPath>
</defs>
<g clip-path="url(#round)">
<rect width="{W}" height="{H}" fill="url(#bg)"/>
<rect width="{W}" height="{H}" fill="url(#dots)"/>
<rect x="-160" y="0" width="160" height="{H}" fill="url(#scan)"><animateTransform attributeName="transform" type="translate" from="0 0" to="{W + 160} 0" dur="7s" repeatCount="indefinite"/></rect>
{body}
</g>
<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="18" fill="none" stroke="#1e293b"/>
</svg>'''


def label(x, y, txt, size=15, fill="#94a3b8", mono=True, anchor="start", weight=400):
    return (f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-family="{MONO if mono else SANS}" '
            f'font-size="{size}" font-weight="{weight}" fill="{fill}">{esc(txt)}</text>')


def header(title, right, today):
    return label(40, 44, title, 16, CYAN) + label(1160, 44, right, 13, "#64748b", anchor="end")


# ───────────────────────── cards ─────────────────────────
def stats_card(rest, total, first, cur, best, today):
    W, H = 1200, 250
    items = [
        (fmt(total), "contributions", f"since {first:%b %Y}" if first else ""),
        (fmt(cur[0]), "current streak", rng(cur)),
        (fmt(best[0]), "longest streak", rng(best)),
        (fmt(rest["repos"]), "public repos", f"{rest['own']} original"),
        (fmt(rest["stars"]), "stars earned", "on original repos"),
        (fmt(rest["prs"]), "pull requests", "opened, all time"),
        (fmt(rest["followers"]), "followers", ""),
    ]
    cy, step, x0 = 128, 160, 120
    out = [header("// training metrics", f"updated {today.isoformat()}", today)]
    for i in range(len(items) - 1):
        xa, xb = x0 + step * i + 52, x0 + step * (i + 1) - 52
        out.append(f'<line x1="{xa}" y1="{cy}" x2="{xb}" y2="{cy}" stroke="#1e293b" stroke-width="1.5"/>'
                   f'<line x1="{xa}" y1="{cy}" x2="{xb}" y2="{cy}" stroke="{mix(i / 6)}" stroke-width="2" stroke-linecap="round" stroke-dasharray="2 8" filter="url(#glow)">'
                   f'<animate attributeName="stroke-dashoffset" from="10" to="0" dur="1.2s" repeatCount="indefinite"/></line>')
    for i, (val, lab, sub) in enumerate(items):
        cx, c = x0 + step * i, mix(i / 6)
        size = 28 if len(val) <= 4 else 22
        sign, dur = (1 if i % 2 == 0 else -1), 5 + (i % 3)
        out.append(
            f'<circle cx="{cx}" cy="{cy}" r="46" fill="#0b1220" stroke="#1e293b" stroke-width="3"/>'
            f'<circle cx="{cx}" cy="{cy}" r="46" fill="none" stroke="{c}" stroke-width="1.5" stroke-opacity=".55"/>'
            f'<circle cx="{cx}" cy="{cy}" r="46" fill="none" stroke="{c}" stroke-width="1.5">'
            f'<animate attributeName="r" values="46;64" dur="3s" begin="{i * .4:.1f}s" repeatCount="indefinite"/>'
            f'<animate attributeName="stroke-opacity" values=".6;0" dur="3s" begin="{i * .4:.1f}s" repeatCount="indefinite"/></circle>'
            f'<g><animateTransform attributeName="transform" type="rotate" from="0 {cx} {cy}" to="{sign * 360} {cx} {cy}" dur="{dur}s" repeatCount="indefinite"/>'
            f'<circle cx="{cx}" cy="{cy - 46}" r="3.6" fill="{c}" filter="url(#glow)"/></g>'
            f'<text x="{cx}" y="{cy + size * .35:.0f}" text-anchor="middle" font-family="{SANS}" font-size="{size}" font-weight="800" fill="#f8fafc">{esc(val)}</text>'
            + label(cx, cy + 84, lab, 14, "#cbd5e1", mono=False, anchor="middle", weight=600)
            + label(cx, cy + 104, sub, 11, "#64748b", anchor="middle"))
    return frame(W, H, "\n".join(out), f"GitHub metrics for {USER}")


def languages_card(rest, today):
    langs = sorted(rest["langs"].items(), key=lambda kv: -kv[1])
    total = sum(v for _, v in langs) or 1
    top = langs[:6]
    n = max(len(top), 1)
    W, H = 1200, 84 + n * 40 + 16
    X0, TW = 200, 820
    kb = total / 1024
    size = f"{kb / 1024:.1f} MB" if kb >= 1024 else f"{kb:.0f} KB"
    out = [header("// language weights", f"{size} across {rest['own']} original repos", today)]
    if not top:
        out.append(label(40, 100, "no language data yet", 14))
    for i, (name, b) in enumerate(top):
        pct = b / total * 100
        w = max(TW * b / top[0][1], 6)  # longest bar = top language; % label is the true share
        y = 88 + i * 40
        ends = f"{X0};{X0 + w:.0f};{X0 + w:.0f};{X0}"
        anim = f'keyTimes="0;.15;.9;1" dur="9s" begin="{i * .15:.2f}s" repeatCount="indefinite" calcMode="spline" keySplines=".2 .8 .2 1;0 0 1 1;.6 0 .8 .2"'
        out.append(
            label(40, y + 5, name, 15, "#e2e8f0", mono=False, weight=600)
            + f'<rect x="{X0}" y="{y - 5}" width="{TW}" height="10" rx="5" fill="#111a2e"/>'
            + f'<line x1="{X0}" y1="{y}" x2="{X0 + TW}" y2="{y}" stroke="#334155" stroke-width="1" stroke-dasharray="2 10"><animate attributeName="stroke-dashoffset" from="12" to="0" dur="2s" repeatCount="indefinite"/></line>'
            + f'<rect x="{X0}" y="{y - 5}" width="{w:.0f}" height="10" rx="5" fill="url(#spectrum)" filter="url(#glow)"><animate attributeName="width" values="0;{w:.0f};{w:.0f};0" {anim}/></rect>'
            + f'<circle cx="{X0 + w:.0f}" cy="{y}" r="4" fill="#f8fafc" filter="url(#glow)"><animate attributeName="cx" values="{ends}" {anim}/><animate attributeName="r" values="3;6;3" dur="1.6s" repeatCount="indefinite"/></circle>'
            + label(X0 + TW + 24, y + 5, f"{pct:.1f}%", 14, "#94a3b8"))
    return frame(W, H, "\n".join(out), f"Language weights for {USER}", chart=(X0, X0 + TW))


def monotone(pts):
    n = len(pts)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    dx = [xs[i + 1] - xs[i] for i in range(n - 1)]
    m = [(ys[i + 1] - ys[i]) / dx[i] for i in range(n - 1)]
    t = [m[0]] + [0 if m[i - 1] * m[i] <= 0 else (m[i - 1] + m[i]) / 2 for i in range(1, n - 1)] + [m[-1]]
    for i in range(n - 1):
        if m[i] == 0:
            t[i] = t[i + 1] = 0
        else:
            a, b = t[i] / m[i], t[i + 1] / m[i]
            s = a * a + b * b
            if s > 9:
                k = 3 / math.sqrt(s)
                t[i], t[i + 1] = k * a * m[i], k * b * m[i]
    d = f"M{xs[0]:.1f},{ys[0]:.1f}"
    for i in range(n - 1):
        h = dx[i] / 3
        d += f" C{xs[i] + h:.1f},{ys[i] + t[i] * h:.1f} {xs[i + 1] - h:.1f},{ys[i + 1] - t[i + 1] * h:.1f} {xs[i + 1]:.1f},{ys[i + 1]:.1f}"
    return d


def activity_card(days, today):
    vals, starts = weekly(days, today)
    W, H = 1200, 300
    X0, X1, YT, YB = 80, 1130, 100, 250
    vmax = max(max(vals), 1)
    pts = [(X0 + (X1 - X0) * i / 51, YB - (YB - YT) * v / vmax) for i, v in enumerate(vals)]
    line = monotone(pts)
    area = f"{line} L{X1},{YB} L{X0},{YB} Z"
    out = [header("// contribution signal", f"{sum(vals):,} contributions · last 52 weeks", today)]
    for frac in (0, .5, 1):
        y = YB - (YB - YT) * frac
        out.append(f'<line x1="{X0}" y1="{y:.0f}" x2="{X1}" y2="{y:.0f}" stroke="#1e293b" stroke-width="1" stroke-dasharray="3 6"/>'
                   + label(X0 - 12, y + 4, f"{round(vmax * frac)}", 11, "#64748b", anchor="end"))
    prev = None
    for i, s in enumerate(starts):
        if prev is not None and s.month != prev and i < 50:
            out.append(label(pts[i][0], YB + 26, f"{s:%b}", 11, "#64748b", anchor="middle"))
        prev = s.month
    ipk = vals.index(max(vals))
    px, py = pts[ipk]
    cyc = 'dur="10s" repeatCount="indefinite"'
    out.append(
        f'<g><animate attributeName="opacity" values="1;1;0;0" keyTimes="0;.88;.97;1" {cyc}/>'
        f'<path d="{area}" fill="url(#area)"><animate attributeName="fill-opacity" values="0;1;1" keyTimes="0;.35;1" {cyc}/></path>'
        f'<path d="{line}" fill="none" stroke="url(#spectrum)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" pathLength="1" stroke-dasharray="1 1" filter="url(#glow)">'
        f'<animate attributeName="stroke-dashoffset" values="1;0;0" keyTimes="0;.3;1" {cyc}/></path>'
        f'<circle r="5.5" fill="#f8fafc" filter="url(#glow)"><animateMotion path="{line}" keyPoints="0;1;1" keyTimes="0;.3;1" calcMode="linear" {cyc}/>'
        f'<animate attributeName="r" values="4;7;4" dur="1.6s" repeatCount="indefinite"/></circle></g>'
        f'<circle cx="{px:.0f}" cy="{py:.0f}" r="4" fill="{PINK}" filter="url(#glow)"><animate attributeName="r" values="3;7;3" dur="2.4s" begin="1s" repeatCount="indefinite"/></circle>'
        + label(f"{px:.0f}", f"{py - 16:.0f}", f"peak {vals[ipk]}", 12, PINK, anchor="middle"))
    return frame(W, H, "\n".join(out), f"Contribution activity for {USER}", chart=(X0, X1))


# ───────────────────────── main ─────────────────────────
def main(rest=None, days=None):
    today = dt.datetime.now(dt.timezone.utc).date()
    rest = rest or rest_data()
    days = days or fetch_calendar(int(rest["created"][:4]), today)
    total, first, cur, best = streaks(days, today)
    os.makedirs(OUT, exist_ok=True)
    for name, svg in (
        ("stats.svg", stats_card(rest, total, first, cur, best, today)),
        ("languages.svg", languages_card(rest, today)),
        ("activity.svg", activity_card(days, today)),
    ):
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
            f.write(svg)
        print("wrote", name, len(svg), "bytes")
    print(f"total={total} current={cur[0]} longest={best[0]}")


if __name__ == "__main__":
    main()
