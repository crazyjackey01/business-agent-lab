# Measurable validation

Three checks, decided by code and by people; no language model scores anything. Run everything
from the `business-agent-lab` folder with the venv active. Every module runs its own assert-based
self-check first. After changing results, run `python midterm/eval/summary.py`: it collects
them for the page (the Cloudflare site needs a redeploy to show them).

| Check | Question | Status (2026-11-01) |
|---|---|---|
| Live predictions | Did code's forecast of next week's searches come true? | logging; first results from 2026-11-08 |
| Forecast accuracy | Can search interest be forecast better than a simple guess? | on Google, no |
| Jev vs a human | Does Jev's source check agree with a person? | no: kappa −0.09 on 30 blind labels |

## 1. Live predictions: `eval/score_predictions.py`

Each analysis logs one forecast to `data/predictions.jsonl`, made entirely by code. The topic's
5 years of weekly Google Trends data choose the method with the smallest past error (same as last
week, 4-week mean, exponential smoothing, same week last year), and a range from the 10th-90th
percentile of actual/predicted over the last two years. The forecast is up / down (more than 10%
from this week) or flat.

Once the week is over, code compares this week and the forecast week as daily averages from one
Trends response, since Trends rescales its index per request. It reports direction hits, range hits,
and the hits from always saying "flat", because a forecast is only worth something if it beats that.

**Run:** `python midterm/eval/score_predictions.py` → `data/eval/scored_predictions.json`

Limits: the forecast is often "flat", because no method beats "same as last week" on this data
(section 2), so the direction score may simply equal the baseline; all four demo topics that could be
forecast said flat on 2026-11-01. Topics with under about 18 months of history get no forecast (피지컬 AI
today). The Cloudflare version has none: the forecasting code is Python only, and Google refuses Cloudflare for Google News, so its Trends data may not be reachable there either (not tested).

Two earlier logs are kept: `data/eval/old_wikipedia_*` forecast Wikipedia pageviews, which tested
nothing the analysis said (3 of 5 inside their 80% range, week of 2026-10-19; the file also holds a
duplicate 전기차 row, also outside), and `data/eval/old_writer_predictions.jsonl` is the single
forecast the writer model made in the short-lived version where it forecast with a Google News test.

**Google Trends** gives a relative 0–100 index of how much people searched a term, not raw
counts (Google publishes none; Keyword Planner gives monthly ranges with an Ads account).
It is read through the endpoints the Trends website uses (`eval/gtrends.py`), which is not an
official API: it works from a home connection, is cached, and may be rate-limited or change.

## 2. Forecast accuracy on unseen data: `eval/prediction_test.py`

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
| Google weekly | 전기차 | ses | 52 | 1.059 | 7.8% | 85% | 52% (0.44) |
| Google weekly | 갤럭시 | naive | 52 | 1.000 | 11.0% | 56% | - |
| Google weekly | 스마트 안경 | mean4 | 52 | 1.005 | 24.8% | 98% | 50% (0.56) |
| Google weekly | 피지컬 AI | too little history (24 origins, since the term appeared) | | | | | |
| Google weekly | physical AI | naive | 52 | 1.000 | 14.6% | 98% | - |
| Wikipedia 7-day | 전기차 | naive | 180 | 1.000 | 42.5% | 59% | - |
| Wikipedia 7-day | 갤럭시 | ses | 180 | **0.845** | 54.5% | 50% | **65% (p < 0.001)** |
| Wikipedia 7-day | 스마트 안경 | decay | 180 | 1.292 | 38.3% | 73% | 53% (0.25) |
| Wikipedia 7-day | 피지컬 AI | naive | 180 | 1.000 | 41.7% | 59% | - |
| Wikipedia 7-day | physical AI | too little history (34 origins) | | | | | |

Rerun 2026-11-01. When naive is chosen there is no up/down call (it always predicts "no change").

One real forecast per topic, made from a fixed earlier date:

| source | topic | data up to | predicted | 80% interval | actual |
|---|---|---|---|---|---|
| Google | 전기차 | 2026-10-04 | 51.0 | 43.0–58.2 | 48 ✓ |
| Google | 갤럭시 | 2026-10-04 | 48.0 | 43.6–52.3 | 45 ✓ |
| Google | 스마트 안경 | 2026-10-04 | 24.2 | 0–75.2 | **100 ✗** (sudden jump) |
| Google | physical AI | 2026-10-04 | 23.0 | 15.6–34.5 | 22 ✓ |
| Wikipedia | 전기차 | 2026-10-11 | 35 | 24–50 | 40 ✓ |
| Wikipedia | 갤럭시 | 2026-10-11 | 361 | 251–509 | 389 ✓ (naive said 142) |
| Wikipedia | 스마트 안경 | 2026-10-11 | 45 | 28–74 | **152 ✗** |
| Wikipedia | 피지컬 AI | 2026-10-11 | 293 | 208–483 | 303 ✓ |

6 of 8 inside the interval; both misses are the same 스마트 안경 jump, which no past data
announced.

### Backtest on Wikipedia pageviews: `eval/forecast.py`

**Measures:** how well the next 7 days of pageviews can be predicted. Models: naive (last 7
days repeated), 28-day mean, simple exponential smoothing (alpha picked on past errors only),
and exponential decay after a detected spike (half-life fit on post-peak days). Rolling
origin, step 1 day, over up to the last 2 years; each forecast uses only data up to its day.
Metrics: MAE of the 7-day sum, MASE (= MAE / naive MAE; < 1 beats naive), direction hit rate
vs the last 7 days, and half-life error after spikes.

