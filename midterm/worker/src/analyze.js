// Fact-based analysis: the JavaScript port of analyze_topic.py.
//   1. measured facts (plain code): search intent, news drivers, dated events, coverage
//   2. explanation (language model): only from numbered evidence, every claim cites ids
//   3. check: each claim is rated against its cited evidence, by Jev (a decision model that
//      can only pick supported / partly / unsupported) when OPENCODE_API_KEY is set,
//      otherwise by a second text-model call
import { dayIn } from "./collect.js";

const OPENROUTER = "https://openrouter.ai/api/v1/chat/completions";
// Writes the analysis. Override with the OPENROUTER_MODEL variable.
const DEFAULT_MODEL = "anthropic/claude-sonnet-5.5";
const JEV_ENDPOINT = "https://opencode.ai/zen/v1/systemone";
const JEV_MAX_QUESTIONS = 200; // one request per step when possible: the free tier allows few requests per minute

// Jev writes no text: it answers questions whose possible answers we fix in advance.
async function askJev(env, state, questions) {
  const ids = Object.keys(questions), answers = {};
  // One batch at a time, and wait on 429: the free tier rejects bursts.
  for (let i = 0; i < ids.length; i += JEV_MAX_QUESTIONS) {
    const batch = ids.slice(i, i + JEV_MAX_QUESTIONS);
    for (let attempt = 0; ; attempt++) {
      const response = await fetch(JEV_ENDPOINT, {
        method: "POST",
        headers: { Authorization: `Bearer ${env.OPENCODE_API_KEY}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          model: env.JEV_MODEL || "jev-1.13-free", state,
          questions: Object.fromEntries(batch.map(id => [id, questions[id]])),
        }),
      });
      if (response.status === 429 && attempt < 3) {
        await new Promise(r => setTimeout(r, 1500 * 2 ** attempt));
        continue;
      }
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.answers) throw new Error(`Jev HTTP ${response.status}: ${data.error?.message || "no answers"}`);
      Object.assign(answers, data.answers);
      break;
    }
  }
  return answers;
}

const isAscii = s => /^[\x00-\x7f]*$/.test(s);

// Search intent ----------------------------------------------------------------

// Checked in this order; the first intent with a matching word wins.
// Korean words match inside longer words ("로봇팔" counts as 로봇).
export const INTENT_WORDS = {
  problems: ["화재", "리콜", "고장", "결함", "사고", "문제", "논란", "부작용", "위험", "단점", "recall",
    "problems", "issues", "fire", "lawsuit", "risks", "dangers", "complaints"],
  buying: ["가격", "보조금", "추천", "순위", "비교", "중고", "구매", "할인", "후기", "리뷰", "충전", "렌트",
    "price", "prices", "cost", "best", "vs", "review", "reviews", "buy", "cheap", "deals",
    "subsidy", "used", "charging", "rent"],
  investing: ["관련주", "대장주", "주도주", "주가", "주식", "종목", "etf", "수혜주", "테마주", "투자",
    "밸류체인", "stock", "stocks", "invest", "investments", "investors", "funding", "shares", "price"],
  definition: ["뜻", "란", "이란", "개념", "의미", "정의", "뭐야", "특징", "종류", "영어로", "나무위키",
    "meaning", "what is", "definition", "explained", "overview", "wiki", "que es", "là gì", "kya hai"],
  learning: ["공부", "교육", "강의", "논문", "책", "자격증", "부트캠프", "대학원", "연구실", "랩실", "코딩",
    "학습", "트레이닝", "course", "paper", "papers", "book", "books", "learn", "learning", "tutorial",
    "bootcamp", "certification", "research", "journal", "pdf", "github", "open source", "projects", "kit"],
  jobs: ["채용", "취업", "연봉", "직무", "신입", "jobs", "careers", "salary", "hiring", "engineer", "roles",
    "fellowship"],
  events: ["컨퍼런스", "대회", "챌린지", "포럼", "세미나", "해커톤", "박람회", "conference", "summit",
    "hackathon", "expo", "meetup", "events"],
  policy: ["특별법", "전략", "정책", "얼라이언스", "협회", "규제", "패권", "governance", "regulation", "policy"],
  companies: ["기업", "회사", "스타트업", "업체", "현대차", "삼성", "엔비디아", "companies", "company",
    "startups", "startup", "key players", "leaders", "nvidia", "google", "openai", "anthropic", "intel",
    "amd", "qualcomm", "aws", "tesla", "hitachi", "fujitsu", "fanuc"],
  industries: ["제조", "물류", "방산", "자율주행", "항만", "의료", "사례", "산업", "분야", "manufacturing",
    "healthcare", "logistics", "applications", "in healthcare", "for robotics"],
  technology: ["기술", "모델", "데이터", "월드모델", "반도체", "메모리", "액추에이터", "플랫폼", "풀스택",
    "시스템", "로보틱스", "휴머노이드", "로봇", "드론", "vla", "models", "model", "dataset", "data",
    "world models", "reinforcement learning", "framework", "hardware", "platform", "os",
    "operating system", "benchmarks", "robotics", "robot", "robots", "humanoid", "simulation",
    "omniverse", "cosmos", "embodied ai"],
  outlook: ["전망", "미래", "트렌드", "동향", "시장", "규모", "보고서", "future", "outlook", "market",
    "trends", "forecast", "boom", "hype", "growth", "report", "next frontier"],
  news: ["뉴스", "디시", "news", "newsletter", "blog", "podcast", "reddit", "linkedin"],
};

// What each intent means, so Jev knows what it is choosing between.
const INTENT_DESCRIPTIONS = {
  problems: "problems, risks, recalls, accidents, controversy, downsides",
  buying: "buying or using it: prices, reviews, comparisons, recommendations, subsidies, charging",
  investing: "stocks, ETFs, funds, investment opportunities",
  definition: "what it is: meaning, definition, examples, types",
  learning: "studying it: courses, papers, books, research, tutorials, projects",
  jobs: "jobs, careers, salaries, hiring",
  events: "conferences, competitions, expos, hackathons, forums",
  policy: "government policy, laws, regulation, national strategy, alliances",
  companies: "specific companies, brands, startups, key players",
  industries: "use in an industry or field: manufacturing, healthcare, logistics, cases",
  technology: "how it works: technology, models, hardware, data, platforms",
  outlook: "the future: outlook, market size, trends, forecasts, reports",
  news: "the latest news, blogs, forums, communities",
  other: "none of the above",
};

async function classifyWithJev(env, phrases, topic) {
  const questions = Object.fromEntries(phrases.map((phrase, n) => [`p${n}`, {
    type: "choice", instructions: `What does someone who searches "${phrase}" want?`, criteria: INTENT_DESCRIPTIONS,
  }]));
  const answers = await askJev(env, `Search phrases people typed into Google about the topic: ${topic}`, questions);
  const out = {};
  phrases.forEach((phrase, n) => {
    const choice = answers[`p${n}`]?.choice;
    if (choice in INTENT_DESCRIPTIONS) out[phrase] = choice;
  });
  return out;
}

export function classifyIntent(phrase, topic) {
  const rest = phrase.toLowerCase().replace(topic.toLowerCase(), " ").trim();
  const words = new Set(rest.split(/\s+/));
  for (const [intent, keys] of Object.entries(INTENT_WORDS)) {
    for (const key of keys) {
      if (key.includes(" ") || !isAscii(key) ? rest.includes(key) : words.has(key)) return intent;
    }
  }
  return "other";
}

// Sort phrases the word lists missed into the same fixed intents, in one model call.
// The model only picks a label for each phrase; it adds no facts.
async function classifyWithModel(env, phrases, topic) {
  if (!phrases.length) return {};
  const labels = [...Object.keys(INTENT_WORDS), "other"];
  const numbered = phrases.map((p, n) => `${n}. ${p}`).join("\n");
  try {
    const reply = parseJsonReply(await requestModel(env, [
      { role: "system", content: "Classify what each search phrase's searcher wants. Pick exactly one label per phrase from: "
          + labels.join(", ") + '. Use other only if none fits. Reply with JSON only: {"labels": {"0": "buying", "1": "technology"}}' },
      { role: "user", content: `Topic: ${topic}\n\nSearch phrases:\n${numbered}` },
    ]));
    const out = {};
    for (const [n, label] of Object.entries(reply.labels || {})) {
      if (/^\d+$/.test(n) && +n < phrases.length && labels.includes(label)) out[phrases[+n]] = label;
    }
    return out;
  } catch {
    return {}; // phrases stay "other"
  }
}

export async function searchIntent(env, related, topic) {
  const byRule = Object.fromEntries(related.map(r => [r.phrase, classifyIntent(r.phrase, topic)]));
  const leftovers = Object.keys(byRule).filter(p => byRule[p] === "other").slice(0, 150);
  let byModel = {};
  // Jev's free tier allows few requests from Cloudflare, so it is saved for the claim check
  // unless JEV_FOR_INTENT is set.
  if (leftovers.length && env.OPENCODE_API_KEY && env.JEV_FOR_INTENT) {
    byModel = await classifyWithJev(env, leftovers, topic).catch(() => ({}));
  }
  if (leftovers.length && !Object.keys(byModel).length) byModel = await classifyWithModel(env, leftovers, topic);

  const totals = new Map(), examples = {};
  for (const r of related) {
    const intent = byModel[r.phrase] || byRule[r.phrase];
    totals.set(intent, (totals.get(intent) || 0) + r.times_suggested);
    (examples[intent] ||= []).push(r.phrase);
  }
  const all = [...totals.values()].reduce((a, b) => a + b, 0) || 1;
  return [...totals].sort((a, b) => b[1] - a[1]).map(([intent, n]) => ({
    intent, share: Math.round((n / all) * 100) / 100, examples: examples[intent].slice(0, 5),
  }));
}

// News drivers -----------------------------------------------------------------

// Korean particles that stick to the end of words ("KAIST가", "정의선의").
const PARTICLES = ["에서", "으로", "까지", "부터", "에게", "은", "는", "이", "가", "을", "를", "의",
  "에", "와", "과", "도", "로", "만"];
const STOPWORDS = new Set(["the", "and", "for", "with", "from", "into", "its", "how", "why", "what", "new",
  "are", "will", "has", "this", "that", "it", "is", "to", "of", "in", "on", "as", "at", "by", "an", "now",
  "be", "can", "after", "over", "more", "your", "you", "says", "종합", "속보", "단독", "포토", "영상", "기자"]);

function headlineWords(title, topicWords) {
  const words = new Set();
  for (let raw of title.toLowerCase().match(/[\p{L}\p{N}_·]+/gu) || []) {
    for (const p of PARTICLES) {
      if (raw.length > p.length + 1 && raw.endsWith(p) && !isAscii(raw)) { raw = raw.slice(0, -p.length); break; }
    }
    if (raw.length < 2 || /^\d+$/.test(raw) || STOPWORDS.has(raw) || topicWords.has(raw)) continue;
    words.add(raw);
  }
  return words;
}

export function newsDrivers(news, topic, geo, top = 12) {
  const topicWords = new Set([...topic.toLowerCase().split(/\s+/), topic.toLowerCase().replace(/ /g, "")]);
  const today = dayIn(new Date(), geo);
  const todayCount = new Map(), beforeCount = new Map();
  let todayN = 0, beforeN = 0;
  for (const a of news) {
    const isToday = dayIn(new Date(a.published), geo) === today;
    const counts = isToday ? todayCount : beforeCount;
    isToday ? todayN++ : beforeN++;
    for (const w of headlineWords(a.title, topicWords)) counts.set(w, (counts.get(w) || 0) + 1);
  }
  const drivers = [...todayCount].filter(([, n]) => n >= 3).map(([word, n]) => {
    const shareToday = n / todayN;
    const shareBefore = beforeN ? (beforeCount.get(word) || 0) / beforeN : 0;
    return {
      word, headlines_today: n,
      share_today: Math.round(shareToday * 100) / 100,
      share_before: Math.round(shareBefore * 1000) / 1000,
      lift: shareBefore ? Math.round((shareToday / shareBefore) * 10) / 10 : null, // null = new today
    };
  });
  // New-today and big-lift words first.
  drivers.sort((a, b) => (a.lift !== null) - (b.lift !== null) || (b.lift || 0) - (a.lift || 0)
    || b.headlines_today - a.headlines_today);
  return drivers.slice(0, top);
}

// Scheduled events -------------------------------------------------------------

const DATE_PATTERNS = [/\d{1,2}월\s?\d{1,2}일/g, /\d{1,2}일/g, /\d{1,2}\/\d{1,2}/g, /다음\s?(주|달)/g, /내년/g,
  /하반기/g, /(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? \d{1,2}/g, /next (week|month|year)/g,
  /\b20\d\d\b/g];
const EVENT_WORDS = ["개최", "출시", "공개", "발표", "선포", "착공", "예정", "앞두고", "열린다", "박람회", "컨퍼런스",
  "launch", "unveil", "to open", "will", "summit", "conference", "expo", "plans", "set to"];

export function scheduledEvents(news, limit = 15) {
  const events = [];
  for (const a of news) {
    // Headline plus summary: Gemini's one-line summaries often carry the dates.
    const title = `${a.title} ${a.summary || ""}`.toLowerCase();
    const dates = DATE_PATTERNS.flatMap(p => title.match(p) || []);
    const words = EVENT_WORDS.filter(w => title.includes(w));
    if (dates.length && words.length) events.push({ ...a, dates_mentioned: dates, event_words: words });
  }
  return events.slice(0, limit);
}

// Model calls --------------------------------------------------------------------

async function requestModel(env, messages) {
  const body = JSON.stringify({ model: env.OPENROUTER_MODEL || DEFAULT_MODEL, messages });
  for (let attempt = 0; attempt < 3; attempt++) {
    const response = await fetch(OPENROUTER, {
      method: "POST",
      headers: { Authorization: `Bearer ${env.OPENROUTER_API_KEY}`, "Content-Type": "application/json" },
      body,
    });
    if (response.status === 429 && attempt < 2) {
      await new Promise(r => setTimeout(r, 2000 * 2 ** attempt)); // rate limited: wait, try again
      continue;
    }
    const data = await response.json().catch(() => ({ error: { message: "not JSON" } }));
    if (!response.ok || data.error) throw new Error(`model HTTP ${response.status}: ${data.error?.message || "no message"}`);
    return data.choices[0].message.content;
  }
}

function parseJsonReply(text) {
  const match = (text || "").match(/\{[\s\S]*\}/);
  if (!match) throw new Error("the model did not reply with JSON");
  return JSON.parse(match[0]);
}

// Explanation ----------------------------------------------------------------------

const SYSTEM_PROMPT = `You are a careful trend analyst. You explain why people are searching for a topic,
what is happening, and what is likely to happen next.

Rules:
- Use ONLY the evidence given. Each evidence item has an id like [D1] (measured data) or [S4] (a news headline).
- Every claim must list the ids that support it in "cites". A claim with no support must not be written.
- Headlines tell you what was reported, not the full story. Say "reported" when that matters.
- "outlook" items are forecasts. Base each one on a scheduled event or a measured trend in the evidence,
  give a confidence (low / medium / high), and say in "basis" which evidence it extends.
  Do not forecast prices or anything the evidence does not touch.
- Write every claim, basis and caveat in {language}.

Reply with JSON only, in this shape:
{
  "why_people_search": [{"claim": "...", "cites": ["D1", "S3"]}],
  "what_is_happening": [{"claim": "...", "cites": ["S1", "S2"]}],
  "outlook": [{"claim": "...", "basis": "...", "confidence": "medium", "cites": ["S5", "D2"]}],
  "caveats": ["..."]
}`;

const CHECK_PROMPT = `You check claims against evidence. For each claim you get the exact evidence it cites.
Rate it:
- "supported": the cited evidence states it, or it follows directly.
- "partly": the core is in the evidence but the claim adds something the evidence does not say
  (an exaggeration, a cause, a trend over time that was measured only once).
- "unsupported": the cited evidence does not say it, or is about something else.
For forecasts ("outlook"), judge whether the basis is really in the evidence, not whether the future is certain.
Reply with JSON only: {"checks": [{"id": 0, "rating": "supported", "reason": "..."}]}
Write each reason in {language}, one short sentence.`;

const SECTIONS = ["why_people_search", "what_is_happening", "outlook"];

// Number every fact and headline so the model can cite them.
export function buildEvidence(facts, news, maxHeadlines = 40) {
  const evidence = {}, links = {};
  const m = facts.coverage;
  // A blocked news source must not read as "no news was published".
  evidence.D1 = facts.news_unavailable
    ? "Daily news counts could NOT be measured this time (the news feed refused the request). The [S] articles below come from Google Search and are a sample, not a count. Say nothing about news volume or momentum."
    : `News articles per day for the last ${m.per_day.length} days, today first: [${m.per_day.join(", ")}]. `
    + `Today ${m.today} vs previous average ${m.previous_daily_average} -> momentum ${m.momentum}.`;
  evidence.D2 = "Search intent from Google autocomplete (share of suggestions): " + facts.intent.map(i =>
    `${i.intent} ${Math.round(i.share * 100)}% (e.g. ${i.examples.slice(0, 3).join(", ")})`).join("; ");
  evidence.D3 = "Words much more common in today's headlines than earlier (lift = times more common, new = absent before): "
    + facts.drivers.map(d => `${d.word} in ${d.headlines_today} headlines (${d.lift === null ? "new" : d.lift + "x"})`).join("; ");
  if (facts.trends_matches.length) {
    evidence.D4 = "Matching Google Trends searches right now: "
      + facts.trends_matches.map(t => `${t.term} (${t.traffic_text})`).join("; ");
  }
  // Headlines: scheduled-event ones first, then the newest, without duplicates.
  const seen = new Set(), chosen = [];
  for (const a of [...facts.events, ...news]) {
    if (!seen.has(a.url)) { seen.add(a.url); chosen.push(a); }
  }
  chosen.slice(0, maxHeadlines).forEach((a, i) => {
    evidence[`S${i + 1}`] = `${a.published.slice(0, 10)} | ${a.source} | ${a.title}` + (a.summary ? ` | ${a.summary}` : "");
    links[`S${i + 1}`] = a.url;
  });
  return [evidence, links];
}

function keepSupported(claims, evidence) {
  const kept = [];
  let dropped = 0;
  for (const c of claims || []) {
    const cites = (c.cites || []).map(x => String(x).replace(/[\[\] ]/g, ""));
    if (cites.length && cites.every(x => x in evidence)) kept.push({ ...c, cites });
    else dropped++;
  }
  return [kept, dropped];
}

const CHECK_LABELS = {
  supported: "The cited evidence states the claim, or it follows directly.",
  partly: "The core is in the evidence, but the claim adds something it does not say (an exaggeration, a cause, a trend measured only once).",
  unsupported: "The cited evidence does not say this, or is about something else.",
};
const UNCERTAIN_BELOW = 0.6; // Jev confidence under this is shown as uncertain

function claimText(n, section, c, evidence) {
  const cited = c.cites.map(x => `    [${x}] ${evidence[x]}`).join("\n");
  const claim = c.claim + (c.basis ? ` (basis: ${c.basis})` : "");
  return `Claim ${n} (${section}): ${claim}\n  Cited evidence:\n${cited}`;
}

async function ratingsFromJev(env, items, evidence) {
  const state = "Claims written by an analyst, each with the exact evidence it cites:\n\n"
    + items.map(([section, c], n) => claimText(n, section, c, evidence)).join("\n\n");
  const questions = Object.fromEntries(items.map((_, n) => [`c${n}`, {
    type: "choice",
    instructions: `Does the cited evidence support Claim ${n}? For a forecast, judge whether its basis is really in the evidence, not whether the future is certain.`,
    criteria: CHECK_LABELS,
  }]));
  const answers = await askJev(env, state, questions);
  const ratings = new Map();
  items.forEach((_, n) => {
    const a = answers[`c${n}`];
    if (a?.choice in CHECK_LABELS) {
      ratings.set(n, { rating: a.choice, confidence: a.confidence, probabilities: a.probabilities || {}, by: "jev", reason: "" });
    }
  });
  return ratings;
}

async function ratingsFromModel(env, items, evidence, language) {
  const checks = parseJsonReply(await requestModel(env, [
    { role: "system", content: CHECK_PROMPT.replace("{language}", language) },
    { role: "user", content: items.map(([section, c], n) => claimText(n, section, c, evidence)).join("\n\n") },
  ])).checks;
  return new Map(checks.filter(c => /^\d+$/.test(String(c.id))).map(c => [+c.id, { ...c, by: "model" }]));
}

async function checkClaims(env, result, evidence, language) {
  const items = SECTIONS.flatMap(section => result[section].map(c => [section, c]));
  if (!items.length) return 0;
  let ratings = null;
  if (env.OPENCODE_API_KEY) {
    try {
      ratings = await ratingsFromJev(env, items, evidence);
    } catch (error) {
      result.jev_error = String(error.message || error);
    }
  }
  if (!ratings || !ratings.size) {
    try {
      ratings = await ratingsFromModel(env, items, evidence, language);
    } catch (error) {
      result.check_error = String(error.message || error);
      return 0;
    }
  }
  result.checked_by = ratings.size ? [...ratings.values()][0].by : "none";

  let removed = 0;
  for (const section of SECTIONS) {
    result[section] = result[section].flatMap(c => {
      const n = items.findIndex(([, item]) => item === c);
      const check = ratings.get(n) || { rating: "unchecked", reason: "" };
      if (check.rating === "unsupported") { removed++; return []; }
      const confidence = check.confidence ?? null;
      return [{ ...c, check: check.rating, check_reason: check.reason || "", check_confidence: confidence,
        check_uncertain: confidence !== null && confidence < UNCERTAIN_BELOW }];
    });
  }
  return removed;
}

async function explain(env, topic, evidence, language) {
  const evidenceText = Object.entries(evidence).map(([k, v]) => `[${k}] ${v}`).join("\n");
  const reply = parseJsonReply(await requestModel(env, [
    { role: "system", content: SYSTEM_PROMPT.replace("{language}", language) },
    { role: "user", content: `Topic: ${topic}\n\nEvidence:\n${evidenceText}` },
  ]));
  const result = {};
  let dropped = 0;
  for (const section of SECTIONS) {
    const [kept, n] = keepSupported(reply[section], evidence);
    result[section] = kept;
    dropped += n;
  }
  result.caveats = reply.caveats || [];
  result.unsupported_claims_removed = dropped;
  result.failed_check_removed = await checkClaims(env, result, evidence, language);
  return result;
}

// Run --------------------------------------------------------------------------------

export async function analyze(env, data) {
  const facts = {
    coverage: data.news_momentum,
    news_unavailable: (data.source_errors || []).some(e => e.startsWith("news")),
    spam_removed: data.news_spam_removed || 0,
    intent: await searchIntent(env, data.related_searches, data.topic),
    intent_method: `word lists, then ${env.OPENCODE_API_KEY && env.JEV_FOR_INTENT ? "Jev" : "the text model"} for phrases they missed`,
    drivers: newsDrivers(data.news, data.topic, data.geo),
    events: scheduledEvents(data.news),
    trends_matches: data.google_trends_matches,
    history: [],
  };
  const [evidence, links] = buildEvidence(facts, data.news);
  let explanation;
  try {
    explanation = await explain(env, data.topic, evidence, data.lang === "ko" ? "Korean" : "English");
  } catch (error) {
    explanation = { error: String(error.message || error) };
  }
  return {
    topic: data.topic,
    geo: data.geo,
    source_collected_at: data.collected_at,
    source_errors: data.source_errors || [],
    news_source: data.news_source,
    google_search: data.google_search || null,
    writer_model: env.OPENROUTER_MODEL || DEFAULT_MODEL,
    analyzed_at: new Date().toISOString().slice(0, 19) + "+00:00",
    facts, evidence, evidence_links: links,
    related_searches: data.related_searches,
    explanation,
  };
}
