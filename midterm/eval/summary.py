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


def _load(name):
    path = EVAL / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


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
    """Every logged prediction, newest first; scored ones carry their results."""
    scored = scored or {}
    rows = [{**p, "status": "scored"} for p in scored.get("scored", [])] + [{**p, "status": "pending"} for p in scored.get("pending", [])]
    return sorted(rows, key=lambda r: r["made_at"], reverse=True)


def summary():
    pred = prediction_rows(_load("prediction_test.json"))
    scored = _load("scored_predictions.json")
    coverage = [r["coverage_80"] for r in pred]
    return {
        "made_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "prediction_test": {"rows": pred,
                            "mean_coverage_80": round(sum(coverage) / len(coverage), 3) if coverage else None},
        "prediction_log": prediction_log(scored),
        "prediction_totals": (scored or {}).get("totals"),
        "jev_agreement": _load("jev_agreement.json"),
    }


def self_check():
    assert prediction_rows({"results": {"google": {"x": {"note": "too short"}}}}) == []


def main():
    self_check()
    OUT.write_text(json.dumps(summary(), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"self-check ok\nWrote {OUT.relative_to(HERE.parent.parent)}")


if __name__ == "__main__":
    main()