**Run:** `python midterm/eval/forecast.py` → `data/eval/backtest_<date>.{md,json}`

| topic | history | origins | naive MAE | mean28 MASE | ses MASE | decay MASE | best |
|---|---|---|---|---|---|---|---|
| 갤럭시 | 3.0 y | 730 | 64.8 | 0.944 | **0.883** | 0.918 | ses |
| physical AI | 0.5 y ⚠ | 109 | 9.2 | **0.948** | 1.023 | 1.103 | mean28 |
| 스마트 안경 | 2.8 y | 730 | 19.7 | 1.120 | 1.000 | 1.059 | naive |
| 전기차 | 3.0 y | 730 | 21.4 | 1.297 | 1.078 | 1.147 | naive |
| 피지컬 AI | 1.0 y ⚠ | 315 | 431.7 | 1.088 | 1.106 | 1.182 | naive |

⚠ under the 2 years asked for: those Wikipedia articles are new. Rerun 2026-11-01; details in
`data/eval/backtest_2026-11-01.md`.

## 3. Jev vs a human: `eval/jev_agreement.py`

**Measures:** whether Jev's supported / partly / unsupported rating matches a person's, as
Cohen's kappa (agreement after removing what chance gives; 1 perfect, 0 chance level), with a
confusion table, forecasts vs other claims, and agreement per band of Jev's confidence.

**Run:**
**Result (2026-11-01, 30 claims, one labeller):** agreement 53%, kappa −0.09, so no better than
chance. Both rated 22 of 30 "supported", which is why chance agreement is already 57%.

| Jev \ human | supported | partly | unsupported |
|---|---|---|---|
| supported | 15 | 3 | 4 |
| partly | 7 | 1 | 0 |
| unsupported | 0 | 0 | 0 |

Jev never said "unsupported", so it passed all 4 claims the human rejected, and the human accepted
7 of the 8 it called "partly". Forecasts agreed on 1 of 5, other claims on 15 of 25. Agreement by
Jev's confidence: 38% (n=8), 50% (n=6), 62% (n=16), too few to call calibrated. With no second
labeller this cannot show which side is right. Several rejected claims closely restate their headlines
(#15, #20), so the two may be using different standards, such as whether the headline is enough.

1. `python midterm/eval/jev_agreement.py export` (already done: 30 claims in `data/eval/jev_agreement.csv`)
2. Fill `human_label` with `s`, `p` or `u`, using only the cited evidence. Optional:
   `second_label` from a second person shows how far two humans agree at all.
3. `python midterm/eval/jev_agreement.py score`

Don't open `data/eval/jev_agreement_key.json` before labelling: it holds Jev's answers.

**What changed, and why the old result is not used** (it is kept as `*_old_not_blind`; kappa
−0.10 on 30 claims):
- Jev's answers were next to the label column, so it was not blind. They are in a separate file now.
- Labels were scores converted with cut-offs picked after seeing results. Now they are direct labels.
- Jev's labels said "partly" = adds something the evidence does not say, which is true of any
  forecast: 17 of 22 saved forecasts got it, and in the sample the human disagreed on 4 of 5.
  Forecasts are now rated on whether their basis is in the evidence: 13 of 22 "partly" on
  the same forecasts. Whether that is right is what the new labels will show.
- Jev re-rates the sample under the current rules, and claims from the old round are excluded.
- The writer no longer forecasts, so forecasts in the sample come from older runs.
- Claims Jev removes are now saved and sampled, so the test can also catch wrongly removed
  claims. None exist yet in the sample, because older runs did not save them.

## Other statistics used by the analysis

**Driver words** (`eval/fightin.py`, used by `analyze_topic.py`): log-odds with an informative
Dirichlet prior (Monroe, Colaresi & Quinn 2008), α0 = 500, keep z > 1.96. Run
`python midterm/eval/fightin.py` for its self-check.
The '카지노' report checks out: on the 2026-10-11 전기차 headlines it is genuinely
over-represented (z = 2.55), because those runs analysed a collection made before the spam
filter existed, or reused it without `--refresh`. No frequency statistic can reject it; the
fix is that the analysis now re-applies the spam filter to any loaded collection. On the
same data the drivers become 모델 (z = 2.35) and 중국차 (z = 2.06).

**Spike note** (`eval/spike.py`): a negative binomial test on the last 7 days of article counts.
When p < 0.01 the page says it looks like a spike; otherwise it says nothing. Six earlier windows
and the 100-article cap can't support a firm result, so it changes nothing in the analysis and is
not a validation result.

## Not covered

- **The Cloudflare Worker** has no daily counts, so no spike note and no forecast, and it uses
  share-ratio drivers and no re-applied spam filter. It shares the word lists, headline filter and Jev's rules.
- **Word lists and the headline filter have no ground truth yet.** Against Jev's labels on 423 phrases
  from three topics the lists were not built from, they catch 32-48% and agree 78-91% when they do; the rest
  stay "other". The filter keeps 184 of 240 headlines Jev kept and rejects 230 of 305 it dropped, and it
  drops articles that use another name (a "버즈 온" headline under 갤럭시). Jev is not a reference for
  truth either, since it has not passed its own test.
- Removed from validation on 2026-11-01 (see git history): news-vs-search correlation (the 100-article
  cap hit most days, e.g. 74 of 90 for 전기차) and number grounding (it only showed that a
  number exists in the sources, not that it is used correctly).
