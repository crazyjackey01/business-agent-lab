"""Find what is trending around one topic you choose (for example "피지컬 AI").

Three signals, all real-time and without an API key:
  1. Google autocomplete: what people type after the topic. The topic is tried
     alone and followed by each starting letter (ㄱ-ㅎ for Korean, a-z for
     English), a common keyword-research trick. These show what searchers want.
  2. Google News search RSS: articles about the topic, counted day by day for the
     last 7 days. Comparing today with the daily average gives a momentum number.
  3. The Google Trends "Trending Now" feed, filtered to trends that mention the topic.

Each run saves a result to data/topics/<topic>_<time>.json.

Usage:
    python midterm/topic_trends.py --topic "피지컬 AI"
    python midterm/topic_trends.py --topic "physical AI" --lang en --geo US
    python midterm/topic_trends.py                 # every topic in topics.json
"""
import argparse
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

from collect_trends import HEADERS, fetch_google_trends

SUGGEST_URL = "https://suggestqueries.google.com/complete/search"
NEWS_RSS = "https://news.google.com/rss/search"

HERE = Path(__file__).resolve().parent
TOPICS_FILE = HERE / "topics.json"
RESULT_DIR = HERE / "data" / "topics"

KOREAN_LETTERS = list("ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎ")
ENGLISH_LETTERS = list("abcdefghijklmnopqrstuvwxyz")


# 1. Autocomplete ------------------------------------------------------------

def fetch_suggestions(query, lang, geo):
    params = {"client": "firefox", "hl": lang, "gl": geo.lower(), "q": query}
    response = requests.get(SUGGEST_URL, params=params, headers=HEADERS, timeout=10)
    response.raise_for_status()
    return response.json()[1]


def related_searches(topic, lang, geo):
    """Return the autocomplete phrases for the topic, most often suggested first."""
    letters = KOREAN_LETTERS if lang == "ko" else ENGLISH_LETTERS
    queries = [topic] + [f"{topic} {letter}" for letter in letters]

    def suggest(q):
        try:
            return fetch_suggestions(q, lang, geo)
        except requests.RequestException:
            return []  # one failed letter should not stop the run

    # A few requests at a time instead of one by one.
    counts = Counter()
    with ThreadPoolExecutor(max_workers=5) as pool:
        for phrases in pool.map(suggest, queries):
            for phrase in phrases:
                counts[phrase.lower()] += 1

    counts.pop(topic.lower(), None)
    # Drop phrases where the topic is only the start of another word
    # ("physical ai" -> "physical ailments").
    pattern = re.compile(rf"(^|\s){re.escape(topic.lower())}(\s|$)")
    counts = Counter({p: n for p, n in counts.items() if pattern.search(p)})
    return [{"phrase": p, "times_suggested": n} for p, n in counts.most_common()]


# 2. News --------------------------------------------------------------------

def fetch_news(query, lang, geo):
    params = {"q": query, "hl": lang, "gl": geo, "ceid": f"{geo}:{lang}"}
    response = requests.get(NEWS_RSS, params=params, headers=HEADERS, timeout=20)
    response.raise_for_status()
    root = ET.fromstring(response.content)

    articles = []
    for item in root.iter("item"):
        source = item.findtext("source", "")
        title = item.findtext("title", "")
        # Google appends " - Source" to every title.
        if source and title.endswith(f" - {source}"):
            title = title[: -len(source) - 3]
        try:
            published = parsedate_to_datetime(item.findtext("pubDate", ""))
        except (TypeError, ValueError):
            continue
        articles.append(
            {
                "title": title,
                "source": source,
                "url": item.findtext("link", ""),
                "published": published.isoformat(),
            }
        )
    return articles


def news_by_day(topic, lang, geo, days=7):
    """Fetch the topic's news one day at a time.

    One query returns at most 100 articles, so a single 7-day query undercounts
    busy days. Asking per day (after:/before:) keeps each day's count accurate
    up to 100. Returns (all articles newest first, count per day today first).
    """
    today = datetime.now().date()
    day_list = [today - timedelta(days=d) for d in range(days)]

    def one_day(day):
        query = f"{topic} after:{day - timedelta(days=1)} before:{day + timedelta(days=1)}"
        return [
            a for a in fetch_news(query, lang, geo)
            if datetime.fromisoformat(a["published"]).astimezone().date() == day
        ]

    articles, counts = {}, []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for day_articles in pool.map(one_day, day_list):
            counts.append(len(day_articles))
            for a in day_articles:
                articles[a["url"]] = a
    ordered = sorted(articles.values(), key=lambda a: a["published"], reverse=True)
    return ordered, counts


