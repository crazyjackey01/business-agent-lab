// What do people want when they search a topic? (JavaScript port of intent.py)
// Jev sorts every phrase into one fixed purpose, with a probability.
import { askJev } from "./models.js";

// Kept short on purpose: Jev re-reads them for every phrase.
const INTENTS = {
  buying: "price, reviews, where to buy",
  product_info: "model names, specs, release date",
  how_to: "how to use, settings, fixes",
  problems: "defects, risks, controversy",
  investing: "stocks, ETFs",
  definition: "meaning, examples",
  learning: "courses, papers",
  jobs: "jobs, salaries",
  events: "conferences, expos",
  policy: "laws, government",
  companies: "a company behind it",
  industries: "use in an industry",
  technology: "how it works",
  outlook: "future, market",
  news: "news, forums",
  other: "none of these",
};

async function classifyWithJev(env, phrases, topic) {
  const questions = Object.fromEntries(phrases.map((phrase, n) => [`p${n}`, {
    type: "choice", instructions: `What does someone who searches "${phrase}" want?`, criteria: INTENTS,
  }]));
  const answers = await askJev(env, `Phrases people typed into Google about the topic: ${topic}`, questions, "intent");
  const out = {};
  phrases.forEach((phrase, n) => { if (answers[`p${n}`]?.choice in INTENTS) out[phrase] = answers[`p${n}`].choice; });
  return out;
}

// Returns [how the phrases were sorted, [{intent, share, examples}]].
export async function searchIntent(env, related, topic, maxPhrases = 300) {
  related = related.slice(0, maxPhrases);
  const labels = related.length && env.OPENCODE_API_KEY
    ? await classifyWithJev(env, related.map(r => r.phrase), topic).catch(() => ({})) // failures stay "other"
    : {};
  const totals = new Map(), examples = {};
  for (const r of related) {
    const intent = labels[r.phrase] || "other";
    totals.set(intent, (totals.get(intent) || 0) + r.times_suggested);
    (examples[intent] ||= []).push(r.phrase);
  }
  const all = [...totals.values()].reduce((a, b) => a + b, 0) || 1;
  return ["Jev, every phrase", [...totals].sort((a, b) => b[1] - a[1]).map(([intent, n]) => ({
    intent, share: Math.round((n / all) * 100) / 100, examples: examples[intent].slice(0, 5),
  }))];
}
