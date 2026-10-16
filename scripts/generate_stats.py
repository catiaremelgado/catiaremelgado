#!/usr/bin/env python3
"""Generate self-hosted GitHub activity images for the profile README.

Fetches the contribution calendar from the GitHub GraphQL API and writes:
  images/stats.svg     - total contributions, current streak, longest streak
  images/activity.svg  - area chart of daily contributions (last 31 days)

Only the Python standard library is used, so there is nothing to install.

Usage:
  GITHUB_TOKEN=... python scripts/generate_stats.py catiaremelgado
  python scripts/generate_stats.py catiaremelgado --from-json sample.json   (offline test)
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import urllib.request
from xml.sax.saxutils import escape

# ---- Look & feel (matches the dark theme the README already uses) ----------
BG = "#0d1117"
CARD_BORDER = "#30363d"
TITLE = "#e6edf3"
TEXT = "#8b949e"
ACCENT = "#7289da"       # discord "old blurple"
ACCENT_2 = "#9ba8e8"
GRID = "#21262d"
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
DAYS_IN_GRAPH = 31

QUERY = """
query($login: String!) {
  user(login: $login) {
    name
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


def fetch_calendar(login: str, token: str) -> dict:
    body = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json",
                 "User-Agent": "profile-stats-generator"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    if "errors" in payload:
        raise SystemExit(f"GitHub API error: {payload['errors']}")
    return payload["data"]["user"]


def parse_days(user: dict) -> list[tuple[dt.date, int]]:
    cal = user["contributionsCollection"]["contributionCalendar"]
    days = [
        (dt.date.fromisoformat(d["date"]), d["contributionCount"])
        for w in cal["weeks"] for d in w["contributionDays"]
    ]
    return sorted(days)


def streaks(days: list[tuple[dt.date, int]]) -> tuple[int, int]:
    longest = run = 0
    for _, count in days:
        run = run + 1 if count > 0 else 0
        longest = max(longest, run)
    # Current streak: today not having contributions yet does not break it.
    current = 0
    seq = days[:-1] if days and days[-1][1] == 0 else days
    for _, count in reversed(seq):
        if count == 0:
            break
        current += 1
    return current, longest


def stats_svg(total: int, current: int, longest: int, best: tuple[dt.date, int]) -> str:
    w, h = 900, 150
    cols = [
        (f"{total:,}", "Contributions", "past year"),
        (str(current), "Current streak", "days"),
        (str(longest), "Longest streak", "days, past year"),
        (str(best[1]), "Best day", best[0].strftime("%d %b %Y")),
    ]
    col_w = (w - 40) / len(cols)
    parts = []
    for i, (value, label, sub) in enumerate(cols):
        cx = 20 + col_w * i + col_w / 2
        parts.append(
            f'<text x="{cx:.0f}" y="68" class="value">{escape(value)}</text>'
            f'<text x="{cx:.0f}" y="98" class="label">{escape(label)}</text>'
            f'<text x="{cx:.0f}" y="118" class="sub">{escape(sub)}</text>'
        )
        if i:
            x = 20 + col_w * i
            parts.append(f'<line x1="{x:.0f}" y1="40" x2="{x:.0f}" y2="120" stroke="{CARD_BORDER}"/>')
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="GitHub contribution stats">
<style>
  text {{ font-family: {FONT}; text-anchor: middle; }}
  .value {{ fill: {ACCENT_2}; font-size: 32px; font-weight: 700; }}
  .label {{ fill: {TITLE}; font-size: 15px; font-weight: 600; }}
  .sub {{ fill: {TEXT}; font-size: 12px; }}
</style>
<rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="10" fill="{BG}" stroke="{CARD_BORDER}"/>
{''.join(parts)}
</svg>
"""


def nice_max(v: int) -> int:
    if v <= 4:
        return 4
    for step in (5, 10, 20, 25, 50, 100, 200, 250, 500, 1000):
        if v <= step * 4:
            return -(-v // step) * step
    return v


def activity_svg(days: list[tuple[dt.date, int]], title: str) -> str:
    days = days[-DAYS_IN_GRAPH:]
    w, h = 900, 320
    left, right, top, bottom = 50, 25, 60, 50
    pw, ph = w - left - right, h - top - bottom
    ymax = nice_max(max((c for _, c in days), default=0))
    n = len(days)

    def x(i): return left + pw * i / max(n - 1, 1)
    def y(c): return top + ph - ph * c / ymax

    grid = []
    for k in range(5):
        val = ymax * k / 4
        yy = y(val)
        grid.append(f'<line x1="{left}" y1="{yy:.1f}" x2="{w-right}" y2="{yy:.1f}" stroke="{GRID}"/>'
                    f'<text x="{left-10}" y="{yy+4:.1f}" class="axis" text-anchor="end">{val:g}</text>')

    labels = []
    for i, (d, _) in enumerate(days):
        if i % 3 == 0 or i == n - 1:
            labels.append(f'<text x="{x(i):.1f}" y="{h-bottom+22}" class="axis" text-anchor="middle">{d.day}</text>')

    pts = [(x(i), y(c)) for i, (_, c) in enumerate(days)]
    line = " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
    area = f"{left},{top+ph} {line} {pts[-1][0]:.1f},{top+ph}" if pts else ""
    dots = "".join(
        f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.5" fill="{BG}" stroke="{ACCENT_2}" stroke-width="2">'
        f'<title>{d.isoformat()}: {c} contribution{"s" if c != 1 else ""}</title></circle>'
        for (px, py), (d, c) in zip(pts, days)
    )
    first, last = days[0][0], days[-1][0]
    period = f"{first.strftime('%d %b')} – {last.strftime('%d %b %Y')}"

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{escape(title)}">
<style>
  text {{ font-family: {FONT}; }}
  .title {{ fill: {TITLE}; font-size: 18px; font-weight: 600; }}
  .period {{ fill: {TEXT}; font-size: 12px; }}
  .axis {{ fill: {TEXT}; font-size: 11px; }}
</style>
<defs>
  <linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="{ACCENT}" stop-opacity="0.55"/>
    <stop offset="100%" stop-color="{ACCENT}" stop-opacity="0.02"/>
  </linearGradient>
</defs>
<rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="10" fill="{BG}" stroke="{CARD_BORDER}"/>
<text x="{w/2}" y="32" class="title" text-anchor="middle">{escape(title)}</text>
<text x="{w-right}" y="32" class="period" text-anchor="end">{escape(period)}</text>
{''.join(grid)}
<polygon points="{area}" fill="url(#fill)"/>
<polyline points="{line}" fill="none" stroke="{ACCENT}" stroke-width="2.5" stroke-linejoin="round"/>
{dots}
{''.join(labels)}
<text x="{left + pw/2}" y="{h-8}" class="axis" text-anchor="middle">Days</text>
<text x="14" y="{top + ph/2}" class="axis" text-anchor="middle" transform="rotate(-90 14 {top + ph/2})">Contributions</text>
</svg>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("login")
    ap.add_argument("--out", default="images")
    ap.add_argument("--from-json", help="read a saved API 'user' object instead of calling GitHub")
    args = ap.parse_args()

    if args.from_json:
        user = json.loads(pathlib.Path(args.from_json).read_text())
    else:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            raise SystemExit("Set GITHUB_TOKEN")
        user = fetch_calendar(args.login, token)

    days = parse_days(user)
    total = user["contributionsCollection"]["contributionCalendar"]["totalContributions"]
    current, longest = streaks(days)
    best = max(days, key=lambda d: d[1])
    first_name = (user.get("name") or args.login).split()[0]

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "stats.svg").write_text(stats_svg(total, current, longest, best), encoding="utf-8")
    (out / "activity.svg").write_text(
        activity_svg(days, f"{first_name}'s Contribution Graph"), encoding="utf-8")
    print(f"total={total} current={current} longest={longest} best={best}")


if __name__ == "__main__":
    main()
