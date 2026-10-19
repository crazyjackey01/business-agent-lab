"""Google search interest for a topic, from Google Trends.

Google publishes no raw search counts. Trends gives a relative index: 100 is the busiest
point in the requested period and every other point is scaled to it. Two series per topic:
  daily   - the last 90 days (Trends only gives daily points up to about 90 days)
  weekly  - the last 5 years
Values are rescaled per request, so compare points within one series, not across series.

Source: the endpoints the Trends website itself uses (explore -> widgetdata/multiline).
This is not an official API: it works from a home connection, can be rate-limited (429)
and may change. Every response is cached in data/eval/gtrends/ for a day.
"""
import json
import time
import urllib.parse
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
CACHE = HERE.parent / "data" / "eval" / "gtrends"
BASE = "https://trends.google.com/trends"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/141.0 Safari/537.36"}
TIMEFRAMES = {"daily": "today 3-m", "weekly": "today 5-y"}

# Demo topic -> (search term, region). "" = worldwide.
KEYWORDS = {
    "전기차": ("전기차", "KR"),
    "갤럭시": ("갤럭시", "KR"),
    "스마트 안경": ("스마트 안경", "KR"),
    "피지컬 AI": ("피지컬 AI", "KR"),
    "physical AI": ("physical AI", "US"),
}


def _get(session, url, tries=4):
    for attempt in range(tries):
        response = session.get(url, headers=HEADERS, timeout=30)
        if response.status_code == 429 and attempt < tries - 1:
            time.sleep(5 * 2 ** attempt)  # rate limited: back off
            continue
        response.raise_for_status()
        return json.loads(response.text[5:])  # strip the )]}' guard
    raise RuntimeError("Google Trends kept answering 429 (rate limited); try again later")


def interest(topic, resolution="daily"):
    """{date (YYYY-MM-DD, start of the day or week): index 0-100}, or None if unmapped."""
    if topic not in KEYWORDS:
        print(f"no Google Trends keyword mapped for {topic!r}; skipped")
        return None
    keyword, geo = KEYWORDS[topic]
    CACHE.mkdir(parents=True, exist_ok=True)
    cache = CACHE / f"{keyword.replace(' ', '_')}_{geo or 'world'}_{resolution}.json"
    if cache.exists() and time.time() - cache.stat().st_mtime < 86400:
        return json.loads(cache.read_text(encoding="utf-8"))

    session = requests.Session()
    session.get(f"{BASE}/?geo={geo}", headers=HEADERS, timeout=30)  # sets the cookie Trends expects
    req = {"comparisonItem": [{"keyword": keyword, "geo": geo, "time": TIMEFRAMES[resolution]}],
           "category": 0, "property": ""}
    explore = _get(session, f"{BASE}/api/explore?hl=ko&tz=-540&req={urllib.parse.quote(json.dumps(req))}")
    widget = next(w for w in explore["widgets"] if w["id"] == "TIMESERIES")
    data = _get(session, f"{BASE}/api/widgetdata/multiline?hl=ko&tz=-540&req="
                         f"{urllib.parse.quote(json.dumps(widget['request']))}&token={widget['token']}")
    series = {}
    for point in data["default"]["timelineData"]:
        if point.get("isPartial"):
            continue  # the current day/week is not finished yet
        day = time.strftime("%Y-%m-%d", time.gmtime(int(point["time"])))
        series[day] = point["value"][0]
    cache.write_text(json.dumps(series, ensure_ascii=False), encoding="utf-8")
    return series


if __name__ == "__main__":
    for topic in KEYWORDS:
        for res in TIMEFRAMES:
            s = interest(topic, res)
            days = sorted(s)
            print(f"{topic:12} {res:6} {len(days):3} points {days[0]}..{days[-1]}  last 4: {[s[d] for d in days[-4:]]}")
            time.sleep(2)
