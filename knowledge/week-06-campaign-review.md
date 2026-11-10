---
type: Reference
title: "Week 06: campaign review skill"
description: Where the campaign review method, skill, data and reports are, and the rules the review follows.
---

# Week 06: campaign review skill

Exercise steps: [week-06/README.md](../week-06/README.md). Prompts to paste, in order:
[week-06/prompts.md](../week-06/prompts.md). No API key is needed this week.

## Files

| What | Where |
| --- | --- |
| The review method (measures, checks, report sections) | [week-06/analysis-method.md](../week-06/analysis-method.md) |
| The saved skill built from that method | [.claude/skills/campaign-review/SKILL.md](../.claude/skills/campaign-review/SKILL.md) |
| Data: synthetic campaigns of a small online store, one row per campaign per week | `week-06/data/history.csv` ([week-06/README.md](../week-06/README.md)) |
| Reports written by Claude Code | `week-06/reports/` (e.g. [2026-10-05.md](../week-06/reports/2026-10-05.md), [2026-10-19-auto.md](../week-06/reports/2026-10-19-auto.md)) |

## Rules the review follows

From [analysis-method.md](../week-06/analysis-method.md):

- Compare the two weeks the user names, otherwise the two latest; leave other weeks out.
- Check for missing, negative, and duplicate rows first; report problems; never edit the data file.
- Four measures: CTR, conversion rate, cost per purchase, ROAS (formulas in the method file).
- Report sections: comparison table, up to three findings with causes as questions, data problems.
- Do not recommend budget changes.

[week-06/README.md](../week-06/README.md) adds: check each report against a hand calculation;
a skill does not make the result correct.

## Status

- The prompts ask for a calculation script at `.claude/skills/campaign-review/scripts/analyze_campaigns.py`
  ([prompts.md](../week-06/prompts.md), step 3). That script does not exist in the repo, and
  SKILL.md does not mention running one.
- Reports present: `2026-10-05.md` (prompt 1) and `2026-10-19-auto.md` (prompt 5). The
  fresh-session report `2026-10-19.md` (prompt 4) is not in the repo.
