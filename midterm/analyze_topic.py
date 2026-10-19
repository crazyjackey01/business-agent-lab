"""Connect what people search for with what is happening, and what is likely next.

Input: the latest result from topic_trends.py for a topic (or a fresh run).

Two layers, so the conclusions rest on facts and not on guesses:

  1. Measured facts (plain code, no AI):
     - search intent: what people want from the topic (buying, how-to, investing, ...),
       from autocomplete phrases; Jev sorts every phrase (intent.py)
     - news drivers: words significantly more frequent in the last 24 hours' headlines
       (log-odds with a Dirichlet prior, eval/fightin.py)
     - scheduled events: dates and launch/event words found in headlines
     - coverage trend: daily article counts and momentum, across saved runs too
  2. Explanation (language model through OpenRouter):
     The model gets only the facts above, each with an id ([D1], [S3], ...).
     Every claim it makes must cite ids. Claims that cite nothing, or cite ids
     that do not exist, are removed.
  3. Check: each claim is rated supported / partly / unsupported against the exact
     evidence it cites. Jev (a decision model that can only pick one of those three
     labels, with probabilities) does this when OPENCODE_API_KEY is set; otherwise
     a second text-model call. Unsupported claims are removed; "partly" claims stay
     but are marked, and low-confidence ratings are flagged.

Usage:
    python midterm/analyze_topic.py --topic "피지컬 AI"
    python midterm/analyze_topic.py --topic "피지컬 AI" --refresh   # collect first
"""
import argparse
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jev_api
from intent import search_intent
from model_api import ModelRequestError, parse_json_reply, request_model
from eval.fightin import Z_CUTOFF, log_odds_z
from eval.forecast import log_prediction
from eval.spike import spike_test
from topic_trends import RESULT_DIR, analyze_topic, is_spam, save_result

HERE = Path(__file__).resolve().parent
ANALYSIS_DIR = HERE / "data" / "analysis"

# News drivers -----------------------------------------------------------------

# Korean particles that stick to the end of words ("KAIST가", "정의선의").
PARTICLES = ("에서", "으로", "까지", "부터", "에게", "은", "는", "이", "가", "을", "를", "의",
             "에", "와", "과", "도", "로", "만")
STOPWORDS = {"the", "and", "for", "with", "from", "into", "its", "how", "why", "what", "new",
             "are", "will", "has", "this", "that", "it", "is", "to", "of", "in", "on", "as", "at",
             "by", "an", "now", "be", "can", "after", "over", "more", "your", "you", "says", "종합", "속보", "단독", "포토", "영상", "기자"}


def headline_words(title, topic_words):
    words = set()
    for raw in re.findall(r"[\w·]+", title.lower()):
        for p in PARTICLES:
            if len(raw) > len(p) + 1 and raw.endswith(p) and not raw.isascii():
                raw = raw[: -len(p)]
                break
        if len(raw) < 2 or raw.isdigit() or raw in STOPWORDS or raw in topic_words:
            continue
        words.add(raw)
    return words


def news_drivers(news, topic, top=12, now=None):
    """Words significantly more frequent in the last 24 hours' headlines than in earlier ones.

    Log-odds with an informative Dirichlet prior ("Fightin' Words", eval/fightin.py) on
    headline counts; words with z > 1.96 are kept. Unlike a share ratio, a word seen in
    3 recent headlines and none before does not get an infinite score.
    """
    topic_words = {w.lower() for w in re.split(r"\s+", topic)} | {topic.lower().replace(" ", "")}
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(hours=24)
    today_count, before_count = Counter(), Counter()
    today_n = before_n = 0
    for a in news:
        words = headline_words(a["title"], topic_words)
        if datetime.fromisoformat(a["published"]) >= cutoff:
            today_count.update(words)
            today_n += 1
        else:
            before_count.update(words)
            before_n += 1

    z = log_odds_z(today_count, before_count)
    drivers = [
        {
            "word": word,
            "headlines_today": today_count[word],
            "share_today": round(today_count[word] / today_n, 2),
            "share_before": round(before_count[word] / before_n, 3) if before_n else 0,
            "z": round(z[word], 2),
        }
        for word in today_count if z.get(word, 0) > Z_CUTOFF
    ]
    drivers.sort(key=lambda d: -d["z"])
    return drivers[:top]


# Scheduled events -------------------------------------------------------------

