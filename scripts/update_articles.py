#!/usr/bin/env python3
"""
Keep soccer_articles.yml current.

    python scripts/update_articles.py                  # add new Equalizer Soccer articles from my author feed
    python scripts/update_articles.py --espn URL [URL]  # add ESPN articles by link (ESPN has no author feed)
    python scripts/update_articles.py --dry-run         # show what would be added without changing the file

New entries are inserted in date order, in the same format as the rest of the file.
Network problems print a warning and exit 0, so the scheduled publish still runs.
"""
import argparse
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests
import yaml

YML = Path(__file__).resolve().parent.parent / "soccer_articles.yml"
EQ_FEED = "https://equalizersoccer.com/author/arianna1521386/feed/"
ESPN_API = "https://content.core.api.espn.com/v1/sports/news/{id}"
BYLINE = "Cascone"
HEADERS = {"User-Agent": "adcascone-website-updater (+https://github.com/adcascone/adcascone.github.io)"}
MAX_FEED_PAGES = 10


# ── text helpers ────────────────────────────────────────────────────────────────────────────────

def clean(text: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", "", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\s*The post .* appeared first on .*$", "", text)


def clean_description(text: str) -> str:
    """Drop embedded links and feed truncation marks; end on a full sentence."""
    text = re.split(r"\s*https?://", clean(text))[0].strip()
    truncated = text.endswith(("[…]", "[...]", "…")) or len(text) > 300
    text = re.sub(r"\s*\[(…|\.\.\.)\]\s*$", "", text).strip()
    if truncated:
        ends = [m.end() for m in re.finditer(r"[.!?](?=\s|$)", text)]
        text = text[: ends[-1]] if ends else text
    if text and text[-1] not in ".!?\"”":
        text += "."
    return text


def norm(url: str) -> str:
    return url.strip().rstrip("/").lower()


# ── sources ─────────────────────────────────────────────────────────────────────────────────────

def equalizer_articles(known: set[str]) -> list[dict]:
    """Walk the author feed newest-first until a page has nothing new."""
    found = []
    for page in range(1, MAX_FEED_PAGES + 1):
        resp = requests.get(EQ_FEED, params={"paged": page} if page > 1 else None, headers=HEADERS, timeout=20)
        if resp.status_code == 404:
            break
        resp.raise_for_status()
        items = ET.fromstring(resp.content).iter("item")
        new_on_page, any_items = 0, False
        for item in items:
            any_items = True
            url = item.findtext("link", "").strip()
            if not url or norm(url) in known:
                continue
            known.add(norm(url))
            new_on_page += 1
            found.append({
                "title": clean(item.findtext("title")),
                "date": parsedate_to_datetime(item.findtext("pubDate")).date().isoformat(),
                "url": url,
                "description": clean_description(item.findtext("description")),
                "publisher": "Equalizer Soccer",
                "prefix": "EQ",
            })
        if not any_items or new_on_page == 0:
            break
    return found


def espn_article(ref: str, known: set[str]) -> dict | None:
    match = re.search(r"/id/(\d+)", ref) or re.fullmatch(r"\s*(\d+)\s*", ref)
    if not match:
        print(f"  ! couldn't find an ESPN story id in {ref!r}")
        return None
    story_id = match.group(1)
    if any(f"/id/{story_id}" in u for u in known):
        print(f"  - ESPN story {story_id} is already listed")
        return None
    resp = requests.get(ESPN_API.format(id=story_id), headers=HEADERS, timeout=20)
    resp.raise_for_status()
    story = resp.json()["headlines"][0]
    if BYLINE not in (story.get("byline") or ""):
        print(f"  ! ESPN story {story_id} is bylined {story.get('byline')!r}; skipped")
        return None
    return {
        "title": re.sub(r"\s+", " ", story["headline"]).strip(),
        "date": story["published"][:10],
        "url": story["links"]["web"]["href"],
        "description": clean_description(story.get("description") or ""),
        "publisher": "ESPN",
        "prefix": "ESPN",
    }


# ── writing ─────────────────────────────────────────────────────────────────────────────────────

def yaml_block(a: dict, used: set[str]) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", a["url"].rstrip("/").split("/")[-1]).strip("_")
    base = f'{a["prefix"]}_{a["date"].replace("-", "")}_{"_".join(slug.split("_")[:5])}'
    key, n = base, 2
    while key in used:
        key, n = f"{base}_{n}", n + 1
    used.add(key)
    q = lambda s: json.dumps(s, ensure_ascii=False)  # JSON strings are valid YAML double-quoted scalars
    return (f"{key}:\n  title: {q(a['title'])}\n  authors:\n  - me\n  year: {a['date'][:4]}\n"
            f"  date: {a['date']}\n  published_url: {a['url']}\n  description: {q(a['description'])}\n"
            f"  publisher: {a['publisher']}\n\n")


def insert_in_date_order(src: str, articles: list[dict]) -> str:
    starts = [m.start() for m in re.finditer(r"^[^\s#][^:\n]*:\s*$", src, flags=re.M)]
    head = src[: starts[0]] if starts else src
    blocks = [src[s:e] for s, e in zip(starts, starts[1:] + [len(src)])]
    used = {b.split(":", 1)[0] for b in blocks}

    def block_date(b: str) -> str:
        m = re.search(r"^\s+date:\s*(\S+)", b, flags=re.M)
        return m.group(1) if m else ""

    for a in sorted(articles, key=lambda a: a["date"], reverse=True):
        new = yaml_block(a, used)
        idx = next((i for i, b in enumerate(blocks) if block_date(b) and block_date(b) < a["date"]), len(blocks))
        blocks.insert(idx, new)
    blocks = [b if b.endswith("\n\n") else b.rstrip("\n") + "\n\n" for b in blocks]
    return head + "".join(blocks).rstrip("\n") + "\n"


# ── main ────────────────────────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--espn", nargs="+", metavar="URL", help="ESPN story links (or ids) to add")
    ap.add_argument("--dry-run", action="store_true", help="print what would be added; don't write")
    args = ap.parse_args()

    src = YML.read_text(encoding="utf-8")
    before = len(yaml.safe_load(src) or {})
    known = {norm(u) for u in re.findall(r"published_url:\s*(\S+)", src)}

    new: list[dict] = []
    try:
        if args.espn:
            for ref in args.espn:
                a = espn_article(ref, known)
                if a:
                    known.add(norm(a["url"]))
                    new.append(a)
        else:
            new = equalizer_articles(known)
    except (requests.RequestException, ET.ParseError, KeyError, ValueError) as err:
        print(f"Warning: couldn't check for new articles ({err}); leaving soccer_articles.yml unchanged.")
        return 0

    if not new:
        print("No new articles.")
        return 0
    for a in sorted(new, key=lambda a: a["date"], reverse=True):
        print(f"  + {a['date']}  {a['publisher']}: {a['title']}")
    if args.dry_run:
        print(f"(dry run) {len(new)} article(s) would be added.")
        return 0

    out = insert_in_date_order(src, new)
    after = len(yaml.safe_load(out))
    assert after == before + len(new), f"expected {before + len(new)} entries, found {after}"
    YML.write_text(out, encoding="utf-8")
    print(f"Added {len(new)} article(s); {after} entries in {YML.name}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
