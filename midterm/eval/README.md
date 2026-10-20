# Measurable validation

Every judgment about signals, predictions and accuracy below is made by deterministic
statistics compared against external ground truth. Language models only turn results
that are already decided into sentences; none of them decides whether a spike is real,
whether a prediction was right, or whether a number is correct.

Results as of 2026-10-19. Ground truth: Google Trends search interest and Wikipedia pageviews. Run everything from the `business-agent-lab` folder with the
venv active (`pip install -r midterm/requirements.txt` for numpy and scipy). Every module
runs its own assert-based self-check first.

## The numbers to present

1. **Our news signal tracks real public interest for 4 of 5 topics.** Over 90 days, daily news
   counts correlate significantly (Spearman, p < 0.05) with Google search interest or Wikipedia
   pageviews for 피지컬 AI (Google ρ = +0.40, p = 0.0001; Wikipedia +0.27), physical AI
   (Wikipedia +0.32, p = 0.002), 전기차 (Google +0.24, p = 0.02) and 스마트 안경 (Google +0.23,
   p = 0.03). 갤럭시 shows no link. After a strict correction for 10 tests (p < 0.005), two
   survive: 피지컬 AI on Google and physical AI on Wikipedia.
2. **Predictions, tested on data the models never saw** (holdout, `eval/prediction_test.py`):
   next week's Google search interest is predicted within **8–9%** for 전기차 and 갤럭시 (MAPE),
   but no model beats "same as last week" on Google (MASE ≥ 1.0). On Wikipedia the best case is
   갤럭시: **12% better than naive** (MASE 0.878) and up/down called right **62%** of the time
   (p = 0.0006 vs a coin flip). 80% prediction intervals catch the actual value **76%** of the time
   on average (49–98% by topic). Sudden jumps are missed: 스마트 안경 went to 100 against a
   forecast of 26.
3. **100% of the numbers in generated text are grounded in the run's own facts**:
   205 of 205, including 82 of 82 distinctive numbers (≥ 100 or with decimals). By
   chance, checked against another topic's facts, only 25% of distinctive numbers match.
4. **Jev's supported/partly verdicts do not match a human's** (30 hand-scored claims):
   50% raw agreement, Cohen's kappa −0.10, i.e. no better than chance. Jev is more often
   right when confident (70% agreement at confidence ≥ 0.8, 33% below 0.6), and it never rated
   as supported a claim the human called unsupported. So Jev's dot is a weak signal, which is
   why the numbers in the text are checked by code (point 3), not by Jev.

**Google Trends** gives a relative 0–100 index of how much people searched a term, not raw
counts (Google publishes none; Keyword Planner gives monthly ranges with an Ads account).
It is read through the endpoints the Trends website uses (`eval/gtrends.py`), which is not an
official API: it works from a home connection, is cached, and may be rate-limited or change.

## 1. Spike test: `eval/spike.py`

**Measures:** whether the last 24 hours' article count is unusual given the earlier days.
Daily counts are overdispersed, so a ratio or a Poisson test over-calls spikes. The
baseline days are fit with a negative binomial by the method of moments (p = mean/var,
r = mean·p/(1−p), sample variance; Poisson if var ≤ mean). Output: p = P(X ≥ today),
robust z = (today − median)/(1.4826·MAD), and a verdict: spike (p < 0.01), elevated
(p < 0.05), normal, or uncertain (capped) when a day hit Google News' 100-article limit.
The verdict goes to the writer as a measured fact, and code drops any sentence saying
급증/surge unless the verdict is "spike".

**Run:** `python midterm/eval/spike.py`

| topic | last 24h | baseline mean | baseline var | p | robust z | verdict |
|---|---|---|---|---|---|---|
| 전기차 (2026-10-11) | 72 | 41.2 | 351.0 | 0.069 | 1.67 | normal |
| 피지컬 AI (2026-10-19) | 120 | 68.3 | 955.1 | 0.066 | 1.53 | uncertain (capped) |
| 갤럭시 | 37 | 44.3 | 1029.9 | 0.51 | 0.08 | normal |
| physical AI | 39 | 46.8 | 83.4 | 0.82 | −2.43 | normal |
| 스마트 안경 | 0 | 15.8 | 27.0 | 1.00 | −6.74 | normal |

