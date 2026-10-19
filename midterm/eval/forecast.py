"""Forecast the next 7 days of Wikipedia pageviews, and backtest the forecasts.

Target: the sum of pageviews over the next 7 days. Four models, each using only data
up to the forecast day:
  naive   - the last 7 days repeated
  mean28  - the 28-day mean, times 7
  ses     - simple exponential smoothing; alpha chosen at each origin by the one-step
            squared error on the history so far (no look-ahead)
  decay   - after a detected spike (negative binomial test, p < 0.01, vs the 28 days
            before it, peak within the last 14 days, at least 2 days after the peak):
            exponential decay of the excess toward the pre-spike median, half-life fit
            on the post-peak days. Without a recent spike it is the ses forecast.

Rolling-origin backtest: every day t (step 1) over up to the last 2 years, forecast from
data up to t, score against the actual sum of t+1..t+7. Metrics per model and topic:
  MAE      - mean absolute error of the 7-day sum
  MASE     - MAE / naive MAE on the same origins (< 1 = better than naive)
  dir hit  - share of origins where the predicted direction (vs the last 7 days) matches
             the actual one; naive always predicts "flat", so it has none
  half-life error - after spikes: |predicted - actual half-life| in days

Usage:
    python midterm/eval/forecast.py          # self-check, backtest every demo topic
"""
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # midterm/ modules
from eval.spike import spike_test  # noqa: E402
from eval.wiki import ARTICLES, pageviews  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "data" / "eval"
PREDICTIONS = HERE.parent / "data" / "predictions.jsonl"
H = 7                      # forecast window, days
WARMUP = 56                # history needed before the first origin
MAX_ORIGINS = 730          # backtest at most the last 2 years
ALPHAS = np.round(np.arange(0.05, 1.0, 0.05), 2)
SPIKE_LOOKBACK = 14        # a spike counts if its peak is within this many days
MODELS = ("naive", "mean28", "ses", "decay")


# Exponential smoothing -------------------------------------------------------

def ses_levels(y, alpha):
    """Level after each day, and the one-step error made before seeing that day."""
    levels, errors = np.empty(len(y)), np.empty(len(y))
    level = y[0]
    for i, v in enumerate(y):
        errors[i] = v - level
        level = alpha * v + (1 - alpha) * level
        levels[i] = level
    return levels, errors


class SES:
    """All alphas run once over the series; at origin t the alpha with the lowest
    one-step squared error on days 0..t is used (only past data)."""

    def __init__(self, y):
        runs = [ses_levels(y, a) for a in ALPHAS]
        self.levels = np.array([r[0] for r in runs])
        self.cum_sse = np.cumsum(np.array([r[1] ** 2 for r in runs]), axis=1)

    def forecast(self, t):
        best = int(np.argmin(self.cum_sse[:, t]))
        return self.levels[best, t] * H, float(ALPHAS[best])


# Spikes and decay --------------------------------------------------------------

def spike_days(y):
    """Boolean per day: a spike (p < 0.01) against the 28 days before it."""
    flags = np.zeros(len(y), bool)
    for i in range(28, len(y)):
        base = y[i - 28:i]
        if base.sum() > 0 and y[i] > np.median(base):
            flags[i] = spike_test(int(y[i]), base)["verdict"] == "spike"
    return flags


def fit_half_life(excess):
    """Half-life (days) from post-peak excess values by a log-linear fit; None if not decaying."""
    k = np.arange(len(excess))
    ok = excess > 0
    if ok.sum() < 2:
        return None
    slope = np.polyfit(k[ok], np.log(excess[ok]), 1)[0]
    return None if slope >= 0 else float(np.log(2) / -slope)


def actual_half_life(y, peak, baseline, horizon=60):
    """Days after the peak until the excess first falls to half of the peak excess."""
    peak_excess = y[peak] - baseline
    for k in range(1, min(horizon, len(y) - peak)):
        if y[peak + k] - baseline <= peak_excess / 2:
            return k
    return None


def recent_peak(y, flags, t):
    """The highest flagged spike day in the last SPIKE_LOOKBACK days with >= 2 days after it."""
    window = [i for i in range(max(28, t - SPIKE_LOOKBACK), t - 1) if flags[i]]
    return max(window, key=lambda i: y[i]) if window else None


