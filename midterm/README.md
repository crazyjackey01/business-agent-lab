# Midterm: Trend-Finding Agent + AI Search Manipulation Demo

Deadline: ~2026-10-26 (started 2026-10-11)

## Goal

1. **Find what people are searching for right now** (starting with Korea), and explain
   *why* each topic is trending.
2. **Show that AI search answers are easy to manipulate** with a controlled,
   harmless demo: an invented term published only on pages I control.

## Demo rules (responsible test)

- The demo term is made up. Nobody else searches for it, so nobody is misled.
- No real people, products, health, finance, or news.
- Published only on my own pages (blog / GitHub Pages / LinkedIn / Velog).
- Professor told beforehand; pages taken down after the presentation.
- Every result is screen-recorded as evidence.

## Plan

| Days  | Work |
|-------|------|
| 1–2   | Repo setup, publish demo pages, trend collector |
| 3–5   | "Why it's trending" agent: related news, LLM summary, driver classification |
| 6–7   | Spike detection, lifespan prediction, log predictions to check later |
| 8–9   | Dashboard |
| 10–12 | Daily demo-term checks across AI search tools, score predictions |
| 13–15 | Write-up, rehearsal, take down demo pages |

## Run

From the `business-agent-lab` folder, with the venv active:

### Web app: type any topic

```sh
python midterm/app.py
```

Opens `http://localhost:8765` with a search box. Type any topic (전기차, 피지컬 AI,
smart glasses, ...) and it collects fresh searches and news, measures the facts, and
shows the cited analysis (about 1-1.5 minutes per search). Korean topics are searched
in Korea, others in the US, or pick the region. Each result is saved under `midterm/data/`.

### On Cloudflare (public server)

Live at **https://trend-signals.gimailft01.workers.dev** (running a search needs the class password).

`midterm/worker/` is the same app as a Cloudflare Worker (JavaScript port of the
pipeline, same page template). Analyses are stored in Workers KV.

What runs where on Cloudflare, and why:

| Step | Source / model | Note |
|---|---|---|
| Related searches | Google autocomplete | works from Cloudflare |
| Trending now | Google Trends RSS, Wikipedia | works from Cloudflare |
| News articles | **Gemini + Google Search** (official API) | the Google News feed refuses Cloudflare's servers (HTTP 503); only articles Google attached a citation to are kept; falls back across three Gemini models when one is busy |
| Writing the analysis | **Claude Sonnet 5.5** via OpenRouter | follows the cite-every-claim rules closely |
| Claim check, intent sorting | **Jev 1.13 (paid)** via OpenCode Zen | the free tier refuses Cloudflare (FreeUsageLimitError); paid works |

The Worker is pinned to Google Cloud's Seoul region (`placement` in `wrangler.jsonc`),
because Gemini refuses requests from some of the locations Cloudflare would otherwise use.
Daily news counts (momentum) are only available in the local version.

Deploy:

```sh
cd midterm/worker
npm install
npx wrangler login                          # once, opens the browser
npx wrangler kv namespace create ANALYSES   # once; put the id in wrangler.jsonc
npx wrangler secret put OPENROUTER_API_KEY
npx wrangler secret put SEARCH_PASSWORD
npx wrangler secret put GEMINI_API_KEY      # news via Google Search
npx wrangler secret put OPENCODE_API_KEY    # Jev (optional)
npx wrangler deploy
```

Local test: put `OPENROUTER_API_KEY=...` and `SEARCH_PASSWORD=...` in
`midterm/worker/.dev.vars` (git-ignored), then `npx wrangler dev`.

### Overview: leave the box empty

With no topic, the app explains **what everyone is searching for right now**:
Google Trends' live list (with the news Google links to each trend) is the evidence,
Wikipedia's most-viewed pages are a cross-check, Jev sorts each trend into a category
(sports, politics, entertainment, ...), the writer explains each trend and the common
themes from those articles only, and Jev checks every claim. About 15 s and $0.02.
Code: `overview.py` (local) and `analyzeOverview` in `worker/src/analyze.js`.

### Command line

```sh
python midterm/collect_trends.py               # Korea (Google Trends KR + Korean Wikipedia)
python midterm/collect_trends.py --geo US --wiki en
```

Each run saves a snapshot to `midterm/data/snapshots/`.

### Topic mode: trends around a topic you choose

```sh
python midterm/topic_trends.py --topic "피지컬 AI"
python midterm/topic_trends.py --topic "physical AI" --lang en --geo US --also humanoid robotics
python midterm/topic_trends.py                 # runs every topic in midterm/topics.json
```

For the topic it reports:
- **What people search with it**: Google autocomplete for the topic plus each
  starting letter (ㄱ–ㅎ / a–z), e.g. `피지컬 ai 관련주`, `피지컬 ai 전망`.
- **News momentum**: Google News articles counted per day for 7 days;
  today ÷ previous daily average (above 1 = more coverage than usual).
- **Google Trends matches**: current trending searches that mention the topic
  or one of the `--also` words.

Edit `topics.json` to change the watchlist. Results go to `midterm/data/topics/`.

### Analysis: connect searches to what is happening and what is next

```sh
python midterm/analyze_topic.py --topic "피지컬 AI"            # uses the latest topic_trends result
python midterm/analyze_topic.py --topic "피지컬 AI" --refresh  # collect fresh data first
python midterm/analyze_topic.py --topic "physical AI" --lang en --geo US
```

Built so conclusions rest on facts, not speculation:

1. **Measured facts (plain code)**: search intent shares (buying, investing, definition,
   technology, ...; word lists first, the model only labels phrases the lists miss), today's news drivers (words far more common than in earlier
   headlines), headlines announcing dated events, coverage history across runs.
2. **Explanation (LLM via OpenRouter)**: the model sees only those facts, each with an
   id (`[D1]` data, `[S4]` headline), and must cite ids for every claim. Claims citing
   nothing or nonexistent ids are dropped. Forecasts need a basis and a confidence.
   Before that, **Jev filters the news**: for each article it answers yes/no to "is this
   mainly about the topic?", and articles under 50% are dropped (and listed on the page).
   For 스마트 안경 locally it dropped 43 of 95 (leftover gambling spam, an AI-bubble
   column, XR-headset stories) for about $0.0001.
3. **Evidence check**: a second model call rates each claim against the exact
   evidence it cites. Unsupported claims are removed, "partly" ones are marked.

Spam filter: gambling sites stuff unrelated keywords (토토, 카지노, betting, ...) into
headlines to get into Google News. Those headlines are removed before counting and the
number removed is shown. For 스마트 안경 on 2026-10-11 it was 72 of 180 results (40%),
real-world evidence of how easily search results are gamed.

Known limits: headlines only (no article bodies); English autocomplete has a long
"other" tail; the check uses the same model, so it reduces but does not remove errors.

### Dashboard

```sh
python midterm/build_dashboard.py --open
```

Writes `midterm/dashboard.html` (one self-contained file) from the newest data and opens it.

## Data sources

- Google Trends "Trending Now" RSS: `https://trends.google.com/trending/rss?geo=KR` (real-time, last ~24h)
- Google News search RSS (real-time, per topic)
- Google autocomplete (real-time, per topic)
- Wikipedia Pageviews API (most viewed articles; daily, so the latest full day is yesterday)
- Later: Naver DataLab API (needs a free key) to check whether a spike is real
