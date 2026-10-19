"""Does our news signal track real public interest? News counts vs Wikipedia pageviews.

For each demo topic: daily Google News article counts (UTC calendar days, same
per-day queries as topic_trends.py) are aligned with daily Wikipedia pageviews, then
  - Spearman rank correlation with its p-value, and
  - lead-lag cross-correlation for lags -3..+3: lag k compares news on day t with
    pageviews on day t+k, so a best lag > 0 means news leads pageviews.
With fewer than 7 overlapping days no number is reported.

News counts are cached in data/eval/news/ (one file per topic and day range);
results go to data/eval/groundtruth.json.

Usage:
    python midterm/eval/groundtruth.py            # self-check, then all demo topics (30 days)
    python midterm/eval/groundtruth.py --days 60
"""
import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # midterm/ modules
from eval.wiki import ARTICLES, pageviews  # noqa: E402
from topic_trends import fetch_news, is_spam  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "data" / "eval"
MIN_OVERLAP = 7
LAGS = range(-3, 4)
REGION = {"physical AI": ("en", "US")}  # every other demo topic is Korean


def news_daily_counts(topic, days=30):
    """{UTC date: (count, capped)} for the last `days` full days. Cached per run date."""
    lang, geo = REGION.get(topic, ("ko", "KR"))
    end = datetime.now(timezone.utc).date() - timedelta(days=1)
    cache = OUT / "news" / f"{topic.replace(' ', '-')}_{end}_{days}d.json"
    if cache.exists():
        return {d: tuple(v) for d, v in json.loads(cache.read_text(encoding="utf-8")).items()}

    day_list = [end - timedelta(days=d) for d in range(days)]

    def one_day(day):
        query = f"{topic} after:{day - timedelta(days=1)} before:{day + timedelta(days=1)}"
        articles = fetch_news(query, lang, geo)
        same_day = [a for a in articles if a["published"][:10] == day.isoformat()  # published is UTC
                    and not is_spam(a["title"], topic)]
        return day.isoformat(), (len(same_day), len(articles) >= 100)

    with ThreadPoolExecutor(max_workers=4) as pool:
        counts = dict(pool.map(one_day, day_list))
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(counts, ensure_ascii=False), encoding="utf-8")
    return counts


def lagged_spearman(news, views, lag):
    """Spearman correlation of news[t] with views[t + lag]."""
    if lag > 0:
        a, b = news[:-lag], views[lag:]
    elif lag < 0:
        a, b = news[-lag:], views[:lag]
    else:
        a, b = news, views
    if len(a) < MIN_OVERLAP or np.std(a) == 0 or np.std(b) == 0:
        return None
    return float(stats.spearmanr(a, b).statistic)


def compare(news, views):
    """Correlation and lead-lag for two aligned daily series (same length, same days)."""
    news, views = np.asarray(news, float), np.asarray(views, float)
    if len(news) < MIN_OVERLAP:
        return {"overlap_days": len(news), "note": f"overlap under {MIN_OVERLAP} days; no correlation reported"}
    rho, p = stats.spearmanr(news, views)
    lags = {lag: lagged_spearman(news, views, lag) for lag in LAGS}
    valid = {k: v for k, v in lags.items() if v is not None}
    best = max(valid, key=lambda k: valid[k]) if valid else None
    return {
        "overlap_days": len(news),
        "spearman": float(rho), "p_value": float(p),
        "lags": lags, "best_lag": best, "best_lag_r": valid.get(best),
    }


def self_check():
    rng = np.random.default_rng(0)
    base = rng.poisson(20, 40).astype(float)
    views = np.roll(base, 2) * 10  # pageviews follow news by two days
    result = compare(base[2:], views[2:])
    assert result["best_lag"] == 2, result
    assert abs(compare([1, 2, 3, 4, 5, 6, 7], [2, 4, 6, 8, 10, 12, 14])["spearman"] - 1) < 1e-9
    assert "note" in compare([1, 2, 3], [1, 2, 3])
    assert lagged_spearman(np.arange(10.0), np.arange(10.0), 3) == 1.0


def main():
    parser = argparse.ArgumentParser(description="News counts vs Wikipedia pageviews.")
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()
    self_check()
    print("self-check ok\n")

    results = {}
    for topic in ARTICLES:
        counts = news_daily_counts(topic, args.days)
        views = pageviews(topic)
        days = sorted(d for d in counts if d in views)
        r = compare([counts[d][0] for d in days], [views[d] for d in days])
        r.update({
            "article": "/".join(ARTICLES[topic]),
            "capped_days": sum(counts[d][1] for d in days),
            "news_per_day": round(float(np.mean([counts[d][0] for d in days])), 1) if days else None,
            "views_per_day": round(float(np.mean([views[d] for d in days])), 1) if days else None,
        })
        results[topic] = r
        if "note" in r:
            print(f"{topic:12} {r['note']}")
        else:
            print(f"{topic:12} {r['overlap_days']}d  spearman {r['spearman']:+.2f} (p={r['p_value']:.3f})  "
                  f"best lag {r['best_lag']:+d} (r={r['best_lag_r']:+.2f})  capped days {r['capped_days']}  "
                  f"news/day {r['news_per_day']}  views/day {r['views_per_day']}")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "groundtruth.json").write_text(json.dumps(
        {"made_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "days": args.days, "results": results},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved {OUT.relative_to(HERE.parent.parent)}/groundtruth.json")


if __name__ == "__main__":
    main()
