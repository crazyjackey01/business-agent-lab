"""Did what the analyses said will happen come true? Checked by code, a week later.

Every analysis logs its own forecasts (data/predictions.jsonl; the Cloudflare version keeps
them in KV and serves them at /api/predictions):
  - each "what is next" sentence comes with a test: at least min_articles Google News
    articles matching query in the 7 days after the analysis. The same count for the 7 days
    before shows whether the bar was already met, i.e. whether it was an easy forecast.
  - search_interest: Google search interest in the topic, next 7 days vs last 7 days, up /
    down (more than 10% apart) or flat. Compared with always saying "flat" ("same as last
    week"), because a forecast is only worth something if it beats that.

Both sides of a comparison come from one Trends response, because Trends rescales its index
per request. A prediction stays pending until its week is over in the data.

Usage:
    python midterm/eval/score_predictions.py     # self-check, then data/eval/scored_predictions.json
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # midterm/ modules
from eval.gtrends import interest  # noqa: E402
from topic_trends import fetch_news, is_spam  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"
PREDICTIONS = DATA / "predictions.jsonl"
OUT = DATA / "eval" / "scored_predictions.json"
WORKER_URL = "https://trend-signals.gimailft01.workers.dev/api/predictions"
WINDOW_DAYS = 7
FLAT_BAND = 0.10  # within 10% counts as "flat"
DIRECTIONS = ("up", "flat", "down")


def prediction_from(analysis):
    """What an analysis said will happen, in checkable form, or None if it said nothing checkable."""
    e = analysis.get("explanation") or {}
    tests = []
    for c in e.get("outlook") or []:
        test = c.get("test") or {}
        if test.get("query") and isinstance(test.get("min_articles"), int) and test["min_articles"] > 0:
            tests.append({"claim": c["claim"], "confidence": c.get("confidence"), "query": str(test["query"]),
                          "min_articles": test["min_articles"]})
    si = e.get("search_interest") or {}
    search = {"direction": si["direction"], "confidence": si.get("confidence")} if si.get("direction") in DIRECTIONS else None
    if not tests and not search:
        return None
    made = datetime.fromisoformat(analysis["analyzed_at"])
    return {"topic": analysis["topic"], "geo": analysis["geo"], "made_at": analysis["analyzed_at"],
            "window_start": (made.date() + timedelta(days=1)).isoformat(), "window_days": WINDOW_DAYS,
            "search_interest": search, "tests": tests}


def log_prediction(analysis):
    prediction = prediction_from(analysis)
    if prediction:
        with PREDICTIONS.open("a", encoding="utf-8") as f:
            f.write(json.dumps(prediction, ensure_ascii=False) + "\n")
    return prediction


def window_days(start, days):
    return [start + timedelta(days=d) for d in range(days)]


def direction_of(before, after):
    """up / flat / down for the average of `after` compared with the average of `before`."""
    b, a = sum(before) / len(before), sum(after) / len(after)
    if b == 0:
        return "up" if a > 0 else "flat"
    change = (a - b) / b
    return "up" if change > FLAT_BAND else "down" if change < -FLAT_BAND else "flat"


def score_interest(forecast, start, days, series):
    """The direction call against one Trends series, or None if the week is not in the data yet."""
    after = [d.isoformat() for d in window_days(start, days)]
    before = [d.isoformat() for d in window_days(start - timedelta(days=days), days)]
    if not series or max(series) < after[-1]:
        return None
    if any(d not in series for d in before + after):
        return {**forecast, "actual": None, "hit": None, "flat_hit": None}
    actual = direction_of([series[d] for d in before], [series[d] for d in after])
    return {**forecast, "actual": actual, "hit": actual == forecast["direction"], "flat_hit": actual == "flat"}


def count_articles(query, topic, lang, geo, start, days):
    """Articles matching query published in the window, one query per day (each returns at most 100)."""
    def one_day(day):
        found = fetch_news(f"{query} after:{day - timedelta(days=1)} before:{day + timedelta(days=1)}", lang, geo)
        return [a for a in found if a["published"][:10] == day.isoformat() and not is_spam(a["title"], topic)], len(found) >= 100

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(one_day, window_days(start, days)))
    return len({a["url"] for articles, _ in results for a in articles}), any(capped for _, capped in results)


def score_test(test, count, last_week, capped):
    return {**test, "count": count, "last_week": last_week, "capped": capped, "passed": count >= test["min_articles"],
            "already_met": last_week >= test["min_articles"]}


def score(prediction, today):
    """A scored copy of the prediction, or None while its week is not over."""
    start = date.fromisoformat(prediction["window_start"])
    days = prediction["window_days"]
    if today < start + timedelta(days=days):
        return None
    geo = prediction["geo"]
    lang = "ko" if geo == "KR" else "en"
    search = prediction.get("search_interest")
    if search:
        search = score_interest(search, start, days, interest(prediction["topic"], "daily", geo))
        if search is None:
            return None
    tests = []
    for test in prediction.get("tests") or []:
        count, capped = count_articles(test["query"], prediction["topic"], lang, geo, start, days)
        last_week, capped_before = count_articles(test["query"], prediction["topic"], lang, geo, start - timedelta(days=days), days)
        tests.append(score_test(test, count, last_week, capped or capped_before))
    return {**prediction, "search_interest": search, "tests": tests}


def totals(scored):
    tests = [t for p in scored for t in p["tests"]]
    calls = [p["search_interest"] for p in scored if p.get("search_interest") and p["search_interest"]["hit"] is not None]
    return {"tests": len(tests), "tests_passed": sum(t["passed"] for t in tests),
            "tests_already_met": sum(t["already_met"] for t in tests),
            "search_calls": len(calls), "search_hits": sum(c["hit"] for c in calls),
            "search_flat_hits": sum(c["flat_hit"] for c in calls)}


def all_predictions():
    """The local log plus what the Cloudflare version logged."""
    rows = [json.loads(line) for line in PREDICTIONS.read_text(encoding="utf-8").splitlines() if line.strip()] if PREDICTIONS.exists() else []
    try:
        response = requests.get(WORKER_URL, timeout=30)
        response.raise_for_status()
        rows += response.json()
    except (requests.RequestException, ValueError) as error:
        print(f"could not read the Cloudflare predictions: {error}")
    return list({(p["topic"], p["geo"], p["made_at"]): p for p in rows}.values())


def self_check():
    assert direction_of([10, 10], [12, 12]) == "up"
    assert direction_of([10, 10], [10.5, 10.5]) == "flat"
    assert direction_of([10, 10], [8, 8]) == "down"
    assert direction_of([0, 0], [0, 0]) == "flat" and direction_of([0, 0], [1, 0]) == "up"
    start = date(2026, 1, 8)
    series = {(date(2026, 1, 1) + timedelta(days=d)).isoformat(): (10 if d < 7 else 20) for d in range(14)}
    r = score_interest({"direction": "up"}, start, 7, series)
    assert r["actual"] == "up" and r["hit"] is True and r["flat_hit"] is False
    assert score_interest({"direction": "up"}, start, 8, series) is None  # week not in the data yet
    t = score_test({"min_articles": 10}, 12, 15, False)
    assert t["passed"] is True and t["already_met"] is True
    assert score_test({"min_articles": 10}, 9, 2, False)["passed"] is False
    analysis = {"topic": "x", "geo": "KR", "analyzed_at": "2026-01-07T12:00:00+00:00", "explanation": {
        "search_interest": {"direction": "sideways"},
        "outlook": [{"claim": "a", "test": {"query": "q", "min_articles": 5}}, {"claim": "b", "test": {"query": "q", "min_articles": "many"}},
                    {"claim": "c"}]}}
    p = prediction_from(analysis)
    assert p["window_start"] == "2026-01-08" and [c["claim"] for c in p["tests"]] == ["a"] and p["search_interest"] is None
    assert prediction_from({"explanation": {"outlook": [{"claim": "c"}]}}) is None
    assert totals([{"tests": [t], "search_interest": r}])["search_hits"] == 1


def main():
    self_check()
    today = datetime.now().date()
    scored, pending = [], []
    for p in all_predictions():
        r = score(p, today)
        (scored if r else pending).append(r or p)
    for p in scored:
        s = p.get("search_interest")
        if s:
            print(f"{p['topic']:12} {p['window_start']} search: said {s['direction']}, actual {s['actual']}")
        for t in p["tests"]:
            print(f"{p['topic']:12} {p['window_start']} {'PASS' if t['passed'] else 'FAIL'} {t['query']!r} >= {t['min_articles']}: "
                  f"{t['count']} (week before: {t['last_week']})")
    summary = totals(scored)
    print(f"\n{len(scored)} scored, {len(pending)} pending; {summary}")
    OUT.write_text(json.dumps({"totals": summary, "scored": scored, "pending": pending}, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
