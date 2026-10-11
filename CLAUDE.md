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
python midterm/topic_trends.py                          # every topic in midterm/topics.json
python midterm/analyze_topic.py --topic "피지컬 AI"      # fact-based, cited explanation (needs .env key)
python midterm/build_dashboard.py --open                # write + open midterm/dashboard.html
```

There is no test suite or linter yet.

## Notes

- The API key lives only in `.env` (git-ignored). Never put keys in tracked files.
- The professor grades the git history: commit after each meaningful change with a clear message.
- Pipeline: `collect_trends.py` / `topic_trends.py` collect → `data/` JSON →
  `analyze_topic.py` (facts → cited LLM explanation → second-pass claim check) →
  `build_dashboard.py` fills `dashboard_template.html` with the newest files.
- Scripts import each other by module name, so run them by path (`python midterm/...`).
- `midterm/model_api.py` is a copy of week-05's (week-05 is not committed).
