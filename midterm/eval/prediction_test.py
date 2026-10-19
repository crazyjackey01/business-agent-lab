"""How accurate are the predictions? An out-of-sample holdout test.

Unlike the backtest summary, nothing about the forecaster is chosen on the data it is
scored on. For every topic and source:
  1. Forecasts are made at every origin using only data up to that origin.
  2. TRAINING origins (before the holdout) pick the model (lowest MAE) and the 80%
     interval: the 10th-90th percentile of actual/predicted on the most recent training
     origins (relative, so it scales when a topic gets busier). Leading zeros (before a
     term existed) are dropped first, or they would make the interval zero-wide.
  3. HOLDOUT origins (the most recent period, never used for any choice) score it:
       MAE, MASE vs naive (< 1 = better), MAPE,
       interval coverage (should be near 80% if the interval is honest),
       direction hit rate (up/down vs now) with a binomial test against a coin flip.

Sources and targets:
  google  - Google Trends weekly search interest (5 years); target = next week's index.
            Models: naive (this week), mean4, ses, seasonal (same week last year).
            Holdout = last 52 weeks.
  wiki    - Wikipedia daily pageviews (up to 3 years); target = sum of the next 7 days.
            Models: naive, mean28, ses, decay (eval/forecast.py). Holdout = last 180 days.

A worked example per topic shows one real forecast: made from data up to 2026-10-11
(Wikipedia) / the week of 2026-10-04 (Google), compared with what then happened.

Usage:
    python midterm/eval/prediction_test.py     # self-check, then data/eval/prediction_test.{md,json}
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # midterm/ modules
from eval.forecast import SES, backtest  # noqa: E402
from eval.gtrends import KEYWORDS, interest  # noqa: E402
from eval.wiki import ARTICLES, pageviews  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "data" / "eval"
GOOGLE_MODELS = ("naive", "mean4", "ses", "seasonal")
WIKI_MODELS = ("naive", "mean28", "ses", "decay")
HOLDOUT = {"google": 52, "wiki": 180}
EXAMPLE_ORIGIN = {"google": "2026-10-04", "wiki": "2026-10-11"}


# Forecast rows: one per origin, {t, now, actual, pred: {model: value}} ----------------

def google_rows(y):
    """Weekly series -> next-week forecasts at every origin with a year of history."""
    y = np.asarray(y, float)
    ses = SES(y)
    rows = []
    for t in range(52, len(y) - 1):
        rows.append({"t": t, "now": y[t], "actual": y[t + 1], "pred": {
            "naive": y[t], "mean4": y[t - 3:t + 1].mean(),
            "ses": ses.levels[int(np.argmin(ses.cum_sse[:, t])), t],
            "seasonal": y[t - 51]}})  # same week last year (the week after t, 52 weeks earlier)
    return rows


def wiki_rows(y):
    """Daily series -> next-7-day-sum forecasts (reuses the backtest in eval/forecast.py)."""
    _, rows = backtest(y)
    return [{"t": r["t"], "now": r["last7"], "actual": r["actual"], "pred": r["pred"]} for r in rows]


# Scoring ---------------------------------------------------------------------------

RECENT_TRAIN = {"google": 104, "wiki": 365}  # training origins used for the interval


def score(rows, model, interval=None):
    actual = np.array([r["actual"] for r in rows])
    now = np.array([r["now"] for r in rows])
    pred = np.array([r["pred"][model] for r in rows])
    naive_mae = np.mean(np.abs(actual - now))
    mae = float(np.mean(np.abs(actual - pred)))
    nonzero = actual != 0
    out = {"n": len(rows), "mae": round(mae, 2),
           "mase": round(mae / naive_mae, 3) if naive_mae else None,
           "mape": round(float(np.mean(np.abs(actual - pred)[nonzero] / actual[nonzero]) * 100), 1)
           if nonzero.any() else None}
    calls = np.sign(pred - now) != 0
    if calls.any():
        hits = int((np.sign(pred - now) == np.sign(actual - now))[calls].sum())
        out["direction"] = {"calls": int(calls.sum()), "hits": hits, "hit_rate": round(hits / calls.sum(), 3),
                            "p_vs_coin": round(float(stats.binomtest(hits, int(calls.sum()), 0.5,
                                                                     alternative="greater").pvalue), 4)}
    if interval:
        lo, hi = pred * interval[0], pred * interval[1]
        out["coverage_80"] = round(float(np.mean((actual >= lo) & (actual <= hi))), 3)
    return out


def holdout_test(rows, models, holdout, recent=None):
    """Choose model + interval on training rows, score them on the last `holdout` rows."""
    if len(rows) <= holdout + 20:
        return {"note": f"only {len(rows)} forecast origins; need more than {holdout + 20}"}
    train, test = rows[:-holdout], rows[-holdout:]
    train_mae = {m: score(train, m)["mae"] for m in models}
    chosen = min(models, key=train_mae.get)
    recent_rows = [r for r in train[-(recent or len(train)):] if r["pred"][chosen] > 0]
    ratios = np.array([r["actual"] / r["pred"][chosen] for r in recent_rows])
    interval = [float(q) for q in np.quantile(ratios, [0.1, 0.9])] if len(ratios) else [1.0, 1.0]
    return {
        "train_origins": len(train), "holdout_origins": len(test),
        "chosen_model": chosen, "train_mae": train_mae,
        "interval_ratio_from_training": [round(v, 3) for v in interval],
        "holdout": {**score(test, chosen, interval), "model": chosen},
        "holdout_all_models": {m: score(test, m) for m in models},
    }


def example(rows, dates, origin_date, chosen, interval):
    """The forecast made at a given origin, with its actual outcome."""
    for r in rows:
        if dates[r["t"]] == origin_date:
            p = r["pred"][chosen]
            return {"made_with_data_up_to": origin_date, "model": chosen, "predicted": round(float(p), 1),
                    "interval_80": [round(float(p * interval[0]), 1), round(float(p * interval[1]), 1)],
                    "actual": float(r["actual"]), "naive_predicted": float(r["pred"]["naive"])}
    return None


def run_source(source, series):
    dates = sorted(series)
    first = next((i for i, d in enumerate(dates) if series[d] > 0), 0)  # drop the years before the term existed
    dates = dates[first:]
    y = [series[d] for d in dates]
    rows = google_rows(y) if source == "google" else wiki_rows(y)
    models = GOOGLE_MODELS if source == "google" else WIKI_MODELS
    result = holdout_test(rows, models, HOLDOUT[source], RECENT_TRAIN[source])
    if "note" not in result:
        result["example"] = example(rows, dates, EXAMPLE_ORIGIN[source], result["chosen_model"],
                                    result["interval_ratio_from_training"])
    result["history"] = f"{dates[0]}..{dates[-1]} ({len(dates)} points)"
    return result


# Self-check ---------------------------------------------------------------------------

def self_check():
    rng = np.random.default_rng(3)
    # Noise around a constant: a forecaster that knows the level has an honest interval
    # (coverage near 80%) and beats naive (MASE < 1).
    y = 50 + rng.normal(0, 5, 400)
    rows = [{"t": t, "now": y[t], "actual": y[t + 1], "pred": {"naive": y[t], "level": 50.0}} for t in range(399)]
    r = holdout_test(rows, ("naive", "level"), 150)
    assert r["chosen_model"] == "level", r
    assert abs(r["holdout"]["coverage_80"] - 0.8) < 0.1, r["holdout"]
    assert r["holdout"]["mase"] < 1, r["holdout"]
    # Direction hits on a series that always moves the predicted way: p-value tiny.
    up = [{"t": t, "now": 0.0, "actual": 1.0, "pred": {"m": 1.0}} for t in range(30)]
    assert score(up, "m")["direction"]["p_vs_coin"] < 1e-6
    assert "note" in holdout_test(rows[:100], ("naive", "level"), 150)


# Report --------------------------------------------------------------------------------

def to_markdown(results):
    lines = ["| source | topic | model (chosen on training) | holdout n | MAE | MASE vs naive | MAPE | "
             "80% interval coverage | direction hit (p vs coin) |", "|---|---|---|---|---|---|---|---|---|"]
    for source, topics in results.items():
        for topic, r in topics.items():
            if "note" in r:
                lines.append(f"| {source} | {topic} | {r['note']} | | | | | | |")
                continue
            h = r["holdout"]
            d = h.get("direction")
            direction = f"{d['hit_rate']:.0%} (p={d['p_vs_coin']})" if d else "-"
            lines.append(f"| {source} | {topic} | {h['model']} | {h['n']} | {h['mae']} | {h['mase']} | "
                         f"{h['mape']}% | {h['coverage_80']:.0%} | {direction} |")
    lines += ["", "Worked examples (one real forecast each):", "",
              "| source | topic | data up to | model | predicted | 80% interval | actual | naive predicted |",
              "|---|---|---|---|---|---|---|---|"]
    for source, topics in results.items():
        for topic, r in topics.items():
            e = r.get("example")
            if e:
                lines.append(f"| {source} | {topic} | {e['made_with_data_up_to']} | {e['model']} | {e['predicted']} | "
                             f"{e['interval_80'][0]}–{e['interval_80'][1]} | {e['actual']} | {e['naive_predicted']} |")
    return "\n".join(lines)


def main():
    self_check()
    print("self-check ok\n")
    results = {"google": {}, "wiki": {}}
    for topic in KEYWORDS:
        results["google"][topic] = run_source("google", interest(topic, "weekly"))
    for topic in ARTICLES:
        results["wiki"][topic] = run_source("wiki", pageviews(topic))
    for source, topics in results.items():
        for topic, r in topics.items():
            if "note" in r:
                print(f"{source:6} {topic:12} {r['note']}")
                continue
            h, d = r["holdout"], r["holdout"].get("direction") or {}
            print(f"{source:6} {topic:12} {h['model']:8} n={h['n']:3}  MASE {h['mase']}  MAPE {h['mape']}%  "
                  f"coverage {h['coverage_80']:.0%}  direction {d.get('hit_rate', '-')} (p={d.get('p_vs_coin', '-')})")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "prediction_test.json").write_text(json.dumps(
        {"made_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "results": results},
        ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    (OUT / "prediction_test.md").write_text(to_markdown(results) + "\n", encoding="utf-8")
    print("\nSaved data/eval/prediction_test.json and .md")


if __name__ == "__main__":
    main()
