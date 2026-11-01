"""Does Jev's claim check agree with a human, and does it get closer as labels pile up?

A blind test in rounds, each measured on claims Jev has never seen as examples:
1. export: picks 30 new claims and asks Jev to rate them now. data/eval/jev_agreement.csv holds the
   claims and the evidence each cites, with NO Jev answer in it; Jev's answers go to
   jev_agreement_key.json, so don't open that before labelling.
2. Fill human_label with s / p / u (supported, partly, unsupported), using only the cited evidence.
   second_label is optional: a second person's labels show how far two humans agree at all.
3. score: kappa, a confusion table and agreement per band of Jev's confidence. The round joins the
   history in jev_agreement.json and its labels join the pool in jev_examples.json.
4. learn: tests whether showing Jev the pool helps, on labels held out from what it is shown (5 folds).
   The real checker only uses the examples if they clearly beat no examples; later rounds then show
   whether that held up on new claims.

Claims labelled in the earlier round (not blind; see jev_agreement_old_not_blind.csv) are excluded.
Claims Jev removed are saved, and all of them enter the sample (up to a third of it), so it can
also show when Jev removes a good claim. The first round's forecasts are not in the pool, since the
writer no longer forecasts.

Usage:
    python midterm/eval/jev_agreement.py export      # won't replace labels that aren't scored yet
    python midterm/eval/jev_agreement.py score       # after labelling
    python midterm/eval/jev_agreement.py learn       # about 10 Jev calls
"""
import csv
import json
import random
import subprocess
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # midterm/ modules
from analyze_topic import EXAMPLES_FILE, SECTIONS, ratings_from_jev  # noqa: E402

MIDTERM = Path(__file__).resolve().parent.parent
ANALYSIS_DIR = MIDTERM / "data" / "analysis"
OUT = MIDTERM / "data" / "eval"
CSV = OUT / "jev_agreement.csv"
KEY = OUT / "jev_agreement_key.json"
RESULT = OUT / "jev_agreement.json"
OLD_CSV = OUT / "jev_agreement_old_not_blind.csv"
LABELS = ("supported", "partly", "unsupported")
SHORT = {"s": "supported", "p": "partly", "u": "unsupported"}
BANDS = ((0.0, 0.6), (0.6, 0.8), (0.8, 1.01))
FOLDS = 5
MIN_LABELS = 60  # fewer than this and kappa is too noisy to change what the real checker does
MIN_GAIN = 0.1  # re-rating the same claims moved kappa by about 0.03, so a gain must clear well above that


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
        claims += [(section, c) for section in SECTIONS for c in e.get(section) or []]
        claims = [(section, c, False) for section, c in claims] + [
            (c["section"], c, True) for c in e.get("removed_claims", []) if c["section"] != "outlook"]
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
    by_run = {}
    for r in sample:
        by_run.setdefault(r["run_name"], []).append(r)
    for rows in by_run.values():
        ratings = ratings_from_jev([(r["section"], r["claim"]) for r in rows], rows[0]["run"]["evidence"])
        for n, r in enumerate(rows):
            r["jev"] = ratings.get(n)


def load_pool():
    return json.loads(EXAMPLES_FILE.read_text(encoding="utf-8")) if EXAMPLES_FILE.exists() else {"use": False, "examples": []}


def load_rounds():
    return json.loads(RESULT.read_text(encoding="utf-8")).get("rounds", []) if RESULT.exists() else []


def csv_rows():
    return [r for r in csv.DictReader(CSV.open(encoding="utf-8-sig")) if r["human_label"].strip()] if CSV.exists() else []


