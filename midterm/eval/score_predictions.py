"""Score logged predictions whose 7-day window has ended.

Reads data/predictions.jsonl (one line per prediction, written by every live analysis),
fetches the actual Wikipedia pageviews for each finished window, and reports the error,
whether the actual fell inside the 80% interval, and the overall hit rate. Results go to
data/eval/scored_predictions.json. Predictions whose window has not ended are listed as
pending.

Usage:
    python midterm/eval/score_predictions.py
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # midterm/ modules
from eval.forecast import PREDICTIONS  # noqa: E402
from eval.wiki import pageviews  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "data" / "eval" / "scored_predictions.json"


def score(prediction, views):
    """Error and interval hit for one prediction, or None if its window has not ended."""
    start = date.fromisoformat(prediction["window_start"])
    days = [(start + timedelta(days=d)).isoformat() for d in range(prediction["window_days"])]
    if any(d not in views for d in days):
        return None
    actual = sum(views[d] for d in days)
    inside = None if prediction["low"] is None else prediction["low"] <= actual <= prediction["high"]
    return {**prediction, "actual": actual, "error": round(actual - prediction["point"], 1),
            "abs_pct_error": round(abs(actual - prediction["point"]) / actual * 100, 1) if actual else None,
            "inside_interval": inside}


def self_check():
    p = {"window_start": "2026-01-01", "window_days": 2, "point": 10, "low": 8, "high": 12}
    r = score(p, {"2026-01-01": 5, "2026-01-02": 6})
    assert r["actual"] == 11 and r["error"] == 1 and r["inside_interval"] is True
    assert score(p, {"2026-01-01": 5}) is None  # window not over yet


def main():
    self_check()
    if not PREDICTIONS.exists():
        print("no predictions logged yet (data/predictions.jsonl is created by live analyses)")
        return
    rows = [json.loads(line) for line in PREDICTIONS.read_text(encoding="utf-8").splitlines() if line.strip()]
    scored, pending, views_by_topic = [], [], {}
    for p in rows:
        if p["topic"] not in views_by_topic:
            views_by_topic[p["topic"]] = pageviews(p["topic"]) or {}
        r = score(p, views_by_topic[p["topic"]])
        (scored if r else pending).append(r or p)
    for r in scored:
        print(f"{r['topic']:12} {r['window_start']} +{r['window_days']}d  predicted {r['point']:8.0f} "
              f"[{r['low']}, {r['high']}]  actual {r['actual']:6}  {'inside' if r['inside_interval'] else 'OUTSIDE'}")
    hits = [r["inside_interval"] for r in scored if r["inside_interval"] is not None]
    print(f"\n{len(scored)} scored, {len(pending)} pending"
          + (f"; {sum(hits)}/{len(hits)} inside their 80% interval" if hits else ""))
    OUT.write_text(json.dumps({"scored": scored, "pending": pending}, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
