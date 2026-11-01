"""Does Jev's claim check agree with a human? A blind test: Cohen's kappa and a calibration table.

Step 1 (export): picks 30 claims and asks Jev to rate them now, under the current rules.
data/eval/jev_agreement.csv holds the claims and the evidence each cites, with NO Jev answer
in it; Jev's answers go to jev_agreement_key.json, so don't open that before labelling.
Step 2: fill human_label with s / p / u (supported, partly, unsupported), using only the
cited evidence. A forecast is "supported" if its basis is in the evidence, not if it came true.
second_label is optional: a second person's labels show how far two humans agree at all.
Step 3 (score): kappa, a confusion table, agreement for forecasts vs other claims, and
agreement per band of Jev's confidence.

Claims labelled in the earlier round (not blind; see jev_agreement_old_not_blind.csv) are
excluded. Claims Jev removed are saved since this change, and all of them enter the sample
(up to a third of it), so it can also show when Jev removes a good claim.

Usage:
    python midterm/eval/jev_agreement.py export      # won't overwrite existing labels
    python midterm/eval/jev_agreement.py score       # after labelling
"""
import csv
import json
import random
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # midterm/ modules

MIDTERM = Path(__file__).resolve().parent.parent
ANALYSIS_DIR = MIDTERM / "data" / "analysis"
OUT = MIDTERM / "data" / "eval"
CSV = OUT / "jev_agreement.csv"
KEY = OUT / "jev_agreement_key.json"
OLD_CSV = OUT / "jev_agreement_old_not_blind.csv"
LABELS = ("supported", "partly", "unsupported")
SHORT = {"s": "supported", "p": "partly", "u": "unsupported"}
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


def written_claims():
    """Every claim Jev has seen, with the run it came from; those it removed are flagged."""
    rows = []
    for label, run in sorted(all_runs().items()):
        e = run.get("explanation") or {}
        if e.get("checked_by") != "jev":
            continue
        claims = [("summary", e["summary"])] if e.get("summary") else []
        claims += [(section, c) for section in SECTIONS[1:] for c in e.get(section) or []]
        claims = [(section, c, False) for section, c in claims] + [(c["section"], c, True) for c in e.get("removed_claims", [])]
        rows += [{"run": run, "run_name": label, "section": section, "claim": c, "removed": removed}
                 for section, c, removed in claims]
    return rows


