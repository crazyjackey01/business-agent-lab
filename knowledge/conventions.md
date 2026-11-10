---
type: Reference
title: Conventions
description: Project rules on keys, commits, where to run commands, and data handling.
---

# Conventions

## Keys and secrets

- The OpenRouter key lives only in the lab-root `.env`, never in tracked files
  ([CLAUDE.md](../CLAUDE.md), [week-05/README.md](../week-05/README.md)).
- Check with `git check-ignore .env`, which must print `.env`
  ([week-05/README.md](../week-05/README.md), [week-07/README.md](../week-07/README.md)).
- Scripts never print the key ([week-05/model_api.py](../week-05/model_api.py) docstring).

## Git

- The professor grades the git history: commit after each meaningful change with a clear
  message ([CLAUDE.md](../CLAUDE.md)). Existing week-05 commits use a `week-05: ...` prefix
  (git log).

## Running programs

- Run scripts from the lab root by path, e.g. `python week-05/03_assistant.py`
  ([week-05 script docstrings](../week-05/03_assistant.py), [CLAUDE.md](../CLAUDE.md)).
  Scripts find `.env` relative to their own file, one folder up
  ([week-05/model_api.py](../week-05/model_api.py)).
- Start Claude Code at the lab root, not inside a week folder
  ([week-06/README.md](../week-06/README.md), [week-07/knowledge-bundle-exercise.md](../week-07/knowledge-bundle-exercise.md)).

## Data and outputs

- Data files are records: report problems, do not edit them
  ([week-06/analysis-method.md](../week-06/analysis-method.md)).
- Check model and skill output against a hand calculation or the source
  ([week-05/README.md](../week-05/README.md) exercise step 4, [week-06/README.md](../week-06/README.md)).

## This bundle

Saved information can be wrong or outdated; update the affected page when your work changes
something documented here ([week-07/knowledge-bundle-exercise.md](../week-07/knowledge-bundle-exercise.md)).