def export(n=30):
    answers = json.loads(KEY.read_text(encoding="utf-8")) if KEY.exists() else {}
    current = next(iter(answers.values()), {}).get("round", 1)
    if csv_rows() and current not in [r["round"] for r in load_rounds()]:
        print(f"{CSV.name} has labels that aren't scored yet; run score first")
        return
    pool = load_pool()
    seen = {e["claim"] for e in pool["examples"]}
    seen |= {r["claim"] for r in csv.DictReader(OLD_CSV.open(encoding="utf-8-sig"))} if OLD_CSV.exists() else set()
    rows = [r for r in written_claims() if r["claim"]["claim"] not in seen
            and all(x in r["run"]["evidence"] for x in r["claim"].get("cites", []))]
    round_no = max([r["round"] for r in load_rounds()], default=0) + 1
    sample = pick(rows, n, seed=10 + round_no)
    rate_now(sample)
    sample = [r for r in sample if r["jev"]]  # Jev left a question unanswered: nothing to compare
    if not sample:
        print("no new claims to label: run more analyses first")
        return
    with CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "topic", "section", "claim", "cited_evidence", "human_label", "second_label"])
        for i, r in enumerate(sample, 1):
            cited = " || ".join(f"[{x}] {r['run']['evidence'][x]}" for x in r["claim"]["cites"])
            writer.writerow([i, r["run"].get("topic"), r["section"], r["claim"]["claim"], cited, "", ""])
    examples_used = len(pool["examples"]) if pool["use"] else 0
    KEY.write_text(json.dumps({str(i): {"run": r["run_name"], "section": r["section"], "jev_label": r["jev"]["rating"],
                                        "jev_confidence": r["jev"]["confidence"], "round": round_no,
                                        "examples_used": examples_used} for i, r in enumerate(sample, 1)},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"round {round_no}: wrote {len(sample)} of {len(rows)} claims to data/eval/{CSV.name}; "
          f"Jev's answers are in {KEY.name} (don't open it yet)")


def read_label(value):
    value = value.strip().lower()
    return SHORT.get(value, value)


def agreement(pairs):
    return round(sum(a == b for a, b in pairs) / len(pairs), 2) if pairs else None


def merge_round(pool, round_no, rows):
    """The pool with this round's labels; scoring a round twice replaces them. Forecasts stay out."""
    new = [{"round": round_no, "section": r["section"], "claim": r["claim"], "evidence": r["cited_evidence"],
            "label": read_label(r["human_label"])} for r in rows if r["section"] != "outlook"]
    return {**pool, "examples": [e for e in pool["examples"] if e["round"] != round_no] + new}


def score():
    key = json.loads(KEY.read_text(encoding="utf-8"))
    rows = csv_rows()
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
    round_no = answers[0].get("round", 1)
    rounds = [r for r in load_rounds() if r["round"] != round_no] + [
        {"round": round_no, "date": date.today().isoformat(), "n": len(rows), "kappa": round(kappa, 3),
         "agreement": agree, "examples_used": answers[0].get("examples_used", 0)}]
    RESULT.write_text(json.dumps(
        {"n": len(rows), "agreement": agree, "kappa": round(kappa, 3), "calibration": table,
         "confusion_jev_by_human": confusion, "human_kappa": human_kappa, "human_pairs": len(two), "rounds": rounds},
        indent=2), encoding="utf-8")
    EXAMPLES_FILE.write_text(json.dumps(merge_round(load_pool(), round_no, rows), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nround {round_no} saved; labels added to {EXAMPLES_FILE.name}")


def folds_of(rows, seed=3):
    rows = list(rows)
    random.Random(seed).shuffle(rows)
    return [rows[i::FOLDS] for i in range(FOLDS)]


def examples_help(n, with_examples, without_examples):
    return n >= MIN_LABELS and with_examples - without_examples >= MIN_GAIN


def rate_labelled(rows, examples):
    """Jev's rating of pool rows, with or without examples; {pool row index in `rows`: rating}."""
    items = [(r["section"], {"claim": r["claim"], "cites": [f"r{n}"]}) for n, r in enumerate(rows)]
    return ratings_from_jev(items, {f"r{n}": r["evidence"] for n, r in enumerate(rows)}, examples=examples)


def learn():
    pool = load_pool()
    folds = folds_of(pool["examples"])
    pairs = {"with": [], "without": []}
    for k, fold in enumerate(folds):
        shown = [e for j, f in enumerate(folds) if j != k for e in f]
        for name, examples in (("with", shown), ("without", [])):
            ratings = rate_labelled(fold, examples)
            pairs[name] += [(fold[n]["label"], r["rating"]) for n, r in ratings.items()]
    with_k, without_k = (round(cohens_kappa(*zip(*pairs[name])), 3) for name in ("with", "without"))
    n = len(pool["examples"])
    use = examples_help(n, with_k, without_k)
    pool.update(use=use, learn={"date": date.today().isoformat(), "n": n, "kappa_with": with_k, "kappa_without": without_k})
    EXAMPLES_FILE.write_text(json.dumps(pool, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{n} labels: kappa {with_k} with examples, {without_k} without -> examples {'ON' if use else 'off'}"
          + (f" (needs at least {MIN_LABELS} labels)" if n < MIN_LABELS else ""))


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
    # Scoring a round twice replaces its labels, and forecasts stay out of the pool.
    labelled = [{"section": "what_is_happening", "claim": "c", "cited_evidence": "e", "human_label": "s"},
                {"section": "outlook", "claim": "f", "cited_evidence": "e", "human_label": "p"}]
    pool = merge_round({"use": False, "examples": [{"round": 1, "claim": "old"}]}, 2, labelled)
    pool = merge_round(pool, 2, labelled)
    assert [e["claim"] for e in pool["examples"]] == ["old", "c"] and pool["examples"][1]["label"] == "supported"
    # A claim is never shown as an example while it is being rated.
    folds = folds_of(range(23))
    assert sorted(x for f in folds for x in f) == list(range(23)) and all(f for f in folds)
    # Examples go live only with enough labels and a clear gain.
    assert examples_help(60, 0.3, 0.1) and not examples_help(59, 0.3, 0.1) and not examples_help(60, 0.15, 0.1)


if __name__ == "__main__":
    self_check()
    {"export": export, "score": score, "learn": learn}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: sys.exit(__doc__))()