The 전기차 day is the self-check: Poisson gives p = 8.6e-6 ("spike"), the negative binomial
p = 0.069 ("normal"). The old ratio called 전기차 1.7× and 피지컬 AI (2026-10-11) 2.17×,
which the writer described as a surge; the test calls the latter only "elevated" (p = 0.034).

## 2. Ground truth: `eval/groundtruth.py` (+ `eval/gtrends.py`, `eval/wiki.py`)

**Measures:** whether daily Google News counts move with two independent measures of public
interest: daily Google search interest (Google Trends index, Korean days) and daily Wikipedia
pageviews (Wikimedia REST API, human users). Spearman correlation with its p-value, and
lead-lag correlation for lags −3..+3 (lag k = news on day t vs interest on day t+k). Under 7
overlapping days, no number is reported. Responses are cached in `data/eval/`.

**Run:** `python midterm/eval/groundtruth.py --days 90` (Google daily data covers 90 days)

| topic | Google ρ (p) | Wikipedia ρ (p) | best lag (Google / Wiki) | capped news days |
|---|---|---|---|---|
| 피지컬 AI | **+0.40 (0.0001)** | **+0.27 (0.011)** | 0 / 0 | 69/90 |
| physical AI | +0.14 (0.20) | **+0.32 (0.002)** | 0 / 0 | 46/90 |
| 전기차 | **+0.24 (0.023)** | −0.14 (0.18) | 0 / −3 | 74/90 |
| 스마트 안경 | **+0.23 (0.031)** | +0.03 (0.78) | −3 / 0 | 3/90 |
| 갤럭시 | −0.09 (0.39) | +0.13 (0.23) | −2 / 0 | 64/90 |

Bold = p < 0.05. Over 30 days only 피지컬 AI was significant and its best lag was −1 (searches a
day before news); with 90 days the best lag is 0, so the data do not show news leading interest
or the other way round. Caveats: most news days hit Google's 100-article limit (counts are
minimums); Korean Wikipedia traffic is small (Koreans use 나무위키); Google days are KST and
news days UTC.

## 3. Forecasts and backtest: `eval/forecast.py`, `eval/score_predictions.py`

**Measures:** how well the next 7 days of pageviews can be predicted. Models: naive (last 7
days repeated), 28-day mean, simple exponential smoothing (alpha picked on past errors only),
and exponential decay after a detected spike (half-life fit on post-peak days). Rolling
origin, step 1 day, over up to the last 2 years; each forecast uses only data up to its day.
Metrics: MAE of the 7-day sum, MASE (= MAE / naive MAE; < 1 beats naive), direction hit rate
vs the last 7 days, and half-life error after spikes.

**Run:** `python midterm/eval/forecast.py` → `data/eval/backtest_<date>.{md,json}`

| topic | history | origins | naive MAE | mean28 MASE | ses MASE | decay MASE | best |
|---|---|---|---|---|---|---|---|
| 갤럭시 | 3.0 y | 730 | 59.4 | 0.970 | **0.908** | 0.940 | ses |
| physical AI | 0.4 y ⚠ | 96 | 9.2 | **0.934** | 1.042 | 1.141 | mean28 |
| 스마트 안경 | 2.8 y | 730 | 19.3 | 1.118 | **0.994** | 1.031 | ses |
| 전기차 | 3.0 y | 730 | 22.2 | 1.289 | 1.099 | 1.159 | naive |
| 피지컬 AI | 1.0 y ⚠ | 302 | 447.7 | 1.091 | 1.105 | 1.182 | naive |

⚠ under the 2 years asked for: those Wikipedia articles are new. Direction hit rates are
0.49–0.65 (a coin flip is 0.5). The decay model predicts half-lives within a median of
1.1–2.2 days but never beats naive overall; right after spikes the 28-day mean does better
(post-spike MASE 0.71–0.98 on four topics).

