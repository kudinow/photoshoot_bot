#!/usr/bin/env python3
"""Generate sitemap.xml for ai-photobot.ru from landing + blog posts.

Usage:
    python3 scripts/gen_sitemap.py                  # writes to landing/sitemap.xml
    python3 scripts/gen_sitemap.py --output PATH    # writes to PATH
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, date
from pathlib import Path
from xml.sax.saxutils import escape

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
POSTS_DIR = REPO_ROOT / "blog" / "posts"
DEFAULT_OUTPUT = REPO_ROOT / "landing" / "sitemap.xml"

SITE_URL = "https://ai-photobot.ru"


def parse_post_meta(filepath: Path) -> dict | None:
    text = filepath.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    meta = yaml.safe_load(parts[1])
    if not meta.get("published", False):
        return None
    meta.setdefault("slug", filepath.stem)
    date_val = meta["date"]
    if isinstance(date_val, str):
        meta["date_obj"] = datetime.fromisoformat(date_val).date()
    elif isinstance(date_val, datetime):
        meta["date_obj"] = date_val.date()
    elif isinstance(date_val, date):
        meta["date_obj"] = date_val
    else:
        return None
    return meta


def collect_urls() -> list[dict]:
    today = date.today().isoformat()
    urls: list[dict] = [
        {"loc": f"{SITE_URL}/", "lastmod": today, "changefreq": "weekly", "priority": "1.0"},
        {"loc": f"{SITE_URL}/blog/", "lastmod": today, "changefreq": "daily", "priority": "0.8"},
    ]

    posts = []
    if POSTS_DIR.exists():
        for f in sorted(POSTS_DIR.glob("*.md")):
            meta = parse_post_meta(f)
            if meta:
                posts.append(meta)

    posts.sort(key=lambda p: p["date_obj"], reverse=True)

    for post in posts:
        urls.append({
            "loc": f"{SITE_URL}/blog/{post['slug']}/",
            "lastmod": post["date_obj"].isoformat(),
            "changefreq": "monthly",
            "priority": "0.6",
        })

    return urls


def render_sitemap(urls: list[dict]) -> str:
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        parts.append("  <url>")
        parts.append(f"    <loc>{escape(u['loc'])}</loc>")
        parts.append(f"    <lastmod>{u['lastmod']}</lastmod>")
        parts.append(f"    <changefreq>{u['changefreq']}</changefreq>")
        parts.append(f"    <priority>{u['priority']}</priority>")
        parts.append("  </url>")
    parts.append("</urlset>")
    parts.append("")
    return "\n".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = ap.parse_args()

    urls = collect_urls()
    xml = render_sitemap(urls)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(xml, encoding="utf-8")
    print(f"Wrote {len(urls)} URLs to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
