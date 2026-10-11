// What do people want when they search a topic? (JavaScript port of intent.py)
// Pass 1: generic patterns catch phrases whose purpose is plain from the wording, for any
// topic (~하는 법, 가격, 뜻, how to, vs ...). Pass 2: Jev sorts the rest, one fixed label each.
// Phrases the patterns caught are not sent to Jev, which saves tokens.
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

// Korean is matched inside words (끄는법, 가격비교); English as whole words.
const PATTERNS = {
  how_to: /하는\s?법|하는\s?방법|방법|사용법|설정|끄기|끄는|켜기|켜는|해제|초기화|연결|설치|다운로드|바꾸기|\bhow to\b|\bsettings?\b|\bsetup\b|\binstall\b|\bdownload\b|\bturn (?:on|off)\b|\breset\b|\bfix\b/,
  problems: /고장|결함|리콜|오류|안됨|안 됨|안되|문제|논란|단점|부작용|위험|\brecall\b|\bproblems?\b|\bissues?\b|\bnot working\b|\brisks?\b/,
  buying: /가격|최저가|할인|구매|구입|추천|순위|비교|후기|리뷰|중고|보조금|싸게|\bprice\b|\bcost\b|\bbuy\b|\bbest\b|\bvs\b|\breviews?\b|\bdeals?\b|\bcheap\b|\bused\b/,
  investing: /관련주|대장주|주가|주식|종목|\betf\b|\bstocks?\b|\bshares?\b/,
  definition: /뜻|이란|란$|의미|정의|뭐야|뭔가요|영어로|\bmeaning\b|\bwhat is\b|\bdefinition\b/,
  jobs: /채용|취업|연봉|\bjobs?\b|\bcareers?\b|\bsalary\b|\bhiring\b/,
  product_info: /출시일|스펙|사양|색상|크기|무게|\brelease date\b|\bspecs?\b|\bdimensions\b/,
};

function classifyWithPatterns(phrase, topic) {
  const rest = phrase.toLowerCase().replace(topic.toLowerCase(), " ").trim();
  for (const [intent, pattern] of Object.entries(PATTERNS)) if (pattern.test(rest)) return intent;
  return null;
}

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
  const labels = Object.fromEntries(related.map(r => [r.phrase, classifyWithPatterns(r.phrase, topic)]));
  const rest = Object.keys(labels).filter(p => labels[p] === null);
  const caught = related.length - rest.length;
  if (rest.length && env.OPENCODE_API_KEY) {
    Object.assign(labels, await classifyWithJev(env, rest, topic).catch(() => ({}))); // failures stay "other"
  }
  const totals = new Map(), examples = {};
  for (const r of related) {
    const intent = labels[r.phrase] || "other";
    totals.set(intent, (totals.get(intent) || 0) + r.times_suggested);
    (examples[intent] ||= []).push(r.phrase);
  }
  const all = [...totals.values()].reduce((a, b) => a + b, 0) || 1;
  return [`patterns sorted ${caught} of ${related.length} phrases, Jev the rest`,
    [...totals].sort((a, b) => b[1] - a[1]).map(([intent, n]) => ({
      intent, share: Math.round((n / all) * 100) / 100, examples: examples[intent].slice(0, 5),
    }))];
}
