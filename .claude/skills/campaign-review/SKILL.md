---
name: campaign-review
description: Weekly ad campaign review that compares two weeks of campaign results (CTR, conversion rate, cost per purchase, ROAS), checks the data for problems, and saves a Markdown report. Use this whenever the user asks what changed in their ads, campaigns or marketing results between weeks, wants a weekly campaign report, or points at a campaign data file such as week-06/data/history.csv, even if they don't say "campaign review".
---

# Weekly campaign review

Compare two weeks of ad campaign results and write a short Markdown report that points
people at what to investigate. The report describes and asks; it does not decide budgets.

## Input

The data file has one row per campaign per week, with these columns:
`week_start, campaign, impressions, clicks, attributed_purchases, ad_spend_usd, attributed_revenue_usd`.

Compare the two weeks the user names. If they name none, use the two latest `week_start`
values in the file. Leave all other weeks out of the measures and findings, because the
reader asked about these two weeks and older weeks would blur the comparison.

## Data checks

Before calculating, check the whole file for:

- missing values (empty cells),
- negative values in the numeric columns,
- duplicate rows (identical rows, and repeated `week_start` + `campaign` pairs).

Report every problem you find, or say plainly that none was found. Never edit the data
file: it is the source of record, and the reader needs to see the problem, not a silent fix.
If a problem makes a measure impossible (for example zero purchases, so cost per purchase
divides by zero), show the measure as "n/a" and explain why in the data problems section.

## Four measures

Calculate these for each campaign in each of the two weeks. Compute them with code
(a short Python script) rather than by mental arithmetic, so the numbers are exact.

| Measure                   | Formula                         |
|---------------------------|---------------------------------|
| Click-through rate (CTR)  | clicks ÷ impressions            |
| Conversion rate           | attributed purchases ÷ clicks   |
| Cost per purchase         | ad spend ÷ attributed purchases |
| Return on ad spend (ROAS) | attributed revenue ÷ ad spend   |

Show CTR and conversion rate as percentages with two decimals and their change in
percentage points (pp). Show cost per purchase in dollars and ROAS to two decimals, with
the absolute change and the relative change in brackets. A campaign present in only one of
the two weeks gets "n/a" for the missing week and change, and a note in data problems.

## Report

Save the report as Markdown where the user asks. If they give no path, save it to the
`reports/` folder next to the data folder, named after the later week (e.g.
`week-06/reports/2026-10-05.md`). Use this structure:

```markdown
# Weekly campaign review: week of <later week> vs <earlier week>

Source: <data file>, rows for <earlier week> and <later week> only.

## 1. Comparison table
| Campaign | Measure | <earlier week> | <later week> | Change |
(the four measures for every campaign in both weeks, and the change)

## 2. Findings
(up to three changes worth investigating)

## 3. Data problems
(what was checked and what was found; state that the data file was not edited)
```

### Findings

Pick up to three changes that most deserve a closer look, largest effect on results first.
For each, state the change with its numbers, use the raw counts (impressions, clicks,
purchases, spend, revenue) to show where it came from, and write possible causes as
questions, e.g. "Did the ad creative change in the week of 5 October?". Questions keep the
report honest: the data shows what changed, not why, and the reader is the one who can find
out. Leave out flat campaigns rather than padding to three.

Do not recommend budget changes (no "increase spend on X" or "pause Y"). Budget decisions
need context this data doesn't hold, and the report's job is to direct attention.

After saving, give the user a short summary: the data check result, the main changes, and
the report path.
