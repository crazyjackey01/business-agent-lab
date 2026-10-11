"""Collect what people are searching for right now.

Two sources, both free and without an API key:
  1. Google Trends "Trending Now" RSS feed for one country (default: KR).
     Each trend comes with approximate traffic and a few related news articles.
  2. Wikipedia Pageviews API: the most-viewed articles on one language's Wikipedia
     for one day (default: Korean, yesterday). Used as a second signal.

Each run saves a snapshot to data/snapshots/<time>.json so later steps
(the "why is it trending" agent, spike detection) can compare runs.

Usage:
    python midterm/collect_trends.py              # Korea
    python midterm/collect_trends.py --geo US --wiki en
"""
import argparse
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

TRENDS_RSS = "https://trends.google.com/trending/rss?geo={geo}"
WIKI_TOP = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/top/"
    "{wiki}.wikipedia/all-access/{y}/{m}/{d}"
)
# Wikimedia asks API users to identify themselves.
HEADERS = {"User-Agent": "business-agent-lab-midterm/0.1 (student project)"}
HT = "{https://trends.google.com/trending/rss}"  # namespace of the ht: tags

SNAPSHOT_DIR = Path(__file__).resolve().parent / "data" / "snapshots"

# Wikipedia pages that are always popular and say nothing about trends.
# Main pages, search pages, and other namespaces have a ":" in the title.
WIKI_SKIP_PREFIXES = ("위키백과:", "특수:", "Wikipedia:", "Special:", "Main_Page")


def parse_traffic(text):
    """Turn Google's '2,000+' or '10K+' into a number (the lower bound)."""
    text = (text or "").replace(",", "").replace("+", "").strip().upper()
    multiplier = 1
    if text.endswith("K"):
        multiplier, text = 1_000, text[:-1]
    elif text.endswith("M"):
        multiplier, text = 1_000_000, text[:-1]
    try:
        return int(float(text) * multiplier)
    except ValueError:
        return 0


def fetch_google_trends(geo):
    response = requests.get(TRENDS_RSS.format(geo=geo), headers=HEADERS, timeout=20)
    response.raise_for_status()
    root = ET.fromstring(response.content)

    trends = []
    for item in root.iter("item"):
        news = [
            {
                "title": n.findtext(f"{HT}news_item_title", ""),
                "url": n.findtext(f"{HT}news_item_url", ""),
                "source": n.findtext(f"{HT}news_item_source", ""),
            }
            for n in item.findall(f"{HT}news_item")
        ]
        traffic_text = item.findtext(f"{HT}approx_traffic", "")
        trends.append(
            {
                "term": item.findtext("title", ""),
                "traffic": parse_traffic(traffic_text),
                "traffic_text": traffic_text,
                "started": item.findtext("pubDate", ""),
                "news": news,
            }
        )
    trends.sort(key=lambda t: t["traffic"], reverse=True)
    return trends


def fetch_wikipedia_top(wiki, day, limit=25):
    url = WIKI_TOP.format(wiki=wiki, y=day.year, m=f"{day.month:02d}", d=f"{day.day:02d}")
    response = requests.get(url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    articles = response.json()["items"][0]["articles"]

    top = []
    for a in articles:
        title = a["article"]
        if title.startswith(WIKI_SKIP_PREFIXES):
            continue
        top.append({"title": title.replace("_", " "), "views": a["views"]})
        if len(top) == limit:
            break
    return top


def save_snapshot(snapshot):
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    name = datetime.now().strftime("%Y-%m-%d_%H%M") + f"_{snapshot['geo']}.json"
    path = SNAPSHOT_DIR / name
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--geo", default="KR", help="Google Trends country code (KR, US, JP, ...)")
    parser.add_argument("--wiki", default="ko", help="Wikipedia language code (ko, en, ja, ...)")
    args = parser.parse_args()

    # Pageview data for a day is complete only after that day ends (UTC).
    yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)

    trends = fetch_google_trends(args.geo)
    wiki_top = fetch_wikipedia_top(args.wiki, yesterday)

    snapshot = {
        "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "geo": args.geo,
        "wiki": args.wiki,
        "wiki_day": yesterday.isoformat(),
        "google_trends": trends,
        "wikipedia_top": wiki_top,
    }
    path = save_snapshot(snapshot)

    print(f"Google Trends ({args.geo}) - {len(trends)} trending searches")
    for t in trends[:15]:
        headline = t["news"][0]["title"] if t["news"] else ""
        print(f"  {t['traffic_text']:>7}  {t['term']}  | {headline[:50]}")

    print(f"\nWikipedia ({args.wiki}) most viewed on {yesterday}")
    for a in wiki_top[:10]:
        print(f"  {a['views']:>7,}  {a['title']}")

    print(f"\nSaved {path.relative_to(Path.cwd()) if path.is_relative_to(Path.cwd()) else path}")


if __name__ == "__main__":
    main()