def news_momentum(per_day):
    """Today's article count compared with the average of the previous days.

    Above 1.0 means the topic is getting more coverage than usual right now.
    Today is still in progress, so early in the day the number runs low.
    """
    today, previous = per_day[0], per_day[1:]
    baseline = sum(previous) / len(previous) if previous else 0
    return {
        "today": today,
        "previous_daily_average": round(baseline, 1),
        "momentum": round(today / baseline, 2) if baseline else 0.0,
        "per_day": per_day,  # index 0 = today
        "capped_days": sum(1 for n in per_day if n >= 100),
    }


# 3. Matching Google Trends --------------------------------------------------

def matching_trends(topic, geo, extra_words=()):
    """Trending searches whose term or news headlines mention the topic."""
    # The whole topic plus each extra word. Latin words must match as whole words,
    # so "ai" does not match "weather". Korean words match anywhere, because
    # Korean attaches particles to words ("피지컬AI가").
    phrases = [topic.lower()] + [w.lower() for w in extra_words]
    patterns = [
        re.compile(rf"\b{re.escape(p)}\b") if p.isascii() else re.compile(re.escape(p))
        for p in phrases
    ]
    matches = []
    for t in fetch_google_trends(geo):
        text = " ".join([t["term"]] + [n["title"] for n in t["news"]]).lower()
        if any(p.search(text) for p in patterns):
            matches.append(t)
    return matches


# Run ------------------------------------------------------------------------

def analyze_topic(topic, lang, geo, extra_words=()):
    articles, per_day = news_by_day(topic, lang, geo)
    return {
        "topic": topic,
        "lang": lang,
        "geo": geo,
        "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "related_searches": related_searches(topic, lang, geo),
        "news_momentum": news_momentum(per_day),
        "news": articles,
        "google_trends_matches": matching_trends(topic, geo, extra_words),
    }


def save_result(result):
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^\w]+", "-", result["topic"]).strip("-").lower()
    path = RESULT_DIR / f"{slug}_{datetime.now():%Y-%m-%d_%H%M}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def print_result(result):
    m = result["news_momentum"]
    print(f"\n=== {result['topic']} ({result['geo']}) ===")
    print(
        f"News: {m['today']} articles today, {m['previous_daily_average']}/day before"
        f" -> momentum {m['momentum']}"
        + (f" ({m['capped_days']} day(s) hit the 100-article cap)" if m["capped_days"] else "")
    )
    print(f"      per day, today first: {m['per_day']}")

    print("\nWhat people search with it (Google autocomplete):")
    for s in result["related_searches"][:20]:
        print(f"  {s['times_suggested']:>2}x  {s['phrase']}")

    print("\nLatest headlines:")
    for a in result["news"][:8]:
        print(f"  {a['published'][:16]}  {a['title'][:60]}  ({a['source']})")

    matches = result["google_trends_matches"]
    print(f"\nIn Google Trends right now: {len(matches)} matching trend(s)")
    for t in matches:
        print(f"  {t['traffic_text']:>7}  {t['term']}")


def load_watchlist():
    if not TOPICS_FILE.exists():
        return []
    return json.loads(TOPICS_FILE.read_text(encoding="utf-8"))["topics"]


def main():
    parser = argparse.ArgumentParser(description="Find what is trending around one topic.")
    parser.add_argument("--topic", help="Topic to research. Leave out to run topics.json.")
    parser.add_argument("--lang", default="ko", help="Language code (ko, en, ...)")
    parser.add_argument("--geo", default="KR", help="Country code (KR, US, ...)")
    parser.add_argument(
        "--also", nargs="*", default=[],
        help="Extra words that count as a match in Google Trends (e.g. 로봇 휴머노이드)",
    )
    args = parser.parse_args()

    if args.topic:
        topics = [{"topic": args.topic, "lang": args.lang, "geo": args.geo, "also": args.also}]
    else:
        topics = load_watchlist()
        if not topics:
            parser.error("give --topic or add topics to topics.json")

    for t in topics:
        result = analyze_topic(t["topic"], t.get("lang", "ko"), t.get("geo", "KR"), t.get("also", []))
        print_result(result)
        print(f"\nSaved {save_result(result).relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
