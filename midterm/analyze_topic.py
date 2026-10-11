"""Connect what people search for with what is happening, and what is likely next.

Input: the latest result from topic_trends.py for a topic (or a fresh run).

Two layers, so the conclusions rest on facts and not on guesses:

  1. Measured facts (plain code, no AI):
     - search intent: what kind of thing people ask about the topic
       (investing, definition, companies, outlook, ...), from autocomplete phrases
     - news drivers: words that appear much more in today's headlines than before
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
from datetime import datetime, timezone
from pathlib import Path

import jev_api
from model_api import ModelRequestError, request_model
from topic_trends import RESULT_DIR, analyze_topic, save_result

HERE = Path(__file__).resolve().parent
ANALYSIS_DIR = HERE / "data" / "analysis"

# Search intent ----------------------------------------------------------------

# Words in an autocomplete phrase that show what the searcher wants.
# Checked in this order; the first intent with a matching word wins.
# Korean words match inside longer words ("로봇팔" counts as 로봇).
INTENT_WORDS = {
    "problems": ["화재", "리콜", "고장", "결함", "사고", "문제", "논란", "부작용", "위험", "단점", "recall",
                 "problems", "issues", "fire", "lawsuit", "risks", "dangers", "complaints"],
    "buying": ["가격", "보조금", "추천", "순위", "비교", "중고", "구매", "할인", "후기", "리뷰", "충전", "렌트",
               "price", "prices", "cost", "best", "vs", "review", "reviews", "buy", "cheap", "deals",
               "subsidy", "used", "charging", "rent"],
    "investing": ["관련주", "대장주", "주도주", "주가", "주식", "종목", "etf", "수혜주", "테마주", "투자",
                  "밸류체인", "stock", "stocks", "invest", "investments", "investors", "funding",
                  "shares", "price"],
    "definition": ["뜻", "란", "이란", "개념", "의미", "정의", "뭐야", "특징", "종류", "영어로",
                   "나무위키", "meaning", "what is", "definition", "explained", "overview", "wiki",
                   "que es", "là gì", "kya hai"],
    "learning": ["공부", "교육", "강의", "논문", "책", "자격증", "부트캠프", "대학원", "연구실", "랩실",
                 "코딩", "학습", "트레이닝", "course", "paper", "papers", "book", "books", "learn",
                 "learning", "tutorial", "bootcamp", "certification", "research", "journal", "pdf",
                 "github", "open source", "projects", "kit"],
    "jobs": ["채용", "취업", "연봉", "직무", "신입", "jobs", "careers", "salary", "hiring", "engineer",
             "roles", "fellowship"],
    "events": ["컨퍼런스", "대회", "챌린지", "포럼", "세미나", "해커톤", "박람회", "conference", "summit",
               "hackathon", "expo", "meetup", "events"],
    "policy": ["특별법", "전략", "정책", "얼라이언스", "협회", "규제", "패권", "governance", "regulation",
               "policy"],
    "companies": ["기업", "회사", "스타트업", "업체", "현대차", "삼성", "엔비디아", "companies", "company",
                  "startups", "startup", "key players", "leaders", "nvidia", "google", "openai",
                  "anthropic", "intel", "amd", "qualcomm", "aws", "tesla", "hitachi", "fujitsu", "fanuc"],
    "industries": ["제조", "물류", "방산", "자율주행", "항만", "의료", "사례", "산업", "분야", "manufacturing",
                   "healthcare", "logistics", "applications", "in healthcare", "for robotics"],
    "technology": ["기술", "모델", "데이터", "월드모델", "반도체", "메모리", "액추에이터", "플랫폼", "풀스택",
                   "시스템", "로보틱스", "휴머노이드", "로봇", "드론", "vla", "models", "model", "dataset",
                   "data", "world models", "reinforcement learning", "framework", "hardware", "platform",
                   "os", "operating system", "benchmarks", "robotics", "robot", "robots", "humanoid",
                   "simulation", "omniverse", "cosmos", "embodied ai"],
    "outlook": ["전망", "미래", "트렌드", "동향", "시장", "규모", "보고서", "future", "outlook", "market",
                "trends", "forecast", "boom", "hype", "growth", "report", "next frontier"],
    "news": ["뉴스", "디시", "news", "newsletter", "blog", "podcast", "reddit", "linkedin"],
}


def classify_intent(phrase, topic):
    rest = phrase.lower().replace(topic.lower(), " ").strip()
    words = set(re.split(r"\s+", rest))
    for intent, keys in INTENT_WORDS.items():
        for key in keys:
            if " " in key or not key.isascii():
                if key in rest:
                    return intent
            elif key in words:
                return intent
    return "other"


# What each intent means, so Jev knows what it is choosing between.
INTENT_DESCRIPTIONS = {
    "problems": "problems, risks, recalls, accidents, controversy, downsides",
    "buying": "buying or using it: prices, reviews, comparisons, recommendations, subsidies, charging",
    "investing": "stocks, ETFs, funds, investment opportunities",
    "definition": "what it is: meaning, definition, examples, types",
    "learning": "studying it: courses, papers, books, research, tutorials, projects",
    "jobs": "jobs, careers, salaries, hiring",
    "events": "conferences, competitions, expos, hackathons, forums",
    "policy": "government policy, laws, regulation, national strategy, alliances",
    "companies": "specific companies, brands, startups, key players",
    "industries": "use in an industry or field: manufacturing, healthcare, logistics, cases",
    "technology": "how it works: technology, models, hardware, data, platforms",
    "outlook": "the future: outlook, market size, trends, forecasts, reports",
    "news": "the latest news, blogs, forums, communities",
    "other": "none of the above",
}


def classify_with_jev(phrases, topic):
    """Jev picks one intent per phrase, with a probability. Returns {phrase: intent}."""
    state = f"Search phrases people typed into Google about the topic: {topic}"
    questions = {
        f"p{n}": {
            "type": "choice",
            "instructions": f'What does someone who searches "{phrase}" want?',
            "criteria": INTENT_DESCRIPTIONS,
        }
        for n, phrase in enumerate(phrases)
    }
    answers = jev_api.ask(state, questions)
    return {phrase: answers[f"p{n}"]["choice"] for n, phrase in enumerate(phrases)
            if answers.get(f"p{n}", {}).get("choice") in INTENT_DESCRIPTIONS}


def classify_with_model(phrases, topic):
    """Sort phrases the word lists missed into the same fixed intents, in one model call.

    The model only picks a label from INTENT_WORDS for each phrase; it adds no facts.
    Returns {phrase: intent}; on any failure, an empty dict (phrases stay "other").
    """
    if not phrases:
        return {}
    labels = list(INTENT_WORDS) + ["other"]
    numbered = "\n".join(f"{n}. {p}" for n, p in enumerate(phrases))
    messages = [
        {"role": "system", "content": (
            "Classify what each search phrase's searcher wants. Pick exactly one label per phrase from: "
            + ", ".join(labels) + ". Use other only if none fits. "
            'Reply with JSON only: {"labels": {"0": "buying", "1": "technology"}}')},
        {"role": "user", "content": f"Topic: {topic}\n\nSearch phrases:\n{numbered}"},
    ]
    try:
        answer = parse_json_reply(request_model(messages).get("content"))["labels"]
    except (ModelRequestError, ValueError, KeyError):
        return {}
    return {phrases[int(n)]: label for n, label in answer.items()
            if str(n).isdigit() and int(n) < len(phrases) and label in labels}


def search_intent(related, topic, use_model=True):
    """Share of autocomplete phrases per intent, weighted by how often each was suggested.

    Word lists first (exact and explainable), then the model for what they miss.
    Returns (how the phrases were classified, list of intents with shares).
    """
    by_rule = {item["phrase"]: classify_intent(item["phrase"], topic) for item in related}
    leftovers = [p for p, intent in by_rule.items() if intent == "other"][:150]
    by_model, method = {}, "word lists only"
    if use_model and leftovers and jev_api.available():
        try:
            by_model = classify_with_jev(leftovers, topic)
            method = "word lists, then Jev for phrases they missed"
        except jev_api.JevError:
            by_model = {}
    if use_model and leftovers and not by_model:
        by_model = classify_with_model(leftovers, topic)
        method = "word lists, then the text model for phrases they missed"

    totals, examples = Counter(), {}
    for item in related:
        intent = by_model.get(item["phrase"], by_rule[item["phrase"]])
        totals[intent] += item["times_suggested"]
        examples.setdefault(intent, []).append(item["phrase"])
    all_count = sum(totals.values()) or 1
    return method, [
        {
            "intent": intent,
            "share": round(n / all_count, 2),
            "examples": examples[intent][:5],
        }
        for intent, n in totals.most_common()
    ]


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


def news_drivers(news, topic, top=12):
    """Words that are much more common in today's headlines than in earlier ones."""
    topic_words = {w.lower() for w in re.split(r"\s+", topic)} | {topic.lower().replace(" ", "")}
    today = datetime.now().astimezone().date()
    today_count, before_count = Counter(), Counter()
    today_n = before_n = 0
    for a in news:
        words = headline_words(a["title"], topic_words)
        if datetime.fromisoformat(a["published"]).astimezone().date() == today:
            today_count.update(words)
            today_n += 1
        else:
            before_count.update(words)
            before_n += 1

    drivers = []
    for word, n in today_count.most_common():
        if n < 3:
            break
        share_today = n / today_n
        share_before = before_count[word] / before_n if before_n else 0
        drivers.append(
            {
                "word": word,
                "headlines_today": n,
                "share_today": round(share_today, 2),
                "share_before": round(share_before, 3),
                "lift": round(share_today / share_before, 1) if share_before else None,  # None = new today
            }
        )
    # New-today and big-lift words first.
    drivers.sort(key=lambda d: (d["lift"] is not None, -(d["lift"] or 0), -d["headlines_today"]))
    return drivers[:top], today_n


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
    evidence["D1"] = (
        f"News articles per day for the last {len(m['per_day'])} days, today first: {m['per_day']}. "
        f"Today {m['today']} vs previous average {m['previous_daily_average']} -> momentum {m['momentum']}."
    )
    evidence["D2"] = "Search intent from Google autocomplete (share of suggestions): " + "; ".join(
        f"{i['intent']} {int(i['share'] * 100)}% (e.g. {', '.join(i['examples'][:3])})" for i in facts["intent"]
    )
    evidence["D3"] = "Words much more common in today's headlines than earlier (lift = times more common, new = absent before): " + "; ".join(
        f"{d['word']} in {d['headlines_today']} headlines ({'new' if d['lift'] is None else str(d['lift']) + 'x'})"
        for d in facts["drivers"]
    )
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


def parse_json_reply(text):
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        raise ValueError("the model did not reply with JSON")
    return json.loads(match.group(0))


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


def explain(topic, evidence, language):
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

    kept, dropped, relevance_method = relevant_news(data["news"], topic)
    data = {**data, "news": kept}
    drivers, today_n = news_drivers(data["news"], topic)
    intent_method, intents = search_intent(data["related_searches"], topic)
    facts = {
        "coverage": data["news_momentum"],
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
        explanation = explain(topic, evidence, "Korean" if lang == "ko" else "English")
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
    print("  news drivers today: " + ", ".join(
        f"{d['word']}({d['headlines_today']}{', new' if d['lift'] is None else ''})" for d in f["drivers"]))
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