DATE_PATTERNS = [
    r"\d{1,2}월\s?\d{1,2}일", r"\d{1,2}일", r"\d{1,2}/\d{1,2}", r"다음\s?(주|달)", r"내년", r"하반기",
    r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? \d{1,2}", r"next (week|month|year)",
    r"\b20\d\d\b",
]
EVENT_WORDS = ["개최", "출시", "공개", "발표", "선포", "착공", "예정", "앞두고", "열린다", "박람회", "컨퍼런스",
               "launch", "unveil", "to open", "will", "summit", "conference", "expo", "plans", "set to"]


def scheduled_events(news, limit=15):
    """Headlines that announce something with a date or a future-event word."""
    events = []
    for a in news:
        # Headline plus summary, when the source gives one: summaries often carry the dates.
        title = f"{a['title']} {a.get('summary', '')}".lower()
        dates = [m.group(0) for p in DATE_PATTERNS for m in re.finditer(p, title)]
        words = [w for w in EVENT_WORDS if w in title]
        if dates and words:
            events.append({**a, "dates_mentioned": dates, "event_words": words})
    return events[:limit]


# Coverage history across saved runs --------------------------------------------

def coverage_history(topic):
    """Momentum from every earlier saved run of this topic, oldest first."""
    history = []
    for path in sorted(RESULT_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data["topic"] == topic:
            m = data["news_momentum"]
            history.append({"collected_at": data["collected_at"], "today": m["today"],
                            "momentum": m["momentum"]})
    return history


# Model explanation --------------------------------------------------------------

SYSTEM_PROMPT = """You are a careful trend analyst. You explain why people are searching for a topic,
what is happening, and what is likely to happen next.

Rules:
- Use ONLY the evidence given. Each evidence item has an id like [D1] (measured data) or [S4] (a news headline).
- Every claim must list the ids that support it in "cites". A claim with no support must not be written.
- Headlines tell you what was reported, not the full story. Say "reported" when that matters.
- "outlook" items are forecasts. Base each one on a scheduled event or a measured trend in the evidence,
  give a confidence (low / medium / high), and say in "basis" which evidence it extends.
  Do not forecast prices or anything the evidence does not touch.
- Be brief. "summary": one or two sentences answering "why is this being searched now?".
  At most 3 why_people_search, 5 what_is_happening, 3 outlook items, each one or two short
  sentences. Do not repeat a number the reader already sees in the data (like intent shares)
  unless it is the point. Prefer the most important facts over covering everything.
- Style: write like a Korean wire-news brief (연합뉴스 style). Short declarative sentences.
  Lead with the concrete fact (who, what, number, date). No filler or hedging phrases such as
  "~것으로 보입니다", "관심이 모였습니다", "주목받았습니다", "~라는 점에서", "다양한", "본격화".
  Do not describe the data source in the sentence ("자동완성에서", "보도에 따르면") unless needed;
  the citation already shows where it came from. Use "~했다/~이다" endings, not "~습니다".
- Write every claim, basis and caveat in {language}.

Reply with JSON only, in this shape:
{
  "summary": {"claim": "...", "cites": ["D2", "S1"]},
  "why_people_search": [{"claim": "...", "cites": ["D1", "S3"]}],
  "what_is_happening": [{"claim": "...", "cites": ["S1", "S2"]}],
  "outlook": [{"claim": "...", "basis": "...", "confidence": "medium", "cites": ["S5", "D2"]}],
  "caveats": ["..."]
}"""


def build_evidence(facts, news, max_headlines=40):
    """Number every fact and headline so the model can cite them.

    Returns the evidence texts and the article link for each headline id.
    """
    evidence = {}
    m = facts["coverage"]
    sp = facts["spike"]
    evidence["D1"] = (
        f"News articles per 24-hour window for the last {len(m['per_day'])} days, newest first: {m['per_day']}. "
        f"Spike test (negative binomial fit to the earlier days, decided by statistics, not by you): "
        f"last 24 hours {sp['today']} vs baseline mean {sp['baseline_mean']}, p = {sp['p_value']:.3g}, "
        f"verdict: {sp['verdict']}. State this verdict as given. "
        + ("Only because the verdict is 'spike' may you call it a surge (급증)."
           if sp["verdict"] == "spike" else
           "Do NOT call it a surge, spike, jump or 급증/급등/폭증; describe it as the verdict says.")
    )
    evidence["D2"] = "Search intent from Google autocomplete (share of suggestions): " + "; ".join(
        f"{i['intent']} {int(i['share'] * 100)}% (e.g. {', '.join(i['examples'][:3])})" for i in facts["intent"]
    )
    evidence["D3"] = ("Words significantly more frequent in the last 24 hours' headlines than earlier "
                      "(log-odds z > 1.96): " + ("; ".join(
                          f"{d['word']} in {d['headlines_today']} headlines (z={d['z']})" for d in facts["drivers"])
                          or "none"))
    if facts["trends_matches"]:
        evidence["D4"] = "Matching Google Trends searches right now: " + "; ".join(
            f"{t['term']} ({t['traffic_text']})" for t in facts["trends_matches"]
        )
    if len(facts["history"]) > 1:
        evidence["D5"] = "Momentum in earlier runs, oldest first: " + "; ".join(
            f"{h['collected_at'][:16]} {h['momentum']}" for h in facts["history"]
        )

    # Headlines: scheduled-event ones first, then the newest, without duplicates.
    chosen, seen = [], set()
    for a in facts["events"] + news:
        if a["url"] not in seen:
            seen.add(a["url"])
            chosen.append(a)
    links = {}
    for n, a in enumerate(chosen[:max_headlines], start=1):
        evidence[f"S{n}"] = f"{a['published'][:10]} | {a['source']} | {a['title']}"
        links[f"S{n}"] = a["url"]
    return evidence, links


def keep_supported(claims, evidence):
    """Keep claims whose citations all exist; report how many were dropped."""
    kept, dropped = [], 0
    for c in claims or []:
        cites = [str(x).strip("[] ") for x in c.get("cites", [])]
        if cites and all(x in evidence for x in cites):
            kept.append({**c, "cites": cites})
        else:
            dropped += 1
    return kept, dropped


# Words that claim a spike. Allowed only when the spike test's verdict is "spike";
# this is checked in code, not left to the model.
SURGE_WORDS = re.compile(r"급증|급등|폭증|폭발적|치솟|surg|spik|soar|skyrocket|explod", re.IGNORECASE)


def drop_surge_claims(result, sections, verdict):
    """Remove claims that call it a surge when the measured verdict is not 'spike'."""
    if verdict == "spike":
        return 0
    removed = 0
    for section in sections:
        kept = [c for c in result.get(section, []) if not SURGE_WORDS.search(c["claim"])]
        removed += len(result.get(section, [])) - len(kept)
        result[section] = kept
    return removed


def explain(topic, evidence, language, verdict=None):
    evidence_text = "\n".join(f"[{k}] {v}" for k, v in evidence.items())
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.replace("{language}", language)},
        {"role": "user", "content": f"Topic: {topic}\n\nEvidence:\n{evidence_text}"},
    ]
    reply = parse_json_reply(request_model(messages).get("content"))

    result, dropped = {}, 0
    for section in ("why_people_search", "what_is_happening", "outlook"):
        result[section], n = keep_supported(reply.get(section), evidence)
        dropped += n
    result["caveats"] = reply.get("caveats", [])
    result["unsupported_claims_removed"] = dropped
    result["summary"], _ = keep_supported([reply["summary"]] if reply.get("summary") else [], evidence)
    result["surge_claims_removed"] = drop_surge_claims(result, ("summary",) + SECTIONS, verdict)
    result["failed_check_removed"] = check_claims(result, evidence, language, ("summary",) + SECTIONS)
    result["summary"] = result["summary"][0] if result["summary"] else None
    return result


