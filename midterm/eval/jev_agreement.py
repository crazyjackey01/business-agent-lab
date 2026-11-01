"""Does Jev's claim check agree with a human? Cohen's kappa and a calibration table.

Step 1 (export): 30 random Jev-checked claims, with the evidence each one cites, go to
data/eval/jev_agreement.csv. Fill the human_label column with supported / partly /
unsupported (open it in Excel or Google Sheets; it is UTF-8 with a BOM for Korean).
Step 2 (score): Cohen's kappa between your labels and Jev's, a confusion table, and a
calibration table: for each band of Jev's confidence, how often you agreed.

Limit: claims Jev rated "unsupported" were removed before saving, so the sample holds
only claims Jev kept. Kappa here measures agreement on kept claims, not how often Jev
wrongly removed a good one.

Usage:
    python midterm/eval/jev_agreement.py export      # writes the CSV (won't overwrite your labels)
    python midterm/eval/jev_agreement.py score       # after labelling
"""
import csv
import json
import random
import subprocess
import sys
from collections import Counter
from pathlib import Path

MIDTERM = Path(__file__).resolve().parent.parent
ANALYSIS_DIR = MIDTERM / "data" / "analysis"
OUT = MIDTERM / "data" / "eval"
CSV = OUT / "jev_agreement.csv"
LABELS = ("supported", "partly", "unsupported")
SECTIONS = ("summary", "why_people_search", "what_is_happening", "outlook")
BANDS = ((0.0, 0.6), (0.6, 0.8), (0.8, 1.01))


def cohens_kappa(a, b):
    """Cohen's kappa for two equal-length label lists."""
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum(ca[k] * cb[k] for k in set(a) | set(b)) / n ** 2
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def all_runs():
    """{label: run} for current files and every earlier version in git history."""
    runs = {}
    listing = subprocess.run(["git", "rev-list", "--all", "--objects", "--", str(ANALYSIS_DIR)],
                             capture_output=True, text=True, cwd=MIDTERM).stdout
    for line in listing.splitlines():
        parts = line.split(" ", 1)
        if len(parts) == 2 and parts[1].endswith(".json"):
            blob = subprocess.run(["git", "cat-file", "-p", parts[0]], capture_output=True, cwd=MIDTERM).stdout
            runs.setdefault(parts[1].split("/")[-1], json.loads(blob.decode("utf-8")))
    for path in ANALYSIS_DIR.glob("*.json"):  # files not committed yet
        runs.setdefault(path.name, json.loads(path.read_text(encoding="utf-8")))
    return runs


def jev_checked_claims():
    rows = []
    for label, run in sorted(all_runs().items()):
        e = run.get("explanation") or {}
        if e.get("checked_by") != "jev":
            continue
        for section in SECTIONS:
            items = [e[section]] if section == "summary" and e.get(section) else e.get(section) or []
            if section == "summary" and not e.get(section):
                items = []
            for c in items:
                if c.get("check") in LABELS and c.get("check_confidence") is not None:
                    rows.append({
                        "run": label, "topic": run.get("topic"), "section": section, "claim": c["claim"],
                        "cited_evidence": " || ".join(f"[{x}] {run['evidence'].get(x, '')}" for x in c["cites"]),
                        "jev_label": c["check"], "jev_confidence": c["check_confidence"], "human_label": "",
                    })
    return rows


def export(n=30, seed=7):
    if CSV.exists() and any(r["human_label"] for r in csv.DictReader(CSV.open(encoding="utf-8-sig"))):
        print(f"{CSV.name} already has labels; not overwriting")
        return
    rows = jev_checked_claims()
    sample = random.Random(seed).sample(rows, min(n, len(rows)))
    OUT.mkdir(parents=True, exist_ok=True)
    with CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", *sample[0].keys()])
        writer.writeheader()
        for i, r in enumerate(sample, 1):
            writer.writerow({"id": i, **r})
    print(f"wrote {len(sample)} of {len(rows)} Jev-checked claims to data/eval/{CSV.name}; "
          f"Jev labels in the sample: {dict(Counter(r['jev_label'] for r in sample))}")


def score():
    rows = [r for r in csv.DictReader(CSV.open(encoding="utf-8-sig")) if r["human_label"].strip()]
    bad = [r["id"] for r in rows if r["human_label"].strip() not in LABELS]
    if bad:
        sys.exit(f"human_label must be one of {LABELS}; fix rows {bad}")
    if not rows:
        sys.exit("no human labels yet: fill the human_label column first")
    human = [r["human_label"].strip() for r in rows]
    jev = [r["jev_label"] for r in rows]
    kappa = cohens_kappa(human, jev)
    agree = sum(h == j for h, j in zip(human, jev)) / len(rows)
    print(f"{len(rows)} labelled claims: agreement {agree:.0%}, Cohen's kappa {kappa:.2f}\n")
    print("confusion (rows: Jev, columns: you)")
    print("            " + "".join(f"{l:>12}" for l in LABELS))
    for j in LABELS:
        print(f"{j:>12}" + "".join(f"{sum(1 for a, b in zip(jev, human) if a == j and b == h):>12}" for h in LABELS))
    print("\ncalibration: Jev confidence band -> how often you agreed")
    table = []
    for lo, hi in BANDS:
        band = [h == r["jev_label"] for h, r in zip(human, rows) if lo <= float(r["jev_confidence"]) < hi]
        table.append({"band": f"{lo:.1f}-{min(hi, 1):.1f}", "n": len(band),
                      "agreement": round(sum(band) / len(band), 2) if band else None})
        print(f"  {table[-1]['band']}: n={len(band):2}  agreement {'-' if not band else f'{sum(band) / len(band):.0%}'}")
    (OUT / "jev_agreement.json").write_text(json.dumps(
        {"n": len(rows), "agreement": round(agree, 3), "kappa": round(kappa, 3), "calibration": table,
         "confusion_jev_by_human": {j: {h: sum(1 for a, b in zip(jev, human) if a == j and b == h) for h in LABELS}
                                    for j in LABELS}},
        indent=2), encoding="utf-8")


def self_check():
    # Classic 2x2 example: 20 yes-yes, 5 yes-no, 10 no-yes, 15 no-no -> kappa 0.4.
    a = ["y"] * 25 + ["n"] * 25
    b = ["y"] * 20 + ["n"] * 5 + ["y"] * 10 + ["n"] * 15
    assert abs(cohens_kappa(a, b) - 0.4) < 1e-9
    assert cohens_kappa(["x", "y"], ["x", "y"]) == 1.0


if __name__ == "__main__":
    self_check()
    {"export": export, "score": score}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: sys.exit(__doc__))()