**Live predictions:** every saved live analysis logs one falsifiable prediction (next 7 days
of pageviews, point and an 80% interval from the backtest's error quantiles, model = best by
MASE) to `data/predictions.jsonl`. Five are logged for 2026-10-19..25:

| topic | predicted 7-day views | 80% interval | model |
|---|---|---|---|
| 갤럭시 | 373 | 247–544 | ses |
| 피지컬 AI | 303 | 183–518 | naive |
| 스마트 안경 | 126 | 82–206 | ses |
| physical AI | 44 | 40–100 | mean28 |
| 전기차 | 40 | 26–57 | naive |

**Score them** after 2026-10-26 (once Wikimedia publishes the 25th):
`python midterm/eval/score_predictions.py`.

## 3b. Prediction accuracy on unseen data: `eval/prediction_test.py`

**Measures:** how accurate the forecasts are on a period never used to build them. At every
origin the forecast uses only past data. The model (lowest error) and the 80% interval (10th–90th
percentile of actual/predicted on recent training origins) are chosen on training origins only;
the most recent period is the holdout: 52 weeks of Google next-week interest (5 years of weekly
data; models naive, 4-week mean, exponential smoothing, same week last year) and 180 days of
Wikipedia 7-day sums. Metrics: MAE, MASE vs naive, MAPE, interval coverage (should be near 80%),
direction hit rate with a one-sided binomial test against a coin flip.

**Run:** `python midterm/eval/prediction_test.py` → `data/eval/prediction_test.{md,json}`

| source | topic | model (chosen on training) | holdout n | MASE vs naive | MAPE | 80% coverage | direction hit (p vs coin) |
|---|---|---|---|---|---|---|---|
| Google weekly | 전기차 | ses | 52 | 1.055 | 7.9% | 83% | 58% (0.17) |
| Google weekly | 갤럭시 | naive | 52 | 1.000 | 9.2% | 60% | - |
| Google weekly | 스마트 안경 | mean4 | 52 | 1.011 | 26.7% | 94% | 61% (0.08) |
| Google weekly | 피지컬 AI | mean4 | 52 | 1.114 | 38.5% | 98% | 50% (0.56) |
| Google weekly | physical AI | naive | 52 | 1.000 | 14.9% | 98% | - |
| Wikipedia 7-day | 전기차 | naive | 180 | 1.000 | 40.2% | 60% | - |
| Wikipedia 7-day | 갤럭시 | ses | 180 | **0.878** | 50.0% | 49% | **62% (0.0006)** |
| Wikipedia 7-day | 스마트 안경 | decay | 180 | 1.223 | 34.3% | 78% | 55% (0.10) |
| Wikipedia 7-day | 피지컬 AI | naive | 180 | 1.000 | 41.7% | 61% | - |
| Wikipedia 7-day | physical AI | too little history (21 origins) | | | | | |

When naive is chosen there is no up/down call (it always predicts "no change").

One real forecast per topic, made with data up to a week before the latest data:

| source | topic | data up to | predicted | 80% interval | actual |
|---|---|---|---|---|---|
| Google | 전기차 | 2026-10-04 | 55.8 | 47.6–63.5 | 54 ✓ |
| Google | 갤럭시 | 2026-10-04 | 56.0 | 51.8–60.1 | 55 ✓ |
| Google | 스마트 안경 | 2026-10-04 | 26.0 | 0–62.9 | **100 ✗** (sudden jump) |
| Google | 피지컬 AI | 2026-10-04 | 15.5 | 0–44.0 | 19 ✓ |
| Google | physical AI | 2026-10-04 | 17.0 | 11.3–25.5 | 16 ✓ |
| Wikipedia | 전기차 | 2026-10-11 | 35 | 23–49 | 40 ✓ |
| Wikipedia | 갤럭시 | 2026-10-11 | 361 | 252–510 | 389 ✓ (naive said 142) |
| Wikipedia | 스마트 안경 | 2026-10-11 | 45 | 28–75 | **152 ✗** |
| Wikipedia | 피지컬 AI | 2026-10-11 | 293 | 204–494 | 303 ✓ |

