"""Are the numbers in the generated sentences real? A deterministic check, no model involved.

For each claim the writer produced (summary, why / what is happening / outlook, and the
outlook's basis), every number is extracted with a regex (counts, %, 배/x multipliers,
money, dates) and looked up in that same run's facts and evidence (measured data and
the headlines/summaries the writer was given). A number is grounded if some number in
the run's facts equals it at the precision shown, e.g. "68%" matches a share of 0.68,
"7,368억" matches "7368억", "2.2배" matches a ratio of 2.17.

A control shows how often numbers would "ground" by chance: each run's numbers are also
checked against the facts of every run about a different topic. Small numbers (1, 13,
2026) match by chance often, so the report separates distinctive numbers (>= 100 or with
decimals), where chance matches are rare.

Runs over every analysis ever saved: the files in data/analysis/ plus earlier versions
that were pruned from the folder but are still in git history.

Usage:
    python midterm/eval/grounding.py      # self-check, then report -> data/eval/grounding.{json,md}
"""
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MIDTERM = HERE.parent
ANALYSIS_DIR = MIDTERM / "data" / "analysis"
OUT = MIDTERM / "data" / "eval"

# A number, optionally with thousands separators and decimals; the unit after it is kept
# for the report. Digits inside words like "S26" or "ID.4" count too (they must be sourced).
NUMBER = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?\s*(%|배|x|×|건|원|억|조|만|명|대|개|일|월|년|시간|분)?",
                    re.IGNORECASE)
ANY_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
SECTIONS = ("why_people_search", "what_is_happening", "outlook")


def numbers_in(text):
    """[(value, decimals, unit, as written)] for every number in a sentence."""
    out = []
    for m in NUMBER.finditer(text):
        whole, frac, unit = m.group(1), m.group(2), (m.group(3) or "")
        value = float(whole.replace(",", "") + ("." + frac if frac else ""))
        out.append((value, len(frac) if frac else 0, unit, m.group(0).strip()))
    return out


def source_numbers(run):
    """Every number in the run's facts and evidence, as floats."""
    text = json.dumps(run.get("facts", {}), ensure_ascii=False) + " " + " ".join(run.get("evidence", {}).values())
    return {float(n.replace(",", "")) for n in ANY_NUMBER.findall(text)}


def grounded(value, decimals, unit, sources):
    """True if a source number shows as this value at the precision written."""
    for s in sources:
        candidates = [s]
        if unit == "%":
            candidates.append(s * 100)  # shares are stored as fractions (0.68 -> 68%)
        if any(round(c, decimals) == value for c in candidates):
            return True
    return False


def claims_of(run):
    """(section, text) for every claim, plus the outlook bases."""
    e = run.get("explanation") or {}
    out = []
    if e.get("summary"):
        out.append(("summary", e["summary"]["claim"]))
    for section in SECTIONS:
        for c in e.get(section) or []:
            out.append((section, c["claim"]))
            if c.get("basis"):
                out.append((section + ".basis", c["basis"]))
    return out


def check_run(run):
    sources = source_numbers(run)
    rows = []
    for section, text in claims_of(run):
        for value, decimals, unit, written in numbers_in(text):
            rows.append({"section": section, "number": written, "grounded": grounded(value, decimals, unit, sources),
                         "claim": text})
    return rows


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


def distinctive(value, decimals):
    return value >= 100 or decimals > 0


def rates(runs, pairs):
    """Grounded / total for all numbers and for distinctive numbers, over (claims run, facts run) pairs."""
    n = g = dn = dg = 0
    for a, b in pairs:
        sources = source_numbers(runs[b])
        for _, text in claims_of(runs[a]):
            for value, decimals, unit, _ in numbers_in(text):
                ok = grounded(value, decimals, unit, sources)
                n, g = n + 1, g + ok
                if distinctive(value, decimals):
                    dn, dg = dn + 1, dg + ok
    return {"all": [g, n], "distinctive": [dg, dn]}


def self_check():
    run = {"facts": {"intent": [{"share": 0.68}], "coverage": {"momentum": 2.17}},
           "evidence": {"S1": "2026-10-10 | 뉴스 | 부산, 135억 원으로 1,520대 보조금 추가"},
           "explanation": {"summary": {"claim": "구매 의도가 68%다. 기사량은 2.2배다.", "cites": []},
                           "what_is_happening": [{"claim": "부산시가 135억 원으로 1520대분을 추가했다. 3000대 추가설도 있다.",
                                                  "cites": []}]}}
    rows = check_run(run)
    found = {r["number"]: r["grounded"] for r in rows}
    assert found == {"68%": True, "2.2배": True, "135억": True, "1520대": True, "3000대": False}, found
    assert numbers_in("9조6434억 원")[0][0] == 9


def main():
    self_check()
    print("self-check ok\n")
    report, ungrounded, claims = {}, [], 0
    for label, run in sorted(all_runs().items()):
        rows = check_run(run)
        claims += len(claims_of(run))
        report[label] = {"topic": run.get("topic"), "claims": len(claims_of(run)), "numbers": len(rows),
                         "grounded": sum(r["grounded"] for r in rows)}
        ungrounded += [{"run": label, **r} for r in rows if not r["grounded"]]
    numbers = sum(r["numbers"] for r in report.values())
    good = sum(r["grounded"] for r in report.values())
    runs = all_runs()
    own = rates(runs, [(k, k) for k in runs])
    chance = rates(runs, [(a, b) for a in runs for b in runs if runs[a].get("topic") != runs[b].get("topic")])
    pct = lambda pair: f"{pair[0]}/{pair[1]} ({pair[0] / pair[1] * 100:.0f}%)" if pair[1] else "-"
    print(f"{len(report)} analyses, {claims} claims, {numbers} numbers, {good} grounded "
          f"({good / numbers * 100:.1f}%), {numbers - good} ungrounded")
    print(f"  own facts:            all {pct(own['all'])}, distinctive {pct(own['distinctive'])}")
    print(f"  chance (other topic): all {pct(chance['all'])}, distinctive {pct(chance['distinctive'])}\n")
    for u in ungrounded:
        print(f"  {u['run'][:34]:34} {u['number']:>10}  {u['claim'][:90]}")
    summary = {"analyses": len(report), "claims": claims, "numbers": numbers, "grounded": good,
               "grounded_pct": round(good / numbers * 100, 1), "own": own, "chance_other_topic": chance,
               "per_run": report, "ungrounded": ungrounded}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "grounding.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [f"{len(report)} analyses, {claims} claims, {numbers} numbers, **{good} grounded "
          f"({summary['grounded_pct']}%)**, {numbers - good} ungrounded.", "",
          "| numbers checked against | all numbers | distinctive (>= 100 or decimal) |", "|---|---|---|",
          f"| the run's own facts | {pct(own['all'])} | {pct(own['distinctive'])} |",
          f"| another topic's facts (chance) | {pct(chance['all'])} | {pct(chance['distinctive'])} |", "",
          "| run | number | claim |", "|---|---|---|"]
    md += [f"| {u['run']} | {u['number']} | {u['claim'][:120]} |" for u in ungrounded]
    (OUT / "grounding.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\nSaved data/eval/grounding.json and .md")


if __name__ == "__main__":
    main()
