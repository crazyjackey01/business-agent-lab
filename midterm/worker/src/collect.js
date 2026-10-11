// Data collection: the JavaScript port of collect_trends.py and topic_trends.py.
// Same sources, same output shape, so the dashboard template works for both.

const HEADERS = { "User-Agent": "business-agent-lab-midterm/0.1 (student project)" };
const TRENDS_RSS = "https://trends.google.com/trending/rss?geo=";
const SUGGEST_URL = "https://suggestqueries.google.com/complete/search";
const WIKI_TOP = "https://wikimedia.org/api/rest_v1/metrics/pageviews/top";

// Gambling spam sites stuff unrelated keywords into headlines to get into Google News.
// Dropped unless the topic itself is about these words. The count is kept as a finding.
const SPAM_WORDS = ["토토", "카지노", "바카라", "슬롯", "베팅", "먹튀", "casino", "betting", "baccarat", "slots"];
const isSpam = (title, topic) => SPAM_WORDS.some(w => title.toLowerCase().includes(w) && !topic.toLowerCase().includes(w));

const KOREAN_LETTERS = [..."ㄱㄴㄷㄹㅁㅂㅅㅇㅈㅊㅋㅌㅍㅎ"];
const ENGLISH_LETTERS = [..."abcdefghijklmnopqrstuvwxyz"];
const WIKI_SKIP_PREFIXES = ["위키백과:", "특수:", "Wikipedia:", "Special:", "Main_Page"];

// "Today" depends on where the searchers are, not on the server's clock (UTC).
export const TIMEZONES = { KR: "Asia/Seoul", US: "America/New_York" };

export function dayIn(date, geo) {
  return new Intl.DateTimeFormat("en-CA", { timeZone: TIMEZONES[geo] || "UTC" }).format(date); // YYYY-MM-DD
}

