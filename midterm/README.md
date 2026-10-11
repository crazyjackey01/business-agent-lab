# Midterm: Trend Signals + AI Search Manipulation Demo

Deadline: ~2026-10-26 (started 2026-10-11)

## Goal

1. **Find what people are searching for and explain why, from cited facts.** Type a topic
   (or nothing, for what is trending right now) and get a short briefing: why people
   search it, what is happening, what is likely next, every sentence linked to a source.
2. **Show that AI search answers are easy to manipulate** with a controlled, harmless demo:
   an invented term published only on pages I control.

Live: **https://trend-signals.gimailft01.workers.dev** (running an analysis needs the class password).

## Demo rules (responsible test)

- The demo term is made up. Nobody else searches for it, so nobody is misled.
- No real people, products, health, finance, or news.
- Published only on my own pages (blog / GitHub Pages / LinkedIn / Velog).
- Professor told beforehand; pages taken down after the presentation.
- Every result is screen-recorded as evidence.

## How it works

Two versions of the same app share one page template (`dashboard_template.html`):

| | Cloudflare Worker (`worker/`) | Local Python (`*.py`) |
|---|---|---|
| Where | public site | your computer (`python midterm/app.py`) |
| News | Gemini + Google Search (3 searches: topic + top 2 autocomplete phrases) | Google News feed, counted per 24-hour window |
| News momentum | not available (Google News refuses Cloudflare) | yes |
| Stored in | Workers KV | `midterm/data/` |

### Typing a topic

1. **Collect**: Google autocomplete for the topic plus each starting letter (ㄱ–ㅎ / a–z) shows
   what people type with it; news as in the table above. Keyword-stuffed gambling headlines
   are removed (for 스마트 안경 that was 72 of 180 Google News results).
2. **Filter (Jev)**: for each article, "is this mainly about the topic?"; under 50% is dropped.
3. **Measure (plain code)**: search-purpose shares (word lists; Jev labels what they miss),
   words suddenly frequent in the last 24 hours' headlines, dates in the news, momentum.
4. **Write (Claude Sonnet 5.5)**: sees only those numbered facts and articles and must cite ids
   for every sentence; sentences citing nothing or nonexistent ids are dropped. Wire-news style,
   a summary plus at most 3 / 5 / 3 points.
5. **Check (Jev)**: each sentence is rated supported / partly / unsupported against its own
   sources, with a probability. Unsupported sentences are removed; the page shows a colored dot.

### Leaving the box empty

Google Trends' live list is the data and the news Google links to each trend is the evidence.
Wikipedia's most-viewed pages are a cross-check, Jev sorts each trend into a category, Sonnet
writes one line per trend plus common themes, and Jev checks every sentence. About 10 s.

### Models and cost

| Job | Model | Cost per topic search |
|---|---|---|
| Find news (Cloudflare) | Gemini 3.5 Flash-Lite, then 3.6 / 3.8 Flash if it finds under 3 articles or is busy | free monthly allowance |
| Write | Claude Sonnet 5.5 via OpenRouter | about $0.03 (95% of the total) |
| Filter, sort, check | Jev 1.13 (TypeSafe) via OpenCode Zen | about $0.001 |

Jev can only answer with labels we give it, plus a probability, so it cannot invent text.
It filters and checks what Sonnet writes; it does not stop Sonnet from making mistakes.

## Run

From the `business-agent-lab` folder, with the venv active. Keys go in `.env`
(`OPENROUTER_API_KEY`, `OPENCODE_API_KEY`; see `week-05/env.example`).

```sh
python midterm/app.py                                   # web app at localhost:8765
python midterm/topic_trends.py --topic "피지컬 AI"       # collect only
python midterm/analyze_topic.py --topic "피지컬 AI"      # analyze the latest collection
python midterm/analyze_topic.py --topic "피지컬 AI" --refresh   # collect, then analyze
python midterm/collect_trends.py                        # trending searches snapshot
python midterm/build_dashboard.py --open                # offline copy: midterm/dashboard.html
```

`dashboard.html` is a self-contained offline copy of the newest results, a backup for the
presentation if the internet fails.

### Cloudflare

```sh
cd midterm/worker
npm install
npx wrangler login                          # once
npx wrangler secret put OPENROUTER_API_KEY  # writing
npx wrangler secret put GEMINI_API_KEY      # news via Google Search
npx wrangler secret put OPENCODE_API_KEY    # Jev
npx wrangler secret put SEARCH_PASSWORD
npx wrangler deploy
```

The Worker is pinned to Google Cloud's Seoul region (`placement` in `wrangler.jsonc`) because
Gemini refuses some locations Cloudflare would otherwise run it in. Free Jev refuses
Cloudflare, so the Worker uses paid `jev-1.13` (`JEV_MODEL`).

## Known limits

- Headlines and one-line summaries only, not full articles.
- Google News caps each query at 100 articles and its date filter is about a day off, so busy
  days are undercounted; the analysis is told when that happened.
- English autocomplete has a long "other" tail.
- No momentum on the Cloudflare version.

## Plan

| Days  | Work | Status |
|-------|------|--------|
| 1–2   | Repo setup, trend collector | done |
| 3–5   | "Why it's trending" agent | done (cited analysis, Jev checks) |
| 6–7   | Spike detection, lifespan prediction | momentum done; predictions not logged yet |
| 8–9   | Dashboard | done (live on Cloudflare) |
| —     | Publish demo pages | **not started: most time-critical** |
| 10–12 | Daily demo-term checks across AI search tools | |
| 13–15 | Write-up, rehearsal, take down demo pages | |
