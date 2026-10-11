"""What do people want when they search a topic? Sort its autocomplete phrases by purpose.

Jev sorts every phrase: it picks one purpose from the fixed list below, with a
probability, and cannot invent a label of its own. About $0.002 per search.

The result is the share of autocomplete suggestions per purpose, weighted by how
often each phrase was suggested, e.g. 갤럭시: product info 60%, how to use 26%, ...
"""
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
    labels = {}
    if related and jev_api.available():
        try:
            labels = classify_with_jev([r["phrase"] for r in related], topic)
        except jev_api.JevError:
            pass  # phrases stay unsorted ("other")
    method = "Jev, every phrase"

    totals, examples = {}, {}
    for r in related:
        intent = labels.get(r["phrase"]) or "other"
        totals[intent] = totals.get(intent, 0) + r["times_suggested"]
        examples.setdefault(intent, []).append(r["phrase"])
    all_count = sum(totals.values()) or 1
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    return method, [{"intent": i, "share": round(n / all_count, 2), "examples": examples[i][:5]} for i, n in ranked]
