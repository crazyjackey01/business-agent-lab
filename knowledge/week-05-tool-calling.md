---
type: Playbook
title: "Week 05: tool-calling assistant"
description: How to run the Week 05 scripts, where tools are defined and registered, and how to add a tool.
---

# Week 05: tool-calling assistant

Exercise instructions and troubleshooting: [week-05/README.md](../week-05/README.md).

## Run (from the lab root, venv active)

As documented in [week-05/README.md](../week-05/README.md) (Run section) and each script's docstring:

```sh
python week-05/01_model_request.py     # one raw request, every part printed
python week-05/02_calculator_call.py   # the model requests a calculation; press Enter to run it
python week-05/03_assistant.py         # the assistant; type exit to quit
```

In the assistant, `gigachad mode` / `normal mode` switch its voice
([03_assistant.py](../week-05/03_assistant.py), `main`).

## Where things are

| What | Where |
| --- | --- |
| Model call, key loading, retries on HTTP 429 | `request_model` in [model_api.py](../week-05/model_api.py) |
| Default model and override | `DEFAULT_MODEL` in [model_api.py](../week-05/model_api.py); set `OPENROUTER_MODEL` in `.env` to change it |
| Tool functions and tool definitions | [tools.py](../week-05/tools.py) |
| Tool registration | `TOOLS` (definitions sent to the model) and `FUNCTIONS` (name → function) in [03_assistant.py](../week-05/03_assistant.py) |
| Tool loop, max 5 rounds per message | `answer` and `MAX_ROUNDS` in [03_assistant.py](../week-05/03_assistant.py) |
| Fictional schedule read by `read_schedule` and `motivate` | [data/schedule.json](../week-05/data/schedule.json) |
| Notes written by `save_note` (never overwrites) | `week-05/notes/` ([tools.py](../week-05/tools.py), `save_note`) |

Tools now in the code ([tools.py](../week-05/tools.py)): `calculator`, `read_schedule`,
`search_wikipedia` (English Wikipedia only), `save_note`, `convert_currency` (Frankfurter reference
rates), and `motivate` (calls a second "coach" model with the next seven days of the schedule).
The README's currency-conversion exercise is already done in the code.

## Adding a tool

The three required parts are listed in "If you finish early" in
[week-05/README.md](../week-05/README.md): a function in `tools.py`, a tool definition in
`tools.py` whose `"name"` matches the function, and an entry in both `TOOLS` and `FUNCTIONS` in
`03_assistant.py`. The model only reads definitions; the program runs the functions
([tools.py](../week-05/tools.py) docstring). Tool errors come back to the model as
`error: ...` text rather than crashing (`dispatch` in [03_assistant.py](../week-05/03_assistant.py)).

## Common failures

See "If something fails" in [week-05/README.md](../week-05/README.md) (missing key, HTTP 401, HTTP 429, model choice).