def pick(rows, n, seed):
    """All removed claims (up to a third of the sample), the rest at random."""
    rng = random.Random(seed)
    removed = [r for r in rows if r["removed"]]
    kept = [r for r in rows if not r["removed"]]
    chosen = rng.sample(removed, min(n // 3, len(removed)))
    chosen += rng.sample(kept, min(n - len(chosen), len(kept)))
    rng.shuffle(chosen)
    return chosen


def rate_now(sample):
    """Jev's rating of each sampled claim under the current rules. Ratings saved in old runs used older ones."""
    from analyze_topic import ratings_from_jev  # needs the API key, so only when exporting
    by_run = {}
    for r in sample:
        by_run.setdefault(r["run_name"], []).append(r)
    for rows in by_run.values():
        ratings = ratings_from_jev([(r["section"], r["claim"]) for r in rows], rows[0]["run"]["evidence"])
        for n, r in enumerate(rows):
            r["jev"] = ratings.get(n)


def export(n=30, seed=11):
    if CSV.exists() and any(r["human_label"].strip() for r in csv.DictReader(CSV.open(encoding="utf-8-sig"))):
        print(f"{CSV.name} already has labels; not overwriting")
        return
    seen = {r["claim"] for r in csv.DictReader(OLD_CSV.open(encoding="utf-8-sig"))} if OLD_CSV.exists() else set()
    rows = [r for r in written_claims() if r["claim"]["claim"] not in seen
            and all(x in r["run"]["evidence"] for x in r["claim"].get("cites", []))]
    sample = pick(rows, n, seed)
    rate_now(sample)
    sample = [r for r in sample if r["jev"]]  # Jev left a question unanswered: nothing to compare
    with CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "topic", "section", "claim", "cited_evidence", "human_label", "second_label"])
        for i, r in enumerate(sample, 1):
            c = r["claim"]
            text = c["claim"] + (f" (basis: {c['basis']})" if c.get("basis") else "")
            cited = " || ".join(f"[{x}] {r['run']['evidence'][x]}" for x in c["cites"])
            writer.writerow([i, r["run"].get("topic"), r["section"], text, cited, "", ""])
    KEY.write_text(json.dumps({str(i): {"run": r["run_name"], "section": r["section"], "jev_label": r["jev"]["rating"],
                                        "jev_confidence": r["jev"]["confidence"]} for i, r in enumerate(sample, 1)},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {len(sample)} of {len(rows)} claims to data/eval/{CSV.name}; Jev's answers are in {KEY.name} (don't open it yet)")


def read_label(value):
    value = value.strip().lower()
    return SHORT.get(value, value)


def agreement(pairs):
    return round(sum(a == b for a, b in pairs) / len(pairs), 2) if pairs else None


def score():
    key = json.loads(KEY.read_text(encoding="utf-8"))
    rows = [r for r in csv.DictReader(CSV.open(encoding="utf-8-sig")) if r["human_label"].strip()]
    if not rows:
        sys.exit("no human labels yet: fill the human_label column first")
    bad = [r["id"] for r in rows if read_label(r["human_label"]) not in LABELS]
    if bad:
        sys.exit(f"human_label must be s, p or u; fix rows {bad}")
    human = [read_label(r["human_label"]) for r in rows]
    answers = [key[r["id"]] for r in rows]
    jev = [a["jev_label"] for a in answers]
    kappa = cohens_kappa(human, jev)
    agree = agreement(list(zip(human, jev)))
    print(f"{len(rows)} labelled claims: agreement {agree:.0%}, Cohen's kappa {kappa:.2f}\n")
    confusion = {j: {h: sum(1 for a, b in zip(jev, human) if a == j and b == h) for h in LABELS} for j in LABELS}
    print("confusion (rows: Jev, columns: you)")
    print("            " + "".join(f"{l:>12}" for l in LABELS))
    for j in LABELS:
        print(f"{j:>12}" + "".join(f"{confusion[j][h]:>12}" for h in LABELS))
    forecasts = [(h, a["jev_label"]) for h, a in zip(human, answers) if a["section"] == "outlook"]
    others = [(h, a["jev_label"]) for h, a in zip(human, answers) if a["section"] != "outlook"]
    print(f"\nagreement: forecasts {agreement(forecasts)} (n={len(forecasts)}), other claims {agreement(others)} (n={len(others)})")
    print("\ncalibration: Jev confidence band -> how often you agreed")
    table = []
    for lo, hi in BANDS:
        band = [(h, a["jev_label"]) for h, a in zip(human, answers) if lo <= a["jev_confidence"] < hi]
        table.append({"band": f"{lo:.1f}-{min(hi, 1):.1f}", "n": len(band), "agreement": agreement(band)})
        print(f"  {table[-1]['band']}: n={len(band):2}  agreement {table[-1]['agreement']}")
    two = [(read_label(r["human_label"]), read_label(r["second_label"])) for r in rows if r.get("second_label", "").strip()]
    human_kappa = round(cohens_kappa(*zip(*two)), 3) if two else None
    if two:
        print(f"\ntwo humans: {len(two)} claims, kappa {human_kappa}")
    (OUT / "jev_agreement.json").write_text(json.dumps(
        {"n": len(rows), "agreement": agree, "kappa": round(kappa, 3), "calibration": table,
         "confusion_jev_by_human": confusion, "agreement_forecasts": agreement(forecasts),
         "agreement_other_claims": agreement(others), "human_kappa": human_kappa, "human_pairs": len(two)},
        indent=2), encoding="utf-8")


def self_check():
    # Classic 2x2 example: 20 yes-yes, 5 yes-no, 10 no-yes, 15 no-no -> kappa 0.4.
    a = ["y"] * 25 + ["n"] * 25
    b = ["y"] * 20 + ["n"] * 5 + ["y"] * 10 + ["n"] * 15
    assert abs(cohens_kappa(a, b) - 0.4) < 1e-9
    assert cohens_kappa(["x", "y"], ["x", "y"]) == 1.0
    # Removed claims all enter the sample, up to a third of it.
    rows = [{"removed": i < 5} for i in range(50)]
    assert sum(r["removed"] for r in pick(rows, 30, 1)) == 5
    assert sum(r["removed"] for r in pick([{"removed": True}] * 20 + [{"removed": False}] * 20, 30, 1)) == 10
    assert read_label(" S ") == "supported" and read_label("0.8") == "0.8"


if __name__ == "__main__":
    self_check()
    {"export": export, "score": score}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: sys.exit(__doc__))()
