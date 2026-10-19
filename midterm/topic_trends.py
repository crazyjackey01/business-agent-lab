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
RESULT_DIR = HERE / "data" / "topics"

# Gambling spam sites stuff unrelated keywords into headlines to get into Google News.
# Dropped unless the topic itself is about these words. The count is kept as a finding.
SPAM_WORDS = ["토토", "카지노", "바카라", "슬롯", "베팅", "먹튀", "casino", "betting", "baccarat", "slots"]

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


def is_spam(title, topic):
    title, topic = title.lower(), topic.lower()
    return any(w in title and w not in topic for w in SPAM_WORDS)


def news_by_day(topic, lang, geo, days=7):
    """Count the topic's news in 24-hour windows going back from now.

    Windows, not calendar days: at 2 a.m. the calendar day has barely started,
    which made "today" look nearly empty. Window 0 is the last 24 hours, window 1
    the 24 hours before that, and so on.

    One query returns at most 100 articles, so the news is fetched one calendar
    day at a time (after:/before:), one extra day back to fill the oldest window.
    Spam headlines are dropped before counting. On busy days a query fills its
    100-article limit and Google's date filter (about a day off, time zones)
    squeezes out the neighbouring days, so those counts are minimums.
    Returns (articles newest first, count per window newest first, spam removed,
    number of queries that hit the 100 limit, per window: True if it may be undercounted).
    """
    now = datetime.now(timezone.utc)
    today = datetime.now().date()
    day_list = [today - timedelta(days=d) for d in range(days + 1)]

    def one_day(day):
        query = f"{topic} after:{day - timedelta(days=1)} before:{day + timedelta(days=1)}"
        return fetch_news(query, lang, geo)

    articles, spam, capped, from_capped = {}, 0, 0, set()
    with ThreadPoolExecutor(max_workers=4) as pool:
        for day_articles in pool.map(one_day, day_list):
            hit_limit = len(day_articles) >= 100
            capped += hit_limit
            for a in day_articles:
                if is_spam(a["title"], topic):
                    spam += 1
                elif now - datetime.fromisoformat(a["published"]) < timedelta(days=days):
                    articles[a["url"]] = a
                    if hit_limit:
                        from_capped.add(a["url"])

    counts, capped_windows = [0] * days, [False] * days
    for a in articles.values():
        window = (now - datetime.fromisoformat(a["published"])) // timedelta(hours=24)
        counts[window] += 1
        capped_windows[window] |= a["url"] in from_capped  # count may be a minimum
    ordered = sorted(articles.values(), key=lambda a: a["published"], reverse=True)
    return ordered, counts, spam, capped, capped_windows


def news_momentum(per_day, capped_queries=0, capped_windows=None):
    """The last 24 hours' article count compared with the average of the earlier windows.

    Above 1.0 means the topic is getting more coverage than usual right now.
    "today" in the result means the last 24 hours.
    """
    today, previous = per_day[0], per_day[1:]
    baseline = sum(previous) / len(previous) if previous else 0
    return {
        "today": today,
        "previous_daily_average": round(baseline, 1),
        "momentum": round(today / baseline, 2) if baseline else 0.0,
        "per_day": per_day,  # index 0 = last 24 hours
        "capped_queries": capped_queries,  # queries that hit Google's 100-article limit
        "capped_windows": capped_windows or [False] * len(per_day),  # newest first
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
    articles, per_day, spam, capped, capped_windows = news_by_day(topic, lang, geo)
    return {
        "topic": topic,
        "lang": lang,
        "geo": geo,
        "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "related_searches": related_searches(topic, lang, geo),
        "news_momentum": news_momentum(per_day, capped, capped_windows),
        "news": articles,
        "news_spam_removed": spam,
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
        f"News: {m['today']} articles in the last 24h, {m['previous_daily_average']}/day before"
        f" -> momentum {m['momentum']}"
        + (f" ({m['capped_queries']} query(s) hit the 100-article limit: counts are minimums)" if m.get("capped_queries") else "")
    )
    print(f"      per 24h window, newest first: {m['per_day']}")

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


def main():
    parser = argparse.ArgumentParser(description="Find what is trending around one topic.")
    parser.add_argument("--topic", required=True, help="Topic to research")
    parser.add_argument("--lang", default="ko", help="Language code (ko, en, ...)")
    parser.add_argument("--geo", default="KR", help="Country code (KR, US, ...)")
    parser.add_argument(
        "--also", nargs="*", default=[],
        help="Extra words that count as a match in Google Trends (e.g. 로봇 휴머노이드)",
    )
    args = parser.parse_args()

    result = analyze_topic(args.topic, args.lang, args.geo, args.also)
    print_result(result)
    print(f"\nSaved {save_result(result).relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
