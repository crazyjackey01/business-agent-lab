"""What is everyone searching for right now, and why? (The Python port of the
Worker's overview mode, used by app.py when no topic is typed.)

Google Trends' live list is the data: each trending search comes with its approximate
volume and the news articles Google links to it. Those articles are the evidence.
Jev sorts each trend into a category; the writer explains why each one trends and what
they have in common; every claim is checked against its evidence.
"""
from datetime import datetime, timedelta, timezone

import jev_api
from analyze_topic import check_claims, keep_supported, parse_json_reply
from collect_trends import fetch_google_trends, fetch_wikipedia_top
from model_api import ModelRequestError, MODEL, request_model

TREND_CATEGORIES = {
    "breaking_news": "an accident, disaster, crime or sudden news event",
    "politics": "politics, government, elections, diplomacy, North Korea",
    "economy": "stocks, companies, prices, the economy",
    "sports": "a match, player, team or sports result",
    "entertainment": "a TV show, celebrity, music, film or game",
    "scheduled_event": "a planned event, holiday, ceremony or announcement on a set date",
    "product_or_tech": "a product launch, app, gadget or technology",
    "weather_or_seasonal": "weather, seasons, seasonal food or activities",
    "other": "none of the above",
}

OVERVIEW_PROMPT = """You explain what people are searching for most right now, and why.
You get today's trending Google searches. Each comes with the news articles Google links to it.

Rules:
- Use ONLY the evidence given. Cite ids ([T3] for a trend's data, [S7] for an article) for every claim.
- "trends": for each trending search, ONE short sentence on why people are searching it, from its
  articles. Put the trend's exact search term in "term". If its articles do not explain it, skip it.
- "themes": at most three short claims about what the trends have in common (for example several sports
  results, or one news story behind several searches). Each must cite at least two trends.
- Style: write like a Korean wire-news brief (연합뉴스 style). Short declarative sentences.
  Lead with the concrete fact (who, what, number, date). No filler or hedging phrases such as
  "~것으로 보입니다", "관심이 모였습니다", "주목받았습니다", "~라는 점에서", "다양한", "본격화".
  Do not describe the data source in the sentence ("자동완성에서", "보도에 따르면") unless needed;
  the citation already shows where it came from. Use "~했다/~이다" endings, not "~습니다".
- Write in {language}.

Reply with JSON only:
{
  "trends": [{"term": "...", "claim": "...", "cites": ["T1", "S1"]}],
  "themes": [{"claim": "...", "cites": ["T1", "T4"]}]
}"""


def latest_wikipedia_top(wiki):
    """Yesterday's most-viewed pages, or the day before's if yesterday is not published yet."""
    today = datetime.now(timezone.utc).date()
    for back in (1, 2):
        day = today - timedelta(days=back)
        try:
            return day.isoformat(), fetch_wikipedia_top(wiki, day)
        except Exception:
            continue
    return None, []


def categorize(trends):
    if not jev_api.available() or not trends:
        return {}
    state = "Trending Google searches right now, each with the headlines Google links to it:\n\n" + "\n".join(
        f'[{n}] "{t["term"]}": ' + (" / ".join(x["title"] for x in t["news"]) or "(no headlines)")
        for n, t in enumerate(trends))
    questions = {f"t{n}": {"type": "choice", "instructions": f'What kind of thing is trend [{n}] "{t["term"]}"?',
                           "criteria": TREND_CATEGORIES} for n, t in enumerate(trends)}
    try:
        return jev_api.ask(state, questions)
    except jev_api.JevError:
        return {}


def analyze_overview(geo="KR"):
    lang = "ko" if geo == "KR" else "en"
    trends = fetch_google_trends(geo)[:15]
    wiki_day, wiki_top = latest_wikipedia_top(lang)
    wiki_titles = [w["title"].lower() for w in wiki_top]
    categories = categorize(trends)

    evidence, links, rows, s = {}, {}, [], 0
    for n, t in enumerate(trends):
        term = t["term"].lower()
        on_wiki = any(term in w or w in term for w in wiki_titles)
        tid = f"T{n + 1}"
        evidence[tid] = f'Trending search "{t["term"]}", about {t["traffic_text"]} searches' + (
            ", also among the most-viewed Wikipedia pages" if on_wiki else "")
        for a in t["news"]:
            s += 1
            evidence[f"S{s}"] = f'article linked to "{t["term"]}" | {a["source"]} | {a["title"]}'
            links[f"S{s}"] = a["url"]
        c = categories.get(f"t{n}", {})
        rows.append({
            "id": tid, "term": t["term"], "traffic": t["traffic"], "traffic_text": t["traffic_text"],
            "on_wikipedia": on_wiki,
            "category": c.get("choice") if c.get("choice") in TREND_CATEGORIES else None,
            "category_confidence": c.get("confidence"),
            "top_article": t["news"][0] if t["news"] else None,
        })

    language = "Korean" if lang == "ko" else "English"
    try:
        evidence_text = "\n".join(f"[{k}] {v}" for k, v in evidence.items())
        reply = parse_json_reply(request_model([
            {"role": "system", "content": OVERVIEW_PROMPT.replace("{language}", language)},
            {"role": "user", "content": f"Region: {geo}\n\nEvidence:\n{evidence_text}"},
        ]).get("content"))
        explanation, dropped = {}, 0
        for section in ("trends", "themes"):
            explanation[section], n = keep_supported(reply.get(section), evidence)
            dropped += n
        explanation["unsupported_claims_removed"] = dropped
        explanation["failed_check_removed"] = check_claims(explanation, evidence, language, ("trends", "themes"))
    except (ModelRequestError, ValueError) as error:
        explanation = {"error": str(error)}

    for r in rows:
        r["why"] = [c for c in explanation.get("trends", []) if c["term"] == r["term"]]

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {
        "kind": "overview", "topic": f"Trending now ({geo})", "geo": geo,
        "source_collected_at": now, "analyzed_at": now,
        "rows": rows, "evidence": evidence, "evidence_links": links,
        "wikipedia_top": wiki_top, "wiki_day": wiki_day,
        "explanation": explanation, "writer_model": MODEL,
    }
