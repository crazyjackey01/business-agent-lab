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

## Data sources

- Google Trends "Trending Now" RSS: `https://trends.google.com/trending/rss?geo=KR` (real-time, last ~24h)
- Google News search RSS (real-time, per topic)
- Google autocomplete (real-time, per topic)
- Wikipedia Pageviews API (most viewed articles; daily, so the latest full day is yesterday)
- Later: Naver DataLab API (needs a free key) to check whether a spike is real
