# Measurable validation

Every judgment about signals, predictions and accuracy below is made by deterministic
statistics compared against external ground truth. Language models only turn results
that are already decided into sentences; none of them decides whether a spike is real,
whether a prediction was right, or whether a number is correct.

Results as of 2026-10-19. Run everything from the `business-agent-lab` folder with the
venv active (`pip install -r midterm/requirements.txt` for numpy and scipy). Every module
runs its own assert-based self-check first.

## The three numbers to present

1. **Our news signal tracks real public interest for 1 of 5 topics.** 피지컬 AI:
   Spearman ρ = +0.48 (p = 0.007) between daily news counts and Wikipedia pageviews over
   30 days, and +0.75 when pageviews are compared one day earlier. The other four are
   not significant (ρ from −0.32 to +0.33). Korean Wikipedia is a weak ground truth
   (Koreans use 나무위키), and most news days hit Google's 100-article limit.
2. **Forecasts beat the naive "same as last week" forecast on 3 of 5 topics, by up to 9%**:
   MASE 0.908 for 갤럭시 (9% better), 0.934 for physical AI (7%), 0.994 for 스마트 안경
   (0.6%). For 전기차 and 피지컬 AI nothing beats naive.
3. **100% of the numbers in generated text are grounded in the run's own facts**:
   192 of 192, including 79 of 79 distinctive numbers (≥ 100 or with decimals). By
   chance, checked against another topic's facts, only 25% of distinctive numbers match.

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

## 2. Ground truth: `eval/groundtruth.py` (+ `eval/wiki.py`)

**Measures:** whether daily Google News counts move with daily Wikipedia pageviews
(Wikimedia REST API, human users, cached in `data/eval/wiki/`). Spearman correlation with
its p-value, and lead-lag correlation for lags −3..+3 (lag k = news on day t vs pageviews
on day t+k; best lag > 0 means news leads). Under 7 overlapping days, no number is reported.

**Run:** `python midterm/eval/groundtruth.py` (30 days by default; `--days 60`)

| topic | article | ρ (30 days) | p | best lag | r at best lag | capped news days |
|---|---|---|---|---|---|---|
| 피지컬 AI | ko: 피지컬 AI | **+0.48** | **0.007** | −1 (pageviews first) | +0.75 | 26/30 |
| physical AI | en: Physical AI | +0.33 | 0.078 | +1 (news first) | +0.60 | 19/30 |
| 스마트 안경 | ko: 스마트글래스 | +0.12 | 0.54 | +1 | +0.40 | 3/30 |
| 갤럭시 | ko: 삼성 갤럭시 | −0.06 | 0.74 | 0 | −0.06 | 19/30 |
| 전기차 | ko: 전기자동차 | −0.32 | 0.082 | −3 | +0.20 | 30/30 |

Read with care: five topics × seven lags is many comparisons, so only 피지컬 AI's ρ clears
a strict bar. 전기자동차 gets about 6 views a day, too few to track anything.

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

## 4. Number grounding: `eval/grounding.py`

**Measures:** whether every number the writer put in a sentence exists in that run's
facts or evidence, at the precision shown (68% vs a 0.68 share, 7,368억 vs 7368억, 2.2배 vs
2.17). Runs over every analysis ever saved, including versions pruned from `data/analysis/`
but still in git history. A control re-checks each run's numbers against other topics' facts
to show how often a number matches by chance.

**Run:** `python midterm/eval/grounding.py` → `data/eval/grounding.{md,json}`

12 analyses, 217 claims, 192 numbers: **192 grounded (100%)**, none ungrounded.

| numbers checked against | all numbers | distinctive (≥ 100 or decimal) |
|---|---|---|
| the run's own facts | 192/192 (100%) | 79/79 (100%) |
| another topic's facts (chance) | 1050/1750 (60%) | 176/713 (25%) |

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

## Not covered yet

- **The Cloudflare Worker (`midterm/worker/`) is not ported.** It still shows the momentum
  ratio path (it has no daily counts), uses share-ratio drivers, has no surge-word filter, no
  re-applied spam filter on stored data, and logs no predictions. Porting needs: spike verdict
  (needs counts the Worker cannot get; at least drop surge words, since without counts nothing
  can support them), log-odds drivers (`fightin.py` → JS), and the prediction log.
- Predictions can't be scored before 2026-10-26.
- Kappa needs your 30 labels.
