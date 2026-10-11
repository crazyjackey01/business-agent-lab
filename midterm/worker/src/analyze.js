// Fact-based analysis: the JavaScript port of analyze_topic.py.
//   1. measured facts (plain code): search intent, news drivers, dated events, coverage
//   2. explanation (language model): only from numbered evidence, every claim cites ids
//   3. check: each claim is rated against its cited evidence, by Jev (a decision model that
//      can only pick supported / partly / unsupported) when OPENCODE_API_KEY is set,
//      otherwise by a second text-model call
import { dayIn } from "./collect.js";
import { searchIntent } from "./intent.js";
import { DEFAULT_MODEL, askJev, parseJsonReply, requestModel } from "./models.js";

const isAscii = s => /^[\x00-\x7f]*$/.test(s);

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
    evidence[`S${i + 1}`] = `${a.published.slice(0, 10)} | ${a.source} | ${a.title}` + (a.summary ? ` | ${a.summary}` : "")
      + (a.found_by && a.found_by !== facts.topic ? ` | found by searching "${a.found_by}"` : "");
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
  const answers = await askJev(env, state, questions, "check");
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
  ], "check")).checks;
  return new Map(checks.filter(c => /^\d+$/.test(String(c.id))).map(c => [+c.id, { ...c, by: "model" }]));
}

async function checkClaims(env, result, evidence, language, sections = SECTIONS) {
  const items = sections.flatMap(section => result[section].map(c => [section, c]));
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
  for (const section of sections) {
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
  ], "write"));
  const result = {};
  let dropped = 0;
  for (const section of SECTIONS) {
    const [kept, n] = keepSupported(reply[section], evidence);
    result[section] = kept;
    dropped += n;
  }
  result.caveats = reply.caveats || [];
  result.unsupported_claims_removed = dropped;
  [result.summary] = keepSupported(reply.summary ? [reply.summary] : [], evidence)[0];
  result.summary = result.summary ? [result.summary] : [];
  result.failed_check_removed = await checkClaims(env, result, evidence, language, ["summary", ...SECTIONS]);
  result.summary = result.summary[0] || null;
  return result;
}

// Relevance filter ---------------------------------------------------------------------
// Before the writer sees any news, Jev answers yes/no for each article: is it mainly
// about the topic? Off-topic articles (keyword stuffing, passing mentions) are dropped,
// so the writer reads less and cannot cite something unrelated.

const RELEVANT_AT = 0.5; // Jev's probability of "yes" needed to keep an article

export async function relevantNews(env, news, topic) {
  if (!news.length || !env.OPENCODE_API_KEY) return { kept: news, dropped: [], method: "not filtered" };
  const state = `News articles found for the search topic "${topic}":\n\n` + news.map((a, n) =>
    `[${n}] ${a.source} | ${a.title}${a.summary ? ` | ${a.summary}` : ""}`).join("\n");
  const questions = Object.fromEntries(news.map((_, n) => [`a${n}`, {
    type: "noul",
    instructions: `Is article [${n}] mainly about ${topic}, rather than mentioning it in passing or being unrelated?`,
  }]));
  try {
    const answers = await askJev(env, state, questions, "relevance");
    const kept = [], dropped = [];
    news.forEach((a, n) => {
      const p = answers[`a${n}`]?.noul;
      (p === undefined || p >= RELEVANT_AT ? kept : dropped).push({ ...a, relevance: p ?? null });
    });
    return { kept, dropped, method: "Jev" };
  } catch (error) {
    return { kept: news, dropped: [], method: `not filtered (${error.message})` };
  }
}

// Run --------------------------------------------------------------------------------

