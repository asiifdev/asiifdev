#!/usr/bin/env python3
"""Generate assets/github-stats.svg: profile stats, streaks, activity heatmap, languages.

Uses only the standard library, the GitHub REST API and GraphQL API.
Env: GH_USER (default asiifdev), GITHUB_TOKEN (required for GraphQL), OUT.
"""
import json
import os
import sys
import urllib.request
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from xml.sax.saxutils import escape

USER = os.environ.get("GH_USER", "asiifdev")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
OUT = os.environ.get("OUT", "assets/github-stats.svg")

# Palette (Tokyo Night inspired)
BG, TILE, TITLE = "#1A1B27", "#212335", "#70A5FD"
TEXT, MUTED, DIM = "#C0CAF5", "#A9B1D6", "#565F89"
LANG_COLORS = ["#38BDF8", "#818CF8", "#34D399", "#FBBF24", "#F472B6", "#FB923C", "#A78BFA", "#94A3B8"]
HEAT = {"NONE": "#2A2E45", "FIRST_QUARTILE": "#0E4F66", "SECOND_QUARTILE": "#0F7DA0",
        "THIRD_QUARTILE": "#22A9D6", "FOURTH_QUARTILE": "#5FD4FF"}
FONT = "-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"


def request(url, data=None):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "profile-stats-generator"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def rest(path):
    return request(f"https://api.github.com{path}")


def graphql(query, variables):
    out = request("https://api.github.com/graphql", json.dumps({"query": query, "variables": variables}).encode())
    if "errors" in out:
        raise RuntimeError(out["errors"])
    return out["data"]["user"]


CAL = "contributionCalendar{totalContributions weeks{contributionDays{date contributionCount contributionLevel weekday}}}"
Q_YEAR = "query($u:String!,$f:DateTime!,$t:DateTime!){user(login:$u){contributionsCollection(from:$f,to:$t){%s}}}" % CAL
Q_RECENT = ("query($u:String!){user(login:$u){createdAt contributionsCollection{totalCommitContributions "
            "totalPullRequestContributions totalIssueContributions restrictedContributionsCount %s}}}") % CAL


def fmt(n):
    return f"{n:,}"


def short(d):
    return d.strftime("%b %-d") if os.name != "nt" else d.strftime("%b %d")


def compute_streaks(days):
    """days: dict date -> count. Returns (current, cur_range, longest, long_range)."""
    ordered = sorted(days)
    longest, long_range, run, start = 0, None, 0, None
    prev = None
    for d in ordered:
        if days[d] > 0:
            if prev is not None and (d - prev).days == 1 and run > 0:
                run += 1
            else:
                run, start = 1, d
            if run > longest:
                longest, long_range = run, (start, d)
        else:
            run = 0
        prev = d
    # current streak: walk back from today (today may still be empty)
    today = max(ordered)
    d = today if days.get(today, 0) > 0 else today - timedelta(days=1)
    cur, end = 0, d
    while days.get(d, 0) > 0:
        cur += 1
        d -= timedelta(days=1)
    cur_range = (d + timedelta(days=1), end) if cur else None
    return cur, cur_range, longest, long_range


def rng(r):
    if not r:
        return "no active streak"
    a, b = r
    return f"{short(a)}, {a.year} - {short(b)}, {b.year}" if a.year != b.year else f"{short(a)} - {short(b)}, {b.year}"