CHECK_PROMPT = """You check claims against evidence. For each claim you get the exact evidence it cites.
Rate it:
- "supported": the cited evidence states it, or it follows directly.
- "partly": the core is in the evidence but the claim adds something the evidence does not say
  (an exaggeration, a cause, a trend over time that was measured only once).
- "unsupported": the cited evidence does not say it, or is about something else.
For forecasts ("outlook"), judge whether the basis is really in the evidence, not whether the future is certain.
Reply with JSON only: {"checks": [{"id": 0, "rating": "supported", "reason": "..."}]}
Write each reason in {language}, one short sentence."""


CHECK_LABELS = {
    "supported": "The cited evidence states the claim, or it follows directly.",
    "partly": "The core is in the evidence, but the claim adds something it does not say "
              "(an exaggeration, a cause, a trend measured only once).",
    "unsupported": "The cited evidence does not say this, or is about something else.",
}
UNCERTAIN_BELOW = 0.6  # Jev confidence under this is shown as uncertain


SECTIONS = ("why_people_search", "what_is_happening", "outlook")


def claim_items(result, sections=SECTIONS):
    return [(section, c) for section in sections for c in result[section]]


def claim_text(n, section, c, evidence):
    cited = "\n".join(f"    [{x}] {evidence[x]}" for x in c["cites"])
    claim = c["claim"] + (f" (basis: {c['basis']})" if c.get("basis") else "")
    return f"Claim {n} ({section}): {claim}\n  Cited evidence:\n{cited}"