function addDays(isoDay, n) {
  const d = new Date(isoDay + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

// RSS parsing. Workers have no DOMParser, and these feeds are simple, so regexes are enough.

function decode(text) {
  return (text || "")
    .replace(/^<!\[CDATA\[([\s\S]*)\]\]>$/, "$1")
    .replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"')
    .replace(/&#39;|&apos;/g, "'").replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(+n))
    .replace(/&amp;/g, "&").trim();
}

function tag(xml, name) {
  const m = xml.match(new RegExp(`<${name}(?:\\s[^>]*)?>([\\s\\S]*?)</${name}>`));
  return m ? decode(m[1]) : "";
}

function items(xml, name = "item") {
  return [...xml.matchAll(new RegExp(`<${name}>([\\s\\S]*?)</${name}>`, "g"))].map(m => m[1]);
}

// Google answers busy or unfamiliar clients with 503/429; wait a little and try again.
async function getText(url, headers = HEADERS) {
  let response;
  for (let attempt = 0; attempt < 3; attempt++) {
    response = await fetch(url, { headers });
    if (response.ok) return response.text();
    if (![429, 503].includes(response.status)) break;
    await new Promise(r => setTimeout(r, 800 * (attempt + 1)));
  }
  throw new Error(`HTTP ${response.status} from ${new URL(url).host}`);
}

// Google Trends "Trending Now" ------------------------------------------------

export function parseTraffic(text) {
  let t = (text || "").replace(/[,+]/g, "").trim().toUpperCase();
  let multiplier = 1;
  if (t.endsWith("K")) { multiplier = 1_000; t = t.slice(0, -1); }
  else if (t.endsWith("M")) { multiplier = 1_000_000; t = t.slice(0, -1); }
  const n = parseFloat(t);
  return Number.isFinite(n) ? Math.round(n * multiplier) : 0;
}

export async function fetchGoogleTrends(geo) {
  const xml = await getText(TRENDS_RSS + geo);
  const trends = items(xml).map(item => {
    const trafficText = tag(item, "ht:approx_traffic");
    return {
      term: tag(item, "title"),
      traffic: parseTraffic(trafficText),
      traffic_text: trafficText,
      started: tag(item, "pubDate"),
      news: items(item, "ht:news_item").map(n => ({
        title: tag(n, "ht:news_item_title"),
        url: tag(n, "ht:news_item_url"),
        source: tag(n, "ht:news_item_source"),
      })),
    };
  });
  return trends.sort((a, b) => b.traffic - a.traffic);
}

// Wikipedia most viewed ---------------------------------------------------------

export async function fetchWikipediaTop(wiki, isoDay, limit = 25) {
  const [y, m, d] = isoDay.split("-");
  const response = await fetch(`${WIKI_TOP}/${wiki}.wikipedia/all-access/${y}/${m}/${d}`, { headers: HEADERS });
  if (!response.ok) throw new Error(`HTTP ${response.status} from Wikimedia`);
  const articles = (await response.json()).items[0].articles;
  return articles
    .filter(a => !WIKI_SKIP_PREFIXES.some(p => a.article.startsWith(p)))
    .slice(0, limit)
    .map(a => ({ title: a.article.replace(/_/g, " "), views: a.views }));
}

// A day's Wikipedia totals appear a few hours after it ends (UTC), so if yesterday is not
// ready yet, use the day before. Wikipedia is only a cross-check, so failing is allowed.
async function latestWikipediaTop(wiki) {
  const today = new Date().toISOString().slice(0, 10);
  for (const back of [1, 2]) {
    const day = addDays(today, -back);
    try {
      return [day, await fetchWikipediaTop(wiki, day)];
    } catch { /* not published yet */ }
  }
  return [null, []];
}

export async function collectSnapshot(geo = "KR", wiki = "ko") {
  const [trends, [wikiDay, wikiTop]] = await Promise.all([fetchGoogleTrends(geo), latestWikipediaTop(wiki)]);
  return {
    collected_at: new Date().toISOString().slice(0, 19) + "+00:00",
    geo, wiki, wiki_day: wikiDay,
    google_trends: trends,
    wikipedia_top: wikiTop,
  };
}

// Autocomplete --------------------------------------------------------------------

async function fetchSuggestions(query, lang, geo) {
  const params = new URLSearchParams({ client: "firefox", hl: lang, gl: geo.toLowerCase(), q: query });
  try {
    const response = await fetch(`${SUGGEST_URL}?${params}`, { headers: HEADERS });
    if (!response.ok) return [];
    return (await response.json())[1] || [];
  } catch {
    return []; // one failed letter should not stop the run
  }
}

const escapeRegex = s => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

export async function relatedSearches(topic, lang, geo) {
  const letters = lang === "ko" ? KOREAN_LETTERS : ENGLISH_LETTERS;
  const queries = [topic, ...letters.map(l => `${topic} ${l}`)];
  const results = await Promise.all(queries.map(q => fetchSuggestions(q, lang, geo)));

  const counts = new Map();
  for (const phrases of results) {
    for (const p of phrases) counts.set(p.toLowerCase(), (counts.get(p.toLowerCase()) || 0) + 1);
  }
  counts.delete(topic.toLowerCase());
  // Drop phrases where the topic is only the start of another word ("physical ai" -> "physical ailments").
  const pattern = new RegExp(`(^|\\s)${escapeRegex(topic.toLowerCase())}(\\s|$)`);
  return [...counts]
    .filter(([p]) => pattern.test(p))
    .sort((a, b) => b[1] - a[1])
    .map(([phrase, n]) => ({ phrase, times_suggested: n }));
}

// News ----------------------------------------------------------------------------


// News through Gemini with Google Search ---------------------------------------
// Google News refuses Cloudflare's servers, but Google's official Gemini API can search
// Google for us. Gemini lists the articles it found, and Google attaches citations
// (url_citation annotations) to the parts of its answer that come from real pages.
// An article is kept only if its line carries such a citation, so the model cannot
// add an article that Google Search did not return.

const GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/interactions";
// Tried in order. Listing articles is a simple job, so the fastest model goes first
// (about 6 s); the bigger ones are fallbacks for when it is busy.
const GEMINI_SEARCH_MODELS = ["gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-3.8-flash"];

async function geminiSearch(env, input, models = GEMINI_SEARCH_MODELS) {
  let lastError;
  for (const model of models) {
    for (let attempt = 0; attempt < 2; attempt++) {
      const response = await fetch(GEMINI_URL, {
        method: "POST",
        headers: { "x-goog-api-key": env.GEMINI_API_KEY, "Content-Type": "application/json" },
        body: JSON.stringify({ model, input, tools: [{ type: "google_search" }] }),
      });
      const data = await response.json().catch(() => ({}));
      if (response.ok && !data.error) {
        env.usage?.push({ step: "news search", model, input_tokens: data.usage?.total_input_tokens || 0,
          output_tokens: data.usage?.total_output_tokens || 0, cost: null });
        return { ...data, model };
      }
      lastError = `Gemini ${model}: ${data.error?.message || response.status}`;
      if (response.status !== 503 && data.error?.code !== "service_unavailable") break; // only "busy" is worth retrying
      await new Promise(r => setTimeout(r, 3000));
    }
  }
  throw new Error(lastError);
}

async function geminiNewsOne(env, topic, geo) {
  const today = dayIn(new Date(), geo);
  const where = geo === "KR" ? " in South Korea (Korean-language news)" : geo === "US" ? " (English-language news)" : "";
  const input = `Use Google Search to find news articles published in the 7 days up to ${today} about "${topic}"${where}.
List up to 20 different articles, newest first, one per line, exactly in this format and nothing else:
YYYY-MM-DD | outlet | headline | one sentence with the key facts the article reports`;
  // The fast model sometimes lists only one or two articles; then ask the next model.
  let result;
  for (let i = 0; i < GEMINI_SEARCH_MODELS.length; i++) {
    let data;
    try {
      data = await geminiSearch(env, input, GEMINI_SEARCH_MODELS.slice(i));
    } catch (error) {
      if (result) break; // bigger models busy: keep the few articles we have
      throw error;
    }
    result = parseGeminiArticles(data, topic);
    const used = GEMINI_SEARCH_MODELS.indexOf(data.model);
    if (result.articles.length >= MIN_ARTICLES || used === GEMINI_SEARCH_MODELS.length - 1) break;
    i = used; // continue after the model that answered
  }
  return result;
}

const MIN_ARTICLES = 3;

function parseGeminiArticles(data, topic) {
  let text = "", annotations = [], suggestions = "", queries = [];
  for (const step of data.steps || []) {
    if (step.type === "google_search_call") queries.push(...(step.arguments?.queries || []));
    if (step.type === "google_search_result") suggestions ||= step.result?.find(r => r.search_suggestions)?.search_suggestions || "";
    if (step.type === "model_output") {
      for (const c of step.content || []) {
        if (c.type === "text") { annotations.push(...(c.annotations || []).map(a => ({ ...a, offset: new TextEncoder().encode(text).length }))); text += c.text; }
      }
    }
  }

  // Citation positions count UTF-8 bytes, not characters, so measure lines in bytes.
  const encoder = new TextEncoder();
  const articles = [];
  let byte = 0;
  for (const line of text.split("\n")) {
    const start = byte, end = byte + encoder.encode(line).length;
    byte = end + 1;
    const parts = line.replace(/^[\s*•-]+/, "").split("|").map(x => x.trim());
    if (parts.length < 3 || !/^\d{4}-\d{2}-\d{2}$/.test(parts[0])) continue;
    const cites = annotations.filter(a => a.type === "url_citation" && a.offset + a.end_index > start && a.offset + a.end_index <= end + 1);
    if (!cites.length) continue; // no Google citation: not kept
    articles.push({
      title: parts[2],
      source: parts[1],
      summary: parts[3] || "",
      url: cites[0].url,
      cited_domains: [...new Set(cites.map(c => c.title))],
      published: new Date(parts[0] + "T12:00:00Z").toISOString(),
    });
  }
  return { articles, suggestions, queries, model: data.model, searched: topic, dropped_uncited: text.split("\n").filter(l => /^\s*[*•-]?\s*\d{4}-\d{2}-\d{2}\s*\|/.test(l)).length - articles.length };
}

// One search per angle, all at once: the topic itself plus the phrases people type most
// with it (from autocomplete). This ties what people search to the news about it, and
// gives more articles than one search. Articles are merged by headline.
export async function geminiNews(env, topic, geo, related = []) {
  const extra = related.map(r => r.phrase).filter(p => p !== topic.toLowerCase()).slice(0, 2);
  const results = await Promise.allSettled([topic, ...extra].map(q => geminiNewsOne(env, q, geo)));
  const ok = results.filter(r => r.status === "fulfilled").map(r => r.value);
  if (!ok.length) throw results[0].reason;

  const byTitle = new Map();
  for (const r of ok) {
    for (const a of r.articles) {
      const key = a.title.replace(/\s+/g, "").toLowerCase();
      if (!byTitle.has(key)) byTitle.set(key, { ...a, found_by: r.searched });
    }
  }
  return {
    articles: [...byTitle.values()].sort((a, b) => b.published.localeCompare(a.published)),
    suggestions: ok[0].suggestions,
    queries: ok.flatMap(r => r.queries),
    searched: ok.map(r => r.searched),
    model: [...new Set(ok.map(r => r.model))].join(", "),
    dropped_uncited: ok.reduce((n, r) => n + r.dropped_uncited, 0),
    failed: results.filter(r => r.status === "rejected").map(r => String(r.reason?.message || r.reason)),
  };
}

// Trending searches that mention the topic. Latin words must match as whole words
// ("ai" must not match "weather"); Korean matches anywhere because of particles.
export function matchingTrends(trends, topic, extraWords = []) {
  const patterns = [topic, ...extraWords].map(w => w.toLowerCase()).map(p =>
    /^[\x00-\x7f]*$/.test(p) ? new RegExp(`\\b${escapeRegex(p)}\\b`) : new RegExp(escapeRegex(p)));
  return trends.filter(t => {
    const text = [t.term, ...t.news.map(n => n.title)].join(" ").toLowerCase();
    return patterns.some(p => p.test(text));
  });
}

export async function collectTopic(env, topic, lang, geo) {
  // A blocked source should not stop the search; the page shows which ones failed.
  // News comes only from Gemini + Google Search here: the Google News feed refuses
  // Cloudflare's servers, so there are no daily counts (momentum) in this version.
  const sourceErrors = [];
  const [related, trends] = await Promise.all([
    relatedSearches(topic, lang, geo),
    fetchGoogleTrends(geo).catch(error => {
      sourceErrors.push(`google trends: ${error.message}`);
      return [];
    }),
  ]);
  if (!related.length) sourceErrors.push("autocomplete: no suggestions returned");

  // Searched for the topic and for the top autocomplete phrases (hence after related).
  const google = env.GEMINI_API_KEY
    ? await geminiNews(env, topic, geo, related).catch(error => { sourceErrors.push(`gemini search: ${error.message}`); return null; })
    : null;
  if (google?.failed?.length) sourceErrors.push(...google.failed.map(f => `gemini search (one angle): ${f}`));
  const found = google?.articles || [];
  const articles = found.filter(a => !isSpam(a.title, topic));
  return {
    topic, lang, geo,
    collected_at: new Date().toISOString().slice(0, 19) + "+00:00",
    related_searches: related,
    news_momentum: null, // needs daily counts; only the local version has them
    news: articles,
    news_source: google ? `Google Search via ${google.model}` : "none",
    google_search: google && { queries: google.queries, searched: google.searched, suggestions: google.suggestions, dropped_uncited: google.dropped_uncited },
    news_spam_removed: found.length - articles.length,
    google_trends_matches: matchingTrends(trends, topic),
    source_errors: sourceErrors,
  };
}