def main():
    profile = rest(f"/users/{USER}")
    repos, page = [], 1
    while True:
        batch = rest(f"/users/{USER}/repos?per_page=100&type=owner&page={page}")
        repos += batch
        if len(batch) < 100:
            break
        page += 1
    own = [r for r in repos if not r["fork"]]
    stars = sum(r["stargazers_count"] for r in own)
    forks = sum(r["forks_count"] for r in own)

    langs = Counter()
    for r in own:
        try:
            langs.update(rest(f"/repos/{USER}/{r['name']}/languages"))
        except Exception as e:
            print(f"skip {r['name']}: {e}", file=sys.stderr)
    total_bytes = sum(langs.values()) or 1
    top = langs.most_common(6)

    recent = graphql(Q_RECENT, {"u": USER})
    created = datetime.fromisoformat(recent["createdAt"].replace("Z", "+00:00"))
    coll = recent["contributionsCollection"]
    weeks = coll["contributionCalendar"]["weeks"]

    # Full history for streaks and all-time total
    days, total_all = {}, 0
    now = datetime.now(timezone.utc)
    for year in range(created.year, now.year + 1):
        f = datetime(year, 1, 1, tzinfo=timezone.utc)
        t = min(datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc), now)
        cal = graphql(Q_YEAR, {"u": USER, "f": f.isoformat(), "t": t.isoformat()})["contributionsCollection"]["contributionCalendar"]
        total_all += cal["totalContributions"]
        for w in cal["weeks"]:
            for d in w["contributionDays"]:
                days[date.fromisoformat(d["date"])] = d["contributionCount"]
    cur, cur_range, longest, long_range = compute_streaks(days)

    year_total = coll["contributionCalendar"]["totalContributions"]
    tiles1 = [("PUBLIC REPOS", fmt(profile["public_repos"]), "owned by " + USER, "#38BDF8"),
              ("STARS EARNED", fmt(stars), "across public repos", "#FBBF24"),
              ("FORKS", fmt(forks), "of public repos", "#34D399"),
              ("FOLLOWERS", fmt(profile["followers"]), "on GitHub", "#F472B6")]
    tiles2 = [("TOTAL CONTRIBUTIONS", fmt(total_all), f"{created.strftime('%b %-d, %Y')} - present", "#818CF8"),
              ("CURRENT STREAK", f"{cur} days", rng(cur_range), "#FB923C"),
              ("LONGEST STREAK", f"{longest} days", rng(long_range), "#A78BFA"),
              ("LAST 12 MONTHS", fmt(year_total),
               f"{fmt(coll['totalCommitContributions'])} commits · {fmt(coll['totalPullRequestContributions'])} PRs", "#5FD4FF")]

    W, PAD, GAP = 854, 32, 12
    tw = (W - 2 * PAD - 3 * GAP) / 4
    th = 88
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="560" viewBox="0 0 {W} 560" role="img" '
         f'aria-label="GitHub stats for {escape(USER)}">',
         f'<rect width="{W}" height="560" rx="14" fill="{BG}"/>',
         f'<text x="{PAD}" y="46" font-family="{FONT}" font-size="22" font-weight="700" fill="{TITLE}">GitHub at a glance</text>',
         f'<text x="{PAD}" y="66" font-family="{FONT}" font-size="12" fill="{DIM}">@{escape(USER)} · member since {created.year}</text>',
         f'<text x="{W - PAD}" y="46" text-anchor="end" font-family="{FONT}" font-size="11" fill="{DIM}">'
         f'updated {now.strftime("%Y-%m-%d")} UTC</text>']

    def tile_row(tiles, y):
        for i, (label, value, sub, color) in enumerate(tiles):
            x = PAD + i * (tw + GAP)
            p.append(f'<rect x="{x:.1f}" y="{y}" width="{tw:.1f}" height="{th}" rx="10" fill="{TILE}"/>')
            p.append(f'<rect x="{x:.1f}" y="{y + 16}" width="3" height="{th - 32}" rx="1.5" fill="{color}"/>')
            p.append(f'<text x="{x + 18:.1f}" y="{y + 26}" font-family="{FONT}" font-size="10.5" font-weight="600" '
                     f'letter-spacing="0.8" fill="{MUTED}">{escape(label)}</text>')
            p.append(f'<text x="{x + 18:.1f}" y="{y + 56}" font-family="{FONT}" font-size="28" font-weight="700" '
                     f'fill="#FFFFFF">{escape(value)}</text>')
            p.append(f'<text x="{x + 18:.1f}" y="{y + 75}" font-family="{FONT}" font-size="11" fill="{DIM}">{escape(sub)}</text>')

    tile_row(tiles1, 88)
    tile_row(tiles2, 88 + th + GAP)

    # Heatmap
    hy = 88 + 2 * (th + GAP) + 34
    p.append(f'<text x="{PAD}" y="{hy - 12}" font-family="{FONT}" font-size="13" font-weight="600" fill="{TITLE}">'
             f'Contribution activity · last 12 months</text>')
    ncols = len(weeks)
    step = (W - 2 * PAD) / ncols
    cell = step - 3
    for ci, wk in enumerate(weeks):
        for d in wk["contributionDays"]:
            y = hy + d["weekday"] * step
            p.append(f'<rect x="{PAD + ci * step:.1f}" y="{y:.1f}" width="{cell:.1f}" height="{cell:.1f}" rx="2.5" '
                     f'fill="{HEAT[d["contributionLevel"]]}"/>')
    hend = hy + 7 * step
    lx = W - PAD - 5 * (cell + 3) - 60
    p.append(f'<text x="{lx - 6:.0f}" y="{hend + 18:.0f}" text-anchor="end" font-family="{FONT}" font-size="10" fill="{DIM}">Less</text>')
    for i, lvl in enumerate(["NONE", "FIRST_QUARTILE", "SECOND_QUARTILE", "THIRD_QUARTILE", "FOURTH_QUARTILE"]):
        p.append(f'<rect x="{lx + i * (cell + 3):.0f}" y="{hend + 8:.0f}" width="{cell:.0f}" height="{cell:.0f}" rx="2.5" fill="{HEAT[lvl]}"/>')
    p.append(f'<text x="{lx + 5 * (cell + 3) + 4:.0f}" y="{hend + 18:.0f}" font-family="{FONT}" font-size="10" fill="{DIM}">More</text>')

    # Languages
    ly = hend + 52
    p.append(f'<text x="{PAD}" y="{ly}" font-family="{FONT}" font-size="13" font-weight="600" fill="{TITLE}">Top languages</text>')
    bw = W - 2 * PAD
    p.append(f'<clipPath id="bar"><rect x="{PAD}" y="{ly + 12}" width="{bw}" height="10" rx="5"/></clipPath><g clip-path="url(#bar)">')
    cx = float(PAD)
    for i, (_, n) in enumerate(top):
        seg = bw * n / total_bytes
        p.append(f'<rect x="{cx:.1f}" y="{ly + 12}" width="{seg + 0.5:.1f}" height="10" fill="{LANG_COLORS[i % 8]}"/>')
        cx += seg
    p.append("</g>")
    for i, (name, n) in enumerate(top):
        x = PAD + (i % 3) * 270
        y = ly + 46 + (i // 3) * 24
        p.append(f'<circle cx="{x + 5}" cy="{y - 4}" r="5" fill="{LANG_COLORS[i % 8]}"/>')
        p.append(f'<text x="{x + 16}" y="{y}" font-family="{FONT}" font-size="13" fill="{TEXT}">{escape(name)} '
                 f'<tspan fill="{DIM}">{100 * n / total_bytes:.1f}%</tspan></text>')
    height = int(ly + 46 + 24 + 28)
    p.append("</svg>")
    svg = "\n".join(p).replace('height="560" viewBox="0 0 854 560"', f'height="{height}" viewBox="0 0 854 {height}"') \
                      .replace('height="560" rx="14"', f'height="{height}" rx="14"')

    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(svg + "\n")
    print(f"wrote {OUT} h={height} cur={cur} longest={longest} total={total_all} year={year_total}")


if __name__ == "__main__":
    main()