def ratings_from_jev(items, evidence):
    """Jev rates every claim; each question names its claim in the shared state."""
    state = "Claims written by an analyst, each with the exact evidence it cites:\n\n" + "\n\n".join(
        claim_text(n, section, c, evidence) for n, (section, c) in enumerate(items))
    questions = {
        f"c{n}": {
            "type": "choice",
            "instructions": f"Does the cited evidence support Claim {n}? For a forecast, judge whether its "
                            "basis is really in the evidence, not whether the future is certain.",
            "criteria": CHECK_LABELS,
        }
        for n in range(len(items))
    }
    answers = jev_api.ask(state, questions)
    ratings = {}
    for n in range(len(items)):
        a = answers.get(f"c{n}", {})
        if a.get("choice") in CHECK_LABELS:
            ratings[n] = {"rating": a["choice"], "confidence": a.get("confidence"),
                          "probabilities": a.get("probabilities", {}), "by": "jev",
                          "reason": ""}
    return ratings


def ratings_from_model(items, evidence, language):
    messages = [
        {"role": "system", "content": CHECK_PROMPT.replace("{language}", language)},
        {"role": "user", "content": "\n\n".join(
            claim_text(n, section, c, evidence) for n, (section, c) in enumerate(items))},
    ]
    checks = parse_json_reply(request_model(messages).get("content"))["checks"]
    return {int(c["id"]): {**c, "by": "model"} for c in checks if str(c.get("id", "")).isdigit()}


def check_claims(result, evidence, language, sections=SECTIONS):
    """Second pass: rate every claim against its cited evidence. Returns how many were removed."""
    items = claim_items(result, sections)
    if not items:
        return 0
    ratings = None
    if jev_api.available():
        try:
            ratings = ratings_from_jev(items, evidence)
        except jev_api.JevError as error:
            result["jev_error"] = str(error)
    if not ratings:
        try:
            ratings = ratings_from_model(items, evidence, language)
        except (ModelRequestError, ValueError, KeyError) as error:
            result["check_error"] = str(error)
            return 0
    result["checked_by"] = next(iter(ratings.values()))["by"] if ratings else "none"

    removed = 0
    for section in sections:
        kept = []
        for c in result[section]:
            n = next(i for i, (_, item) in enumerate(items) if item is c)
            check = ratings.get(n, {"rating": "unchecked", "reason": ""})
            if check["rating"] == "unsupported":
                removed += 1
                continue
            confidence = check.get("confidence")
            kept.append({**c, "check": check["rating"], "check_reason": check.get("reason", ""),
                         "check_confidence": confidence,
                         "check_uncertain": confidence is not None and confidence < UNCERTAIN_BELOW})
        result[section] = kept
    return removed


# Relevance filter -----------------------------------------------------------------
# Before the writer sees any news, Jev answers yes/no for each article: is it mainly
# about the topic? Off-topic articles are dropped, so the writer reads less and cannot
# cite something unrelated. The daily counts were measured before this step.

RELEVANT_AT = 0.5  # Jev's probability of "yes" needed to keep an article


def relevant_news(news, topic):
    """Returns (kept articles, dropped articles, method)."""
    if not news or not jev_api.available():
        return news, [], "not filtered"
    state = f'News articles found for the search topic "{topic}":\n\n' + "\n".join(
        f"[{n}] {a['source']} | {a['title']}" + (f" | {a['summary']}" if a.get("summary") else "")
        for n, a in enumerate(news))
    questions = {
        f"a{n}": {"type": "noul",
                  "instructions": f"Is article [{n}] mainly about {topic}, rather than mentioning it "
                                  "in passing or being unrelated?"}
        for n in range(len(news))
    }
    try:
        answers = jev_api.ask(state, questions)
    except jev_api.JevError as error:
        return news, [], f"not filtered ({error})"
    kept, dropped = [], []
    for n, a in enumerate(news):
        p = answers.get(f"a{n}", {}).get("noul")
        (kept if p is None or p >= RELEVANT_AT else dropped).append({**a, "relevance": p})
    return kept, dropped, "Jev"


# Run ----------------------------------------------------------------------------

