"""All eval results in one small file for the web page's history tab.

Reads the result files the other eval scripts wrote (it measures nothing itself) and the
prediction log, and writes data/eval/summary.json. build_dashboard.py / app.py call
summary() directly; the Cloudflare Worker imports the JSON file, so run this before
`npx wrangler deploy` to publish newer results.

Usage:
    python midterm/eval/summary.py      # self-check, then data/eval/summary.json
"""
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
EVAL = DATA / "eval"
OUT = EVAL / "summary.json"
ALPHA = 0.05


def _load(name):
    path = EVAL / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def groundtruth_rows(g):
    """One row per topic and source: Spearman rho, p, best lag."""
    rows = []
    for topic, sources in (g or {}).get("results", {}).items():
        for source, r in sources.items():
            if not r or "spearman" not in r:
                continue
            rows.append({"topic": topic, "source": source, "series": r.get("series"), "n": r["overlap_days"],
                         "rho": round(r["spearman"], 2), "p": r["p_value"], "best_lag": r["best_lag"],
                         "significant": r["p_value"] < ALPHA})
    return rows


def prediction_rows(p):
    rows = []
    for source, topics in (p or {}).get("results", {}).items():
        for topic, r in topics.items():
            if "holdout" not in r:
                continue
            h, d = r["holdout"], r["holdout"].get("direction") or {}
            rows.append({"source": source, "topic": topic, "model": h["model"], "n": h["n"], "mape": h["mape"],
                         "mase": h["mase"], "coverage_80": h["coverage_80"], "direction": d.get("hit_rate"),
                         "direction_p": d.get("p_vs_coin"), "example": r.get("example")})
    return rows


def prediction_log(scored):
    """Every logged prediction, newest first, with its score once the window has ended."""
    log = DATA / "predictions.jsonl"
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()] if log.exists() else []
    done = {(r["topic"], r["made_at"]): r for r in (scored or {}).get("scored", [])}
    out = []
    for p in rows:
        r = done.get((p["topic"], p["made_at"]))
        out.append({**p, "status": "scored" if r else "pending",
                    "actual": r and r.get("actual"), "inside_interval": r and r.get("inside_interval")})
    return sorted(out, key=lambda r: r["made_at"], reverse=True)


def summary():
    grounding = _load("grounding.json") or {}
    pred = prediction_rows(_load("prediction_test.json"))
    log = prediction_log(_load("scored_predictions.json"))
    gt = groundtruth_rows(_load("groundtruth.json"))
    coverage = [r["coverage_80"] for r in pred]
    return {
        "made_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "groundtruth": {"days": (_load("groundtruth.json") or {}).get("days"), "rows": gt,
                        "topics": len({r["topic"] for r in gt}),
                        "significant_topics": len({r["topic"] for r in gt if r["significant"]})},
        "prediction_test": {"rows": pred,
                            "mean_coverage_80": round(sum(coverage) / len(coverage), 3) if coverage else None},
        "prediction_log": log,
        "grounding": {k: grounding.get(k) for k in ("analyses", "claims", "numbers", "grounded", "own", "chance_other_topic")},
        "jev_agreement": _load("jev_agreement.json"),
    }


def self_check():
    g = {"results": {"a": {"google": {"overlap_days": 90, "spearman": 0.4, "p_value": 0.001, "best_lag": 0},
                           "wikipedia": None},
                     "b": {"google": {"overlap_days": 90, "spearman": 0.1, "p_value": 0.3, "best_lag": -2}}}}
    rows = groundtruth_rows(g)
    assert [r["significant"] for r in rows] == [True, False], rows
    assert prediction_rows({"results": {"google": {"x": {"note": "too short"}}}}) == []


def main():
    self_check()
    OUT.write_text(json.dumps(summary(), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"self-check ok\nWrote {OUT.relative_to(HERE.parent.parent)}")


if __name__ == "__main__":
    main()
