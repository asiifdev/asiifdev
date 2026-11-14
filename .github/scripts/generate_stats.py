#!/usr/bin/env python3
"""Generate assets/github-stats.svg from the GitHub REST API (stdlib only)."""
import json
import os
import sys
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from xml.sax.saxutils import escape

USER = os.environ.get("GH_USER", "asiifdev")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
OUT = os.environ.get("OUT", "assets/github-stats.svg")

COLORS = ["#38BDF8", "#818CF8", "#34D399", "#FBBF24", "#F472B6", "#FB923C", "#A78BFA", "#94A3B8"]


def api(path):
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "profile-stats-generator",
            **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main():
    user = api(f"/users/{USER}")
    repos, page = [], 1
    while True:
        batch = api(f"/users/{USER}/repos?per_page=100&type=owner&page={page}")
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
            langs.update(api(f"/repos/{USER}/{r['name']}/languages"))
        except Exception as e:  # skip repos we cannot read
            print(f"skip {r['name']}: {e}", file=sys.stderr)
    total = sum(langs.values()) or 1
    top = langs.most_common(6)

    stats = [
        ("Public repos", user["public_repos"]),
        ("Stars earned", stars),
        ("Forks", forks),
        ("Followers", user["followers"]),
    ]

    font = "-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
    w, h = 854, 250
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="GitHub stats for {escape(USER)}">',
        f'<rect width="{w}" height="{h}" rx="12" fill="#1A1B27"/>',
        f'<text x="32" y="44" font-family="{font}" font-size="20" font-weight="700" fill="#70A5FD">GitHub at a glance</text>',
    ]
    colw = (w - 64) / len(stats)
    for i, (label, val) in enumerate(stats):
        x = 32 + i * colw
        parts.append(f'<text x="{x:.0f}" y="94" font-family="{font}" font-size="34" font-weight="700" fill="#FFFFFF">{val}</text>')
        parts.append(f'<text x="{x:.0f}" y="118" font-family="{font}" font-size="13" fill="#A9B1D6">{escape(label)}</text>')

    parts.append(f'<text x="32" y="162" font-family="{font}" font-size="14" font-weight="600" fill="#70A5FD">Top languages</text>')
    bx, bw = 32, w - 64
    parts.append(f'<clipPath id="bar"><rect x="{bx}" y="174" width="{bw}" height="10" rx="5"/></clipPath><g clip-path="url(#bar)">')
    cx = float(bx)
    for i, (_, n) in enumerate(top):
        seg = bw * n / total
        parts.append(f'<rect x="{cx:.1f}" y="174" width="{seg:.1f}" height="10" fill="{COLORS[i % len(COLORS)]}"/>')
        cx += seg
    parts.append("</g>")
    for i, (name, n) in enumerate(top):
        x = 32 + (i % 3) * 270
        y = 214 + (i // 3) * 24
        parts.append(f'<circle cx="{x + 5}" cy="{y - 4}" r="5" fill="{COLORS[i % len(COLORS)]}"/>')
        parts.append(f'<text x="{x + 16}" y="{y}" font-family="{font}" font-size="13" fill="#C0CAF5">{escape(name)} {100 * n / total:.1f}%</text>')
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    parts.append(f'<text x="{w - 32}" y="44" text-anchor="end" font-family="{font}" font-size="11" fill="#565F89">updated {stamp}</text>')
    parts.append("</svg>")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(parts) + "\n")
    print(f"wrote {OUT}: {stats}, langs={top}")


if __name__ == "__main__":
    main()
