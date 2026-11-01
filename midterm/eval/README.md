# Measurable validation

Three checks, each asking something about the analysis itself. Right or wrong is decided by
code and by people; no language model scores its own work. Run everything from the
`business-agent-lab` folder with the venv active. Every module runs its own assert-based
self-check first. After changing results, run `python midterm/eval/summary.py`: it collects
them for the page (the Cloudflare site needs a redeploy to show them).

| Check | Question | Status (2026-11-01) |
|---|---|---|
| Live predictions | Did what the analysis said will happen come true? | logging; first results from 2026-11-09 |
| Forecast accuracy | Can search interest be forecast better than a simple guess? | on Google, no |
| Jev vs a human | Does Jev's source check agree with a person? | waiting for blind labels |

## 1. Live predictions: `eval/score_predictions.py`

Every analysis now writes down what it expects, in a form code can check (local version:
`data/predictions.jsonl`; Cloudflare version: KV, served at `/api/predictions`):

- **Each "what is next" sentence has a test:** a Google News search and a minimum article
  count for the following 7 days, chosen by the writer before the week starts. Code counts the
  real articles. The same count for the week before is reported, so an easy bar is visible
  ("already met").
- **`search_interest`:** Google search interest in the topic, next 7 days vs last 7: up / down
  (more than 10% apart) or flat. It is compared with always saying "flat", because a forecast
  is only worth something if it beats "same as last week". Both weeks come from one Trends
  response, since Trends rescales its index per request.

**Run:** `python midterm/eval/score_predictions.py` → `data/eval/scored_predictions.json`.
Anything whose week is not over stays pending.

Limits: the writer chooses the bar, so it can pick an easy one; "already met" shows how often.
Google News shows at most 100 articles per query, so counts are per day and a capped day is
flagged. Each analysis's score is one small sample until many have accumulated.

The old log only forecast Wikipedia pageviews, which tested nothing the analysis said. Its
final result, kept in `data/eval/old_wikipedia_*`: **3 of 5** forecasts inside their 80% range
(week of 2026-10-19; the file also holds one duplicate 전기차 row, also outside).

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
| 갤럭시 | 3.0 y | 730 | 59.4 | 0.970 | **0.908** | 0.940 | ses |
| physical AI | 0.4 y ⚠ | 96 | 9.2 | **0.934** | 1.042 | 1.141 | mean28 |
| 스마트 안경 | 2.8 y | 730 | 19.3 | 1.118 | **0.994** | 1.031 | ses |
| 전기차 | 3.0 y | 730 | 22.2 | 1.289 | 1.099 | 1.159 | naive |
| 피지컬 AI | 1.0 y ⚠ | 302 | 447.7 | 1.091 | 1.105 | 1.182 | naive |

⚠ under the 2 years asked for: those Wikipedia articles are new. Direction hit rates are
0.49–0.65 (a coin flip is 0.5). The decay model predicts half-lives within a median of
1.1–2.2 days but never beats naive overall; right after spikes the 28-day mean does better
(post-spike MASE 0.71–0.98 on four topics).

## 3. Jev vs a human: `eval/jev_agreement.py`

**Measures:** whether Jev's supported / partly / unsupported rating matches a person's, as
Cohen's kappa (agreement after removing what chance gives; 1 perfect, 0 chance level), with a
confusion table, forecasts vs other claims, and agreement per band of Jev's confidence.

**Run:**
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

- **The Cloudflare Worker** has no daily counts, so no spike note, and uses share-ratio drivers
  and no re-applied spam filter. It does share the forecast rules, Jev's rules and the
  prediction log; scoring runs in Python.
- Removed from validation on 2026-11-01 (see git history): news-vs-search correlation (the 100-article
  cap hit most days, e.g. 74 of 90 for 전기차) and number grounding (it only showed that a
  number exists in the sources, not that it is used correctly).