def decay_forecast(y, t, peak):
    baseline = float(np.median(y[peak - 28:peak]))
    excess = y[peak:t + 1] - baseline
    half_life = fit_half_life(excess)
    if half_life is None:
        return None, None, baseline
    rate = np.log(2) / half_life
    days_after = np.arange(t - peak + 1, t - peak + 1 + H)
    return float(np.sum(baseline + (y[peak] - baseline) * np.exp(-rate * days_after))), half_life, baseline


# Backtest ------------------------------------------------------------------------

def backtest(y):
    """Rolling-origin backtest on one daily series. Returns metrics and per-model errors."""
    y = np.asarray(y, float)
    ses, flags = SES(y), spike_days(y)
    first = max(WARMUP, len(y) - H - MAX_ORIGINS)
    rows = []
    for t in range(first, len(y) - H):
        last7 = y[t - H + 1:t + 1].sum()
        actual = y[t + 1:t + 1 + H].sum()
        pred = {"naive": last7, "mean28": y[t - 27:t + 1].mean() * H, "ses": ses.forecast(t)[0]}
        pred["decay"], half_life, peak = pred["ses"], None, recent_peak(y, flags, t)
        if peak is not None:
            d, half_life, baseline = decay_forecast(y, t, peak)
            if d is not None:
                pred["decay"] = d
                true_hl = actual_half_life(y, peak, baseline)
                half_life = None if true_hl is None else abs(half_life - true_hl)
        rows.append({"t": t, "last7": last7, "actual": actual, "pred": pred,
                     "post_spike": peak is not None, "half_life_error": half_life})
    return summarize(rows), rows


def summarize(rows):
    def metrics(subset):
        if not subset:
            return None
        actual = np.array([r["actual"] for r in subset])
        last7 = np.array([r["last7"] for r in subset])
        naive_mae = np.mean(np.abs(actual - last7))
        out = {}
        for m in MODELS:
            pred = np.array([r["pred"][m] for r in subset])
            mae = float(np.mean(np.abs(actual - pred)))
            calls = np.sign(pred - last7) != 0
            hit = np.sign(pred - last7) == np.sign(actual - last7)
            out[m] = {"mae": round(mae, 1),
                      "mase": round(mae / naive_mae, 3) if naive_mae else None,
                      "direction_hit": round(float(hit[calls].mean()), 3) if calls.any() else None,
                      # relative error quantiles give the prediction interval used in live forecasts
                      "ratio_q10_q90": [round(float(q), 3) for q in np.quantile(
                          actual[pred > 0] / pred[pred > 0], [0.1, 0.9])] if (pred > 0).any() else None}
        return out

    post = [r for r in rows if r["post_spike"]]
    hl = [r["half_life_error"] for r in post if r["half_life_error"] is not None]
    return {
        "origins": len(rows),
        "all": metrics(rows),
        "post_spike_origins": len(post),
        "post_spike": metrics(post),
        "half_life_error_days": {"n": len(hl), "median": round(float(np.median(hl)), 1) if hl else None,
                                 "mean": round(float(np.mean(hl)), 1) if hl else None},
    }


# Live forecast + prediction log ---------------------------------------------------

def best_model(topic):
    """The model with the lowest MASE in the latest backtest (ses if none yet)."""
    files = sorted(OUT.glob("backtest_*.json"))
    if not files:
        return "ses", None
    result = json.loads(files[-1].read_text(encoding="utf-8"))["topics"].get(topic)
    if not result or not result["all"]:
        return "ses", None
    model = min(MODELS, key=lambda m: result["all"][m]["mase"])  # naive included: it is often best
    return model, result["all"][model]["ratio_q10_q90"]