export async function analyze(env, data) {
  const [relevance, [intentMethod, intents]] = await Promise.all([
    relevantNews(env, data.news, data.topic),
    searchIntent(env, data.related_searches, data.topic),
  ]);
  data = { ...data, news: relevance.kept };
  const facts = {
    topic: data.topic,
    coverage: data.news_momentum,
    news_unavailable: !data.news_momentum,
    spam_removed: data.news_spam_removed || 0,
    intent: intents,
    intent_method: intentMethod,
    drivers: newsDrivers(data.news, data.topic, data.geo),
    events: scheduledEvents(data.news),
    trends_matches: data.google_trends_matches,
    relevance: {
      method: relevance.method,
      kept: relevance.kept.length,
      dropped: relevance.dropped.map(a => ({ title: a.title, source: a.source, url: a.url, relevance: a.relevance })),
    },
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

// Overview: what is everyone searching for right now? -----------------------------------
// Used when no topic is typed. Google Trends' live list is the data: each trending search
// comes with its approximate volume and the news articles Google links to it. Those
// articles are the evidence. Jev sorts each trend into a category; the writer explains
// why each one trends and what they have in common; Jev checks every claim.

const TREND_CATEGORIES = {
  breaking_news: "an accident, disaster, crime or sudden news event",
  politics: "politics, government, elections, diplomacy, North Korea",
  economy: "stocks, companies, prices, the economy",
  sports: "a match, player, team or sports result",
  entertainment: "a TV show, celebrity, music, film or game",
  scheduled_event: "a planned event, holiday, ceremony or announcement on a set date",
  product_or_tech: "a product launch, app, gadget or technology",
  weather_or_seasonal: "weather, seasons, seasonal food or activities",
  other: "none of the above",
};

const OVERVIEW_PROMPT = `You explain what people are searching for most right now, and why.
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
}`;

export async function analyzeOverview(env, snapshot, lang) {
  const trends = snapshot.google_trends.slice(0, 15);
  const wikiTitles = (snapshot.wikipedia_top || []).map(w => w.title.toLowerCase());

  // Jev: one category per trend, from its term and headlines.
  let categories = {};
  if (env.OPENCODE_API_KEY && trends.length) {
    const state = "Trending Google searches right now, each with the headlines Google links to it:\n\n" + trends.map((t, n) =>
      `[${n}] "${t.term}": ` + (t.news.map(x => x.title).join(" / ") || "(no headlines)")).join("\n");
    const questions = Object.fromEntries(trends.map((t, n) => [`t${n}`, {
      type: "choice", instructions: `What kind of thing is trend [${n}] "${t.term}"?`, criteria: TREND_CATEGORIES,
    }]));
    try {
      categories = await askJev(env, state, questions, "categories");
    } catch { /* categories stay empty */ }
  }

  // Evidence: one [T] per trend, one [S] per linked article.
  const evidence = {}, links = {};
  let s = 0;
  const rows = trends.map((t, n) => {
    const id = `T${n + 1}`;
    const onWiki = wikiTitles.some(w => w.includes(t.term.toLowerCase()) || t.term.toLowerCase().includes(w));
    evidence[id] = `Trending search "${t.term}", about ${t.traffic_text} searches` + (onWiki ? ", also among the most-viewed Wikipedia pages" : "");
    const articleIds = t.news.map(a => {
      const sid = `S${++s}`;
      evidence[sid] = `article linked to "${t.term}" | ${a.source} | ${a.title}`;
      links[sid] = a.url;
      return sid;
    });
    const c = categories[`t${n}`];
    return {
      id, term: t.term, traffic: t.traffic, traffic_text: t.traffic_text, on_wikipedia: onWiki,
      category: c?.choice in TREND_CATEGORIES ? c.choice : null, category_confidence: c?.confidence ?? null,
      article_ids: articleIds, top_article: t.news[0] || null,
    };
  });

  const language = lang === "ko" ? "Korean" : "English";
  let explanation;
  try {
    const evidenceText = Object.entries(evidence).map(([k, v]) => `[${k}] ${v}`).join("\n");
    const reply = parseJsonReply(await requestModel(env, [
      { role: "system", content: OVERVIEW_PROMPT.replace("{language}", language) },
      { role: "user", content: `Region: ${snapshot.geo}\n\nEvidence:\n${evidenceText}` },
    ], "write"));
    explanation = {};
    let dropped = 0;
    for (const section of ["trends", "themes"]) {
      const [kept, n] = keepSupported(reply[section], evidence);
      explanation[section] = kept;
      dropped += n;
    }
    explanation.unsupported_claims_removed = dropped;
    explanation.failed_check_removed = await checkClaims(env, explanation, evidence, language, ["trends", "themes"]);
  } catch (error) {
    explanation = { error: String(error.message || error) };
  }

  // Attach each trend's explanation to its row.
  for (const r of rows) r.why = (explanation.trends || []).filter(c => c.term === r.term);

  return {
    kind: "overview",
    topic: `Trending now (${snapshot.geo})`,
    geo: snapshot.geo,
    source_collected_at: snapshot.collected_at,
    analyzed_at: new Date().toISOString().slice(0, 19) + "+00:00",
    rows, evidence, evidence_links: links,
    wikipedia_top: snapshot.wikipedia_top || [],
    explanation,
    writer_model: env.OPENROUTER_MODEL || DEFAULT_MODEL,
  };
}