def latest_result(topic):
    paths = sorted(RESULT_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data["topic"] == topic:
            return data
    return None


def analyze(topic, lang="ko", geo="KR", refresh=False):
    data = None if refresh else latest_result(topic)
    if data is None:
        data = analyze_topic(topic, lang, geo)
        save_result(data)

    # Re-apply the spam filter: saved collections made before it existed (or reused without
    # --refresh) still contain keyword-stuffed gambling headlines ('카지노' in 전기차, 2026-10-11).
    data = {**data, "news": [a for a in data["news"] if not is_spam(a["title"], topic)]}
    kept, dropped, relevance_method = relevant_news(data["news"], topic)
    data = {**data, "news": kept}
    # "Last 24 hours" relative to when the news was collected, not to now.
    drivers = news_drivers(data["news"], topic, now=datetime.fromisoformat(data["collected_at"]))
    intent_method, intents = search_intent(data["related_searches"], topic)
    m = data["news_momentum"]
    facts = {
        "coverage": m,
        "spike": spike_test(m["per_day"][0], m["per_day"][1:], m.get("capped_windows")),
        "spam_removed": data.get("news_spam_removed", 0),
        "intent": intents,
        "intent_method": intent_method,
        "drivers": drivers,
        "events": scheduled_events(data["news"]),
        "relevance": {
            "method": relevance_method,
            "kept": len(kept),
            "dropped": [{"title": a["title"], "source": a["source"], "url": a["url"],
                         "relevance": a["relevance"]} for a in dropped],
        },
        "trends_matches": data["google_trends_matches"],
        "history": coverage_history(topic),
    }
    evidence, links = build_evidence(facts, data["news"])
    try:
        explanation = explain(topic, evidence, "Korean" if lang == "ko" else "English", facts["spike"]["verdict"])
    except (ModelRequestError, ValueError) as error:
        explanation = {"error": str(error)}

    return {
        "topic": topic,
        "geo": data["geo"],
        "source_collected_at": data["collected_at"],
        "analyzed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "facts": facts,
        "evidence": evidence,
        "evidence_links": links,
        "related_searches": data["related_searches"],
        "explanation": explanation,
    }


def save_analysis(analysis):
    # Every saved live analysis also logs one falsifiable, scoreable prediction
    # (next 7 days of Wikipedia pageviews; see eval/forecast.py and eval/score_predictions.py).
    try:
        analysis["prediction"] = log_prediction(analysis["topic"])
    except Exception as error:  # a forecast failure must not lose the analysis
        analysis["prediction"] = {"error": str(error)}
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^\w]+", "-", analysis["topic"]).strip("-").lower()
    path = ANALYSIS_DIR / f"{slug}_{datetime.now():%Y-%m-%d_%H%M}.json"
    path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def print_analysis(a):
    f, e = a["facts"], a["explanation"]
    print(f"\n=== {a['topic']} ({a['geo']}) ===")
    print("\nMeasured facts")
    print(f"  coverage per day, today first: {f['coverage']['per_day']} -> momentum {f['coverage']['momentum']}")
    print("  search intent: " + ", ".join(f"{i['intent']} {int(i['share'] * 100)}%" for i in f["intent"]))
    print("  news drivers (log-odds z): " + (", ".join(f"{d['word']}({d['z']})" for d in f["drivers"]) or "none"))
    print(f"  scheduled-event headlines: {len(f['events'])}")
    for ev in f["events"][:5]:
        print(f"    - {ev['title'][:70]} ({', '.join(ev['dates_mentioned'])})")

    if "error" in e:
        print(f"\nExplanation failed: {e['error']}")
        return
    for section, label in [("why_people_search", "Why people search it"),
                           ("what_is_happening", "What is happening"),
                           ("outlook", "What is likely next")]:
        print(f"\n{label}")
        for c in e[section]:
            extra = f" [{c.get('confidence', '')}] basis: {c.get('basis', '')}" if section == "outlook" else ""
            conf = f" {int(c['check_confidence'] * 100)}%" if c.get("check_confidence") is not None else ""
            mark = "" if c.get("check") == "supported" and not c.get("check_uncertain") else \
                f" <{c.get('check')}{conf}{', uncertain' if c.get('check_uncertain') else ''}: {c.get('check_reason')}>"
            print(f"  - {c['claim']}  ({', '.join(c['cites'])}){extra}{mark}")
    if e["unsupported_claims_removed"]:
        print(f"\n({e['unsupported_claims_removed']} claim(s) without valid citations were removed)")
    print(f"\n(claims checked by: {e.get('checked_by', 'none')})")
    if e.get("failed_check_removed"):
        print(f"({e['failed_check_removed']} claim(s) failed the evidence check and were removed)")


def main():
    parser = argparse.ArgumentParser(description="Explain a topic's search trend from facts.")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--lang", default="ko")
    parser.add_argument("--geo", default="KR")
    parser.add_argument("--refresh", action="store_true", help="collect fresh data first")
    args = parser.parse_args()

    analysis = analyze(args.topic, args.lang, args.geo, args.refresh)
    print_analysis(analysis)
    print(f"\nSaved {save_analysis(analysis).relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