def forecast_now(topic):
    """One falsifiable prediction: next 7 days' pageviews, with an 80% interval from the backtest."""
    views = pageviews(topic)
    if not views:
        return None
    days = sorted(views)
    y = np.array([views[d] for d in days], float)
    model, ratio = best_model(topic)
    t = len(y) - 1
    if model == "naive":
        point = y[-H:].sum()
    elif model == "mean28":
        point = y[-28:].mean() * H
    else:
        point = SES(y).forecast(t)[0]
        if model == "decay":
            peak = recent_peak(y, spike_days(y), t)
            if peak is not None:
                point = decay_forecast(y, t, peak)[0] or point
    low, high = (point * ratio[0], point * ratio[1]) if ratio else (None, None)
    start = date.fromisoformat(days[-1]) + timedelta(days=1)
    return {
        "topic": topic,
        "made_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "metric": "wikipedia_pageviews_sum:" + "/".join(ARTICLES[topic]),
        "window_start": start.isoformat(), "window_days": H,
        "point": round(float(point), 1),
        "low": None if low is None else round(float(low), 1),
        "high": None if high is None else round(float(high), 1),
        "model": model,
    }


def log_prediction(topic):
    """Append today's prediction for a topic to data/predictions.jsonl (skips unmapped topics)."""
    if topic not in ARTICLES:
        return None
    prediction = forecast_now(topic)
    if prediction:
        with PREDICTIONS.open("a", encoding="utf-8") as f:
            f.write(json.dumps(prediction, ensure_ascii=False) + "\n")
    return prediction


# Self-check and report --------------------------------------------------------------

def self_check():
    # A pure decay with half-life 3 days is recovered exactly.
    excess = 100 * 0.5 ** (np.arange(6) / 3)
    assert abs(fit_half_life(excess) - 3) < 1e-6
    # On a constant series every model is exact; SES with any alpha stays on the level.
    y = np.full(120, 10.0)
    summary, _ = backtest(y)
    assert all(summary["all"][m]["mae"] == 0 for m in MODELS), summary
    # A spike that halves every 2 days: the decay model beats naive after it.
    rng = np.random.default_rng(1)
    y = rng.poisson(20, 200).astype(float)
    y[150:] += 400 * 0.5 ** (np.arange(50) / 2)
    summary, _ = backtest(y)
    assert summary["post_spike"]["decay"]["mae"] < summary["post_spike"]["naive"]["mae"], summary["post_spike"]
    assert summary["half_life_error_days"]["median"] is not None


def to_markdown(results):
    lines = ["| topic | days | origins | model | MAE | MASE | dir hit | post-spike MASE |",
             "|---|---|---|---|---|---|---|---|"]
    for topic, r in results.items():
        if r.get("note"):
            lines.append(f"| {topic} | {r['days']} | - | {r['note']} | | | | |")
            continue
        for m in MODELS:
            a, p = r["all"][m], (r["post_spike"] or {}).get(m)
            lines.append(f"| {topic} | {r['days']} | {r['origins']} | {m} | {a['mae']} | {a['mase']} | "
                         f"{'-' if a['direction_hit'] is None else a['direction_hit']} | "
                         f"{'-' if not p else p['mase']} |")
    lines.append("")
    lines.append("Half-life error after spikes (decay model, days): " + ", ".join(
        f"{t} median {r['half_life_error_days']['median']} (n={r['half_life_error_days']['n']})"
        for t, r in results.items() if not r.get("note")))
    return "\n".join(lines)


def main():
    self_check()
    print("self-check ok\n")
    results = {}
    for topic in ARTICLES:
        views = pageviews(topic)
        y = [views[d] for d in sorted(views)]
        if len(y) < WARMUP + H + 30:
            results[topic] = {"days": len(y), "note": "history too short"}
            continue
        summary, _ = backtest(y)
        summary["days"] = len(y)
        summary["under_two_years"] = len(y) < 730
        results[topic] = summary
        best = min(MODELS, key=lambda m: summary["all"][m]["mase"])
        print(f"{topic:12} {len(y):4} days, {summary['origins']} origins | " + " | ".join(
            f"{m} MASE {summary['all'][m]['mase']}" for m in MODELS[1:]) + f" | best {best}"
            + (" | UNDER 2 YEARS" if summary["under_two_years"] else ""))
    stamp = date.today().isoformat()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"backtest_{stamp}.json").write_text(json.dumps(
        {"made_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "topics": results},
        ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / f"backtest_{stamp}.md").write_text(to_markdown(results) + "\n", encoding="utf-8")
    print(f"\nSaved data/eval/backtest_{stamp}.json and .md")


if __name__ == "__main__":
    main()
