---
type: Reference
title: Lab layout and setup
description: What each top-level folder holds and where the setup instructions are.
---

# Lab layout and setup

## Folders

| Path | What it is | Start with |
| --- | --- | --- |
| `week-05/` | Tool calling through OpenRouter: a terminal assistant with tools | [week-05/README.md](../week-05/README.md) |
| `week-06/` | Claude Code skills: a weekly ad-campaign review | [week-06/README.md](../week-06/README.md) |
| `week-07/` | RAG exercise and this knowledge-bundle exercise | [week-07/README.md](../week-07/README.md) |
| `midterm/` | Midterm project (trend-finding agent) | [CLAUDE.md](../CLAUDE.md), [midterm/README.md](../midterm/README.md) |
| `.claude/skills/` | Project skills: `campaign-review`, `caveman` | [campaign-review SKILL.md](../.claude/skills/campaign-review/SKILL.md) |
| `knowledge/` | This bundle | [index.md](index.md) |

## Setup

One Python venv (`.venv/`) and one `.env` sit at the lab root and are shared by the weeks
([CLAUDE.md](../CLAUDE.md); week 07 says to reuse the Week 05 environment and key,
[week-07/README.md](../week-07/README.md)).

- Full setup steps (key in `.env`, `.gitignore` lines, venv, `pip install`): the Setup section of
  [week-05/README.md](../week-05/README.md). The `.env` line format is in
  [week-05/env.example](../week-05/env.example).
- Week 05 needs only `requests` and `python-dotenv` ([week-05/requirements.txt](../week-05/requirements.txt)).
- Week 06 needs no API key; it runs inside Claude Code and needs Python 3
  ([week-06/README.md](../week-06/README.md)).
- Re-run `source .venv/bin/activate` in each new terminal ([README.md](../README.md),
  [week-05/README.md](../week-05/README.md)).

`.gitignore` excludes `/.env`, `/.venv/`, `__pycache__/` and some midterm build files
([.gitignore](../.gitignore)).
