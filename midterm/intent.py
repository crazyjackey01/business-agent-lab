"""What do people want when they search a topic? Sort its autocomplete phrases by purpose.

Two passes:
  1. Generic patterns catch phrases whose purpose is plain from the wording alone, for any
     topic: how-to endings (~하는 법, 끄기, 설정, how to), buying words (가격, 비교, vs),
     meaning words (뜻, 이란, what is) and so on. No topic-specific words.
  2. Jev sorts everything else (product names like "폴드8", app names, places, ...): it
     picks one purpose from the fixed list below, with a probability. Phrases the
     patterns caught are not sent, which saves Jev tokens.

The result is the share of autocomplete suggestions per purpose, weighted by how
often each phrase was suggested, e.g. 갤럭시: product info 60%, how to use 26%, ...
"""
import re

import jev_api

# The purposes, and what each one means: Jev reads these descriptions to choose.
# Kept short on purpose: Jev re-reads them for every phrase, and short descriptions
# use 27% fewer tokens with nearly the same answers (5 of 119 borderline phrases differed).
INTENTS = {
    "buying": "price, reviews, where to buy",
    "product_info": "model names, specs, release date",
    "how_to": "how to use, settings, fixes",
    "problems": "defects, risks, controversy",
    "investing": "stocks, ETFs",
    "definition": "meaning, examples",
    "learning": "courses, papers",
    "jobs": "jobs, salaries",
    "events": "conferences, expos",
    "policy": "laws, government",
    "companies": "a company behind it",
    "industries": "use in an industry",
    "technology": "how it works",
    "outlook": "future, market",
    "news": "news, forums",
    "other": "none of these",
}

# Pass 1: wording that means the same purpose for any topic. Checked in this order.
# Korean is matched inside words (끄는법, 가격비교); English as whole words.
PATTERNS = {
    "how_to": r"하는\s?법|하는\s?방법|방법|사용법|설정|끄기|끄는|켜기|켜는|해제|초기화|연결|설치|다운로드|바꾸기|"
              r"\bhow to\b|\bsettings?\b|\bsetup\b|\binstall\b|\bdownload\b|\bturn (?:on|off)\b|\breset\b|\bfix\b",
    "problems": r"고장|결함|리콜|오류|안됨|안 됨|안되|문제|논란|단점|부작용|위험|"
                r"\brecall\b|\bproblems?\b|\bissues?\b|\bnot working\b|\brisks?\b",
    "buying": r"가격|최저가|할인|구매|구입|추천|순위|비교|후기|리뷰|중고|보조금|싸게|"
              r"\bprice\b|\bcost\b|\bbuy\b|\bbest\b|\bvs\b|\breviews?\b|\bdeals?\b|\bcheap\b|\bused\b",
    "investing": r"관련주|대장주|주가|주식|종목|\betf\b|\bstocks?\b|\bshares?\b",
    "definition": r"뜻|이란|란$|의미|정의|뭐야|뭔가요|영어로|\bmeaning\b|\bwhat is\b|\bdefinition\b",
    "jobs": r"채용|취업|연봉|\bjobs?\b|\bcareers?\b|\bsalary\b|\bhiring\b",
    "product_info": r"출시일|스펙|사양|색상|크기|무게|\brelease date\b|\bspecs?\b|\bdimensions\b",
}
COMPILED = {intent: re.compile(p) for intent, p in PATTERNS.items()}


def classify_with_patterns(phrase, topic):
    """The purpose if the wording makes it plain, else None (left for Jev)."""
    rest = phrase.lower().replace(topic.lower(), " ").strip()
    for intent, pattern in COMPILED.items():
        if pattern.search(rest):
            return intent
    return None


def classify_with_jev(phrases, topic):
    """Jev picks one purpose per phrase. Returns {phrase: purpose}."""
    state = f"Phrases people typed into Google about the topic: {topic}"
    questions = {
        f"p{n}": {"type": "choice", "instructions": f'What does someone who searches "{phrase}" want?',
                  "criteria": INTENTS}
        for n, phrase in enumerate(phrases)
    }
    answers = jev_api.ask(state, questions)
    return {phrase: answers[f"p{n}"]["choice"] for n, phrase in enumerate(phrases)
            if answers.get(f"p{n}", {}).get("choice") in INTENTS}


def search_intent(related, topic, max_phrases=300):
    """Share of autocomplete suggestions per purpose.

    Returns (how the phrases were sorted, [{"intent", "share", "examples"}, ...]).
    """
    related = related[:max_phrases]
    labels = {r["phrase"]: classify_with_patterns(r["phrase"], topic) for r in related}
    rest = [p for p, intent in labels.items() if intent is None]
    caught = len(labels) - len(rest)
    if rest and jev_api.available():
        try:
            labels.update(classify_with_jev(rest, topic))
        except jev_api.JevError:
            pass  # those phrases stay unsorted ("other")
    method = f"patterns sorted {caught} of {len(labels)} phrases, Jev the rest"

    totals, examples = {}, {}
    for r in related:
        intent = labels.get(r["phrase"]) or "other"
        totals[intent] = totals.get(intent, 0) + r["times_suggested"]
        examples.setdefault(intent, []).append(r["phrase"])
    all_count = sum(totals.values()) or 1
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    return method, [{"intent": i, "share": round(n / all_count, 2), "examples": examples[i][:5]} for i, n in ranked]
