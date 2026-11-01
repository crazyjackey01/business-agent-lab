"""Next week's Google search interest: forecast by code, checked by code a week later. No model involved.

Each analysis logs one forecast (data/predictions.jsonl). The topic's 5 years of weekly Google
Trends data pick the method with the smallest past error (same as last week, 4-week mean,
exponential smoothing, same week last year) and a range: the 10th-90th percentile of
actual/predicted over the last two years. A forecast is up / down (more than 10% from this week)
or flat.

Once the week is over, this week and the forecast week are compared as daily averages from one
Trends response, because Trends rescales its index per request. Reported: direction hits, range
hits, and the hits from always saying "flat" ("same as last week"), since a forecast is only
worth something if it beats that.

Usage:
    python midterm/eval/score_predictions.py     # self-check, then data/eval/scored_predictions.json
"""
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # midterm/ modules
from eval.forecast import SES  # noqa: E402
from eval.gtrends import interest  # noqa: E402
from eval.prediction_test import GOOGLE_MODELS, RECENT_TRAIN, google_forecasts, google_rows, score  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"
PREDICTIONS = DATA / "predictions.jsonl"
OUT = DATA / "eval" / "scored_predictions.json"
WEEK_DAYS = 7
FLAT_BAND = 0.10  # within 10% counts as "flat"
MIN_ORIGINS = 26  # past forecasts needed to choose a method and a range


def direction_of(before, after):
    """up / flat / down for after compared with before."""
    if before == 0:
        return "up" if after > 0 else "flat"
    change = (after - before) / before
    return "up" if change > FLAT_BAND else "down" if change < -FLAT_BAND else "flat"


def forecast_from(series):
    """{method, direction, change range, week} from {week start: index}, or {"note"} if history is short."""
    dates = sorted(series)
    first = next((i for i, d in enumerate(dates) if series[d] > 0), None)
    if first is None:
        return {"note": "no search interest in Google Trends"}
    dates = dates[first:]
    y = np.array([series[d] for d in dates], float)
    if len(y) < 52 + 1 + MIN_ORIGINS or y[-1] == 0:
        return {"note": "too little search history"}
    rows = google_rows(y)
    method = min(GOOGLE_MODELS, key=lambda m: score(rows, m)["mae"])
    recent = [r for r in rows[-RECENT_TRAIN["google"]:] if r["pred"][method] > 0]
    low, high = np.quantile([r["actual"] / r["pred"][method] for r in recent], [0.1, 0.9])
    point = float(google_forecasts(y, SES(y), len(y) - 1)[method])
    now = float(y[-1])
    return {"method": method, "direction": direction_of(now, point),
            "change": round(point / now - 1, 3), "change_low": round(float(point * low / now - 1), 3),
            "change_high": round(float(point * high / now - 1), 3),
            "week_start": (date.fromisoformat(dates[-1]) + timedelta(days=WEEK_DAYS)).isoformat(), "week_days": WEEK_DAYS}


def log_prediction(topic, geo, made_at):
    prediction = {"topic": topic, "geo": geo, "made_at": made_at, **forecast_from(interest(topic, "weekly", geo) or {})}
    if "direction" in prediction:
        with PREDICTIONS.open("a", encoding="utf-8") as f:
            f.write(json.dumps(prediction, ensure_ascii=False) + "\n")
    return prediction


def score_week(prediction, series):
    """A scored copy of the prediction against one daily series, or None if the week is not in the data yet."""
    start, days = date.fromisoformat(prediction["week_start"]), prediction["week_days"]
    after = [(start + timedelta(days=d)).isoformat() for d in range(days)]
    before = [(start - timedelta(days=days - d)).isoformat() for d in range(days)]
    if not series or max(series) < after[-1]:
        return None
    if any(d not in series for d in before + after):
        return {**prediction, "actual": None, "actual_change": None, "hit": None, "flat_hit": None, "in_range": None}
    b, a = float(np.mean([series[d] for d in before])), float(np.mean([series[d] for d in after]))
    actual = direction_of(b, a)
    change = round(a / b - 1, 3) if b else None
    return {**prediction, "actual": actual, "actual_change": change, "hit": actual == prediction["direction"],
            "flat_hit": actual == "flat",
            "in_range": None if change is None else prediction["change_low"] <= change <= prediction["change_high"]}


def totals(scored):
    done = [p for p in scored if p["hit"] is not None]
    ranged = [p for p in done if p["in_range"] is not None]
    return {"scored": len(done), "hits": sum(p["hit"] for p in done), "flat_hits": sum(p["flat_hit"] for p in done),
            "ranged": len(ranged), "in_range": sum(p["in_range"] for p in ranged)}


def self_check():
    assert direction_of(10, 12) == "up" and direction_of(10, 10.5) == "flat" and direction_of(10, 8) == "down"
    assert direction_of(0, 0) == "flat" and direction_of(0, 1) == "up"
    # A steady series: the forecast is flat, its range holds "no change".
    weeks = {(date(2024, 1, 7) + timedelta(weeks=w)).isoformat(): 50 + (w % 3) for w in range(120)}
    f = forecast_from(weeks)
    assert f["direction"] == "flat" and f["change_low"] <= 0 <= f["change_high"], f
    assert f["week_start"] == (date(2024, 1, 7) + timedelta(weeks=120)).isoformat()
    assert "note" in forecast_from({"2026-01-04": 10, "2026-01-11": 12})
    assert "note" in forecast_from({"2026-01-04": 0})
    # Leading zeros (before the term existed) don't count as history.
    assert "note" in forecast_from({(date(2024, 1, 7) + timedelta(weeks=w)).isoformat(): 0 if w < 100 else 5 for w in range(120)})
    # Scoring: this week averages 10, the forecast week 20.
    p = {"direction": "up", "change_low": 0.5, "change_high": 1.5, "week_start": "2026-01-08", "week_days": 7}
    series = {(date(2026, 1, 1) + timedelta(days=d)).isoformat(): (10 if d < 7 else 20) for d in range(14)}
    r = score_week(p, series)
    assert r["actual"] == "up" and r["hit"] and not r["flat_hit"] and r["in_range"] and r["actual_change"] == 1.0
    assert score_week(p, {k: v for k, v in series.items() if k < "2026-01-14"}) is None  # week not over
    assert totals([r]) == {"scored": 1, "hits": 1, "flat_hits": 0, "ranged": 1, "in_range": 1}


def main():
    self_check()
    rows = [json.loads(line) for line in PREDICTIONS.read_text(encoding="utf-8").splitlines() if line.strip()] if PREDICTIONS.exists() else []
    today = datetime.now().date()
    scored, pending = [], []
    for p in rows:
        end = date.fromisoformat(p["week_start"]) + timedelta(days=p["week_days"])
        r = score_week(p, interest(p["topic"], "daily", p["geo"])) if today >= end else None
        (scored if r else pending).append(r or p)
    for p in scored:
        print(f"{p['topic']:12} week of {p['week_start']}: said {p['direction']}, actual {p['actual']} ({p['actual_change']})")
    summary = totals(scored)
    print(f"\n{len(scored)} scored, {len(pending)} pending; {summary}")
    OUT.write_text(json.dumps({"totals": summary, "scored": scored, "pending": pending}, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
