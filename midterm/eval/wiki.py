"""Daily Wikipedia pageviews for a topic: the external ground truth for public interest.

Wikimedia Pageviews REST API, per article, daily, human users only ("user" agent).
Wikimedia requires a descriptive User-Agent. Responses are cached in
data/eval/wiki/ and refreshed when older than a day.

Caveat: Korean readers mostly use 나무위키, which publishes no pageviews, so Korean
Wikipedia counts are small (전기자동차: about 7 views a day) and noisy.
"""
import json
import time
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
CACHE = HERE.parent / "data" / "eval" / "wiki"
API = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{project}/all-access/user/{title}/daily/{start}/{end}"
HEADERS = {"User-Agent": "business-agent-lab-midterm/0.1 (student project; https://github.com/crazyjackey01/business-agent-lab)"}

# Demo topic -> (Wikipedia project, article title). Chosen by checking which article
# exists and gets the most views (2026-09-01..10-18 averages in the comment).
ARTICLES = {
    "전기차": ("ko.wikipedia", "전기자동차"),       # 7/day ("전기차" itself: 2/day)
    "갤럭시": ("ko.wikipedia", "삼성 갤럭시"),      # 51/day
    "스마트 안경": ("ko.wikipedia", "스마트글래스"),  # 11/day ("스마트 안경": 0/day)
    "피지컬 AI": ("ko.wikipedia", "피지컬 AI"),     # 49/day
    "physical AI": ("en.wikipedia", "Physical AI"),  # 5/day
}


def article_for(topic):
    """(project, title) for a topic, or None (printed) when there is no mapping."""
    if topic not in ARTICLES:
        print(f"no Wikipedia article mapped for {topic!r}; skipped")
        return None
    return ARTICLES[topic]


def pageviews(topic, start=None, end=None):
    """{date: views} for every day from start to end (default: last 3 years to yesterday).

    Days Wikimedia has no row for are 0 (it omits days with no views).
    """
    mapping = article_for(topic)
    if mapping is None:
        return None
    project, title = mapping
    end = end or date.today() - timedelta(days=1)
    start = start or end - timedelta(days=3 * 365)
    CACHE.mkdir(parents=True, exist_ok=True)
    cache = CACHE / f"{project}_{title.replace(' ', '_')}.json"

    series = {}
    if cache.exists() and time.time() - cache.stat().st_mtime < 86400:
        series = json.loads(cache.read_text(encoding="utf-8"))
    if not series or min(series) > start.isoformat() or max(series) < end.isoformat():
        url = API.format(project=project, title=urllib.parse.quote(title.replace(" ", "_"), safe=""),
                         start=start.strftime("%Y%m%d"), end=end.strftime("%Y%m%d"))
        response = requests.get(url, headers=HEADERS, timeout=30)
        if response.status_code == 404:  # article younger than the range, or no views at all
            items = []
        else:
            response.raise_for_status()
            items = response.json()["items"]
        series = {f"{i['timestamp'][:4]}-{i['timestamp'][4:6]}-{i['timestamp'][6:8]}": i["views"] for i in items}
        cache.write_text(json.dumps(series, ensure_ascii=False), encoding="utf-8")

    days = (end - start).days + 1
    first = min(series) if series else end.isoformat()  # before the article existed: no data, not zero
    out = {}
    for d in range(days):
        day = (start + timedelta(days=d)).isoformat()
        if day >= first:
            out[day] = series.get(day, 0)
    return out