7 of 9 inside the interval; both misses are the same 스마트 안경 jump, which no past data
announced.

## 4. Number grounding: `eval/grounding.py`

**Measures:** whether every number the writer put in a sentence exists in that run's
facts or evidence, at the precision shown (68% vs a 0.68 share, 7,368억 vs 7368억, 2.2배 vs
2.17). Runs over every analysis ever saved, including versions pruned from `data/analysis/`
but still in git history. A control re-checks each run's numbers against other topics' facts
to show how often a number matches by chance.

**Run:** `python midterm/eval/grounding.py` → `data/eval/grounding.{md,json}`

13 analyses, 232 claims, 205 numbers: **205 grounded (100%)**, none ungrounded.

| numbers checked against | all numbers | distinctive (≥ 100 or decimal) |
|---|---|---|
| the run's own facts | 205/205 (100%) | 82/82 (100%) |
| another topic's facts (chance) | 1223/2003 (61%) | 202/800 (25%) |

Grounded means the number exists in the evidence, not that the sentence uses it correctly
(a right number in a wrong claim still passes).

## 5. Driver words and Jev agreement

**Driver words** (`eval/fightin.py`, used by `analyze_topic.py`): log-odds with an informative
Dirichlet prior (Monroe, Colaresi & Quinn 2008), α0 = 500, keep z > 1.96. Run
`python midterm/eval/fightin.py` for its self-check.
The '카지노' report checks out: on the 2026-10-11 전기차 headlines it is genuinely
over-represented (z = 2.55), because those runs analysed a collection made before the spam
filter existed, or reused it without `--refresh`. No frequency statistic can reject it; the
fix is that the analysis now re-applies the spam filter to any loaded collection. On the
same data the drivers become 모델 (z = 2.35) and 중국차 (z = 2.06).

**Jev agreement** (`eval/jev_agreement.py`): 30 random Jev-checked claims (of 77) are in
`data/eval/jev_agreement.csv` with the evidence they cite. Fill `human_label` (supported /
partly / unsupported), then run `python midterm/eval/jev_agreement.py score` for Cohen's
kappa, a confusion table and agreement per Jev-confidence band. Limit: claims Jev rated
unsupported were deleted before saving, so the sample holds only claims Jev kept.

Result (2026-10-20): the human scored each claim 0–1 for how well its sources support it
(column `human_score`), with a band around 0.5 as the middle: above 0.6 supported, 0.4–0.6
partly, below 0.4 unsupported.

| | human: supported | partly | unsupported |
|---|---|---|---|
| Jev: supported | 14 | 6 | 0 |
| Jev: partly | 7 | 1 | 2 |

Agreement 50%, **kappa −0.10**. Other cut-offs give the same conclusion (kappa −0.10 to +0.06,
e.g. +0.06 with only exactly 0.5 as partly). Human scores are about the same for claims Jev
called supported (mean 0.73) and partly (0.66; Mann-Whitney p = 0.75). Calibration: agreement
33% when Jev's confidence is under 0.6, 50% at 0.6–0.8, 70% at 0.8 and above. The two claims
the human called unsupported were both rated partly by Jev (kept, with a yellow dot), not
supported.

## Not covered yet

- **The Cloudflare Worker (`midterm/worker/`) is not ported.** It still shows the momentum
  ratio path (it has no daily counts), uses share-ratio drivers, has no surge-word filter, no
  re-applied spam filter on stored data, and logs no predictions. Porting needs: spike verdict
  (needs counts the Worker cannot get; at least drop surge words, since without counts nothing
  can support them), log-odds drivers (`fightin.py` → JS), and the prediction log.
- Predictions can't be scored before 2026-10-26.
- Kappa is from one labeller; a second person's labels would show how much humans agree.
