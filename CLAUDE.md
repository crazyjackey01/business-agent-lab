# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project layout

Class repo for an agents course. Python, one shared venv and `.env` at the repo root.

- `week-05/` — class exercise: tool calling through OpenRouter (`model_api.py`, `tools.py`).
- `midterm/` — midterm project (due ~2026-10-26): trend-finding agent + a controlled
  AI-search manipulation demo. Plan and demo rules are in `midterm/README.md`.

## Commands

Run from the repo root with the venv (`source .venv/bin/activate`):

```sh
pip install -r week-05/requirements.txt          # requests, python-dotenv
python midterm/collect_trends.py [--geo KR --wiki ko]   # general trending searches
python midterm/topic_trends.py --topic "피지컬 AI"       # trends around one topic
python midterm/analyze_topic.py --topic "피지컬 AI"      # fact-based, cited explanation (needs .env key)
python midterm/build_dashboard.py --open                # write + open midterm/dashboard.html
python midterm/app.py                                   # local web app at localhost:8765: type any topic
```

Cloudflare Worker (`midterm/worker/`, Node at `~/.local/node/bin`):

```sh
cd midterm/worker && npx wrangler dev      # local, reads secrets from .dev.vars (git-ignored)
cd midterm/worker && npx wrangler deploy   # production (run eval/summary.py first: the Worker bundles its JSON)
```

Validation (`midterm/eval/`, numpy + scipy; each module runs assert self-checks first):

```sh
python midterm/eval/spike.py                 # negative binomial spike test on saved topics
python midterm/eval/gtrends.py               # Google Trends search interest (unofficial endpoints, cached)
python midterm/eval/groundtruth.py --days 90 # news counts vs Google interest + Wikipedia (Spearman, lead-lag)
python midterm/eval/prediction_test.py       # holdout prediction accuracy (Google weekly, Wikipedia 7-day)
python midterm/eval/forecast.py              # 7-day pageview forecasts, rolling backtest
python midterm/eval/score_predictions.py     # score data/predictions.jsonl once windows end
python midterm/eval/grounding.py             # numbers in generated text vs the run's facts
python midterm/eval/jev_agreement.py export|score   # hand-label CSV, Cohen's kappa
python midterm/eval/summary.py              # collect all results -> data/eval/summary.json (page + Worker)
```

There is no other test suite or linter. Rule for eval/: no LLM decides whether a spike is
real, a prediction was right, or a number is correct; results are in midterm/eval/README.md.

## Notes

- The API key lives only in `.env` (git-ignored). Never put keys in tracked files.
- The professor grades the git history: commit after each meaningful change with a clear message.
- Pipeline: `collect_trends.py` / `topic_trends.py` collect → `data/` JSON →
  `analyze_topic.py` (Jev relevance filter → measured facts → Sonnet writes with citations →
  Jev checks each claim; `jev_api.py`) →
  `build_dashboard.py` fills `dashboard_template.html` with every saved analysis and the eval
  summary (history tab). Elements with `data-how` explain on hover how that part was made.
  `app.py` serves the same template with `live: true`, which shows a search box that
  POSTs to `/api/analyze` and runs the whole pipeline for the typed topic.
- Search purpose lives in `intent.py` / `worker/src/intent.js`: Jev sorts every autocomplete
  phrase, with short category descriptions (short = fewer tokens; Jev re-reads them per phrase). Jev batches are
  capped at 100 questions: it refuses requests over ~60k tokens. Worker model calls are in
  `worker/src/models.js`.
- Empty topic = overview mode: `overview.py` / `analyzeOverview` (Google Trends + Jev categories
  + cited explanation). The page renders it with `overviewSection` in the template.
- Model replies are capped with max_tokens (MAX_REPLY_TOKENS); without it OpenRouter reserves
  credit for a 65k-token reply and fails on keys with a spending limit.
- Scripts import each other by module name, so run them by path (`python midterm/...`).
- `midterm/worker/src/` is a JavaScript port of the Python pipeline (collect.js ≈
  topic_trends + collect_trends, analyze.js ≈ analyze_topic + overview). Keep both in sync
  when changing the analysis logic. The worker imports `../dashboard_template.html` as text.
  Differences: the worker gets news from Gemini + Google Search (Google News refuses
  Cloudflare), so it has no daily counts (`news_momentum: null`); local counts use rolling
  24-hour windows.
- The page template is bilingual (`STR.ko` / `STR.en`, toggle in the tab bar); new interface
  strings go in both.
- `midterm/model_api.py` is a copy of week-05's (week-05 is not committed).
