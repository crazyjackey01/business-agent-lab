"""Is today's news count a real spike? A negative binomial test instead of a ratio.

Daily article counts are overdispersed (the variance is far above the mean), so a
Poisson test calls almost every busy day a spike. The baseline days (today excluded)
are fit with a negative binomial by the method of moments:
    p = mean / var,   r = mean * p / (1 - p)
and the p-value is P(X >= today). If var <= mean the counts are not overdispersed and
Poisson is used instead.

Verdict: "spike" if p < 0.01, "elevated" if p < 0.05, else "normal". If today or any
baseline day hit Google News' 100-article limit, the counts are minimums and the
verdict is "uncertain (capped)".

Usage:
    python midterm/eval/spike.py            # self-check, then every saved topic
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy import stats

HERE = Path(__file__).resolve().parent
TOPICS_DIR = HERE.parent / "data" / "topics"

SPIKE_P, ELEVATED_P = 0.01, 0.05


def fit_baseline(baseline):
    """Method-of-moments fit. Returns ("negative binomial", r, p) or ("poisson", mean, None)."""
    baseline = np.asarray(baseline, dtype=float)
    mean, var = baseline.mean(), baseline.var(ddof=1)  # sample variance
    if var <= mean:
        return "poisson", mean, None
    p = mean / var
    return "negative binomial", mean * p / (1 - p), p


def tail_p(today, baseline):
    """P(X >= today) under the fitted baseline distribution."""
    model, a, b = fit_baseline(baseline)
    if model == "poisson":
        return model, float(stats.poisson.sf(today - 1, a))
    return model, float(stats.nbinom.sf(today - 1, a, b))


def robust_z(today, baseline):
    """(today - median) / (1.4826 * MAD); None when the baseline has no spread."""
    baseline = np.asarray(baseline, dtype=float)
    median = np.median(baseline)
    mad = np.median(np.abs(baseline - median))
    return None if mad == 0 else float((today - median) / (1.4826 * mad))


def spike_test(today, baseline, capped=None):
    """Test one count against its baseline.

    capped: optional list of booleans, today first then the baseline days, True where
    the count hit Google News' 100-article limit.
    """
    baseline = [int(x) for x in baseline]
    model, p_value = tail_p(today, baseline)
    if capped and any(capped[: len(baseline) + 1]):
        verdict = "uncertain (capped)"
    elif p_value < SPIKE_P:
        verdict = "spike"
    elif p_value < ELEVATED_P:
        verdict = "elevated"
    else:
        verdict = "normal"
    return {
        "today": int(today),
        "baseline": baseline,
        "baseline_mean": round(float(np.mean(baseline)), 2),
        "baseline_variance": round(float(np.var(baseline, ddof=1)), 2),
        "model": model,
        "p_value": p_value,
        "robust_z": robust_z(today, baseline),
        "verdict": verdict,
    }


def self_check():
    """The stored 전기차 run: Poisson says spike, the overdispersion-aware test says normal."""
    today, baseline = 72, [38, 49, 68, 27, 50, 15]
    poisson_p = float(stats.poisson.sf(today - 1, np.mean(baseline)))
    assert abs(poisson_p - 8.6e-6) / 8.6e-6 < 0.05, poisson_p
    result = spike_test(today, baseline)
    assert result["model"] == "negative binomial", result
    assert abs(result["p_value"] - 0.069) / 0.069 < 0.05, result["p_value"]
    assert result["verdict"] == "normal", result
    assert robust_z(5, [1, 1, 1]) is None
    assert spike_test(50, [10, 12, 11, 9, 10, 11])["verdict"] == "spike"  # var < mean: Poisson
    assert spike_test(50, [10, 12], capped=[True, False, False])["verdict"] == "uncertain (capped)"
    return poisson_p, result["p_value"]


def latest_topics():
    newest = {}
    for path in sorted(TOPICS_DIR.glob("*.json")):  # names end in the time: sorted = oldest first
        data = json.loads(path.read_text(encoding="utf-8"))
        newest[data["topic"]] = data
    return list(newest.values())


def main():
    poisson_p, nb_p = self_check()
    print(f"self-check ok: 전기차 72 vs [38,49,68,27,50,15] -> Poisson p={poisson_p:.2e}, NB p={nb_p:.3f} (normal)\n")
    print(f"{'topic':14} {'today':>5} {'mean':>6} {'var':>8} {'p':>9} {'robust z':>8}  verdict")
    for data in latest_topics():
        m = data["news_momentum"]
        r = spike_test(m["per_day"][0], m["per_day"][1:], m.get("capped_windows"))
        z = "-" if r["robust_z"] is None else f"{r['robust_z']:.2f}"
        print(f"{data['topic']:14} {r['today']:5} {r['baseline_mean']:6} {r['baseline_variance']:8} "
              f"{r['p_value']:9.2e} {z:>8}  {r['verdict']}")


if __name__ == "__main__":
    sys.exit(main())
