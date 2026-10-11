// Data collection: the JavaScript port of collect_trends.py and topic_trends.py.
// Same sources, same output shape, so the dashboard template works for both.

const HEADERS = { "User-Agent": "business-agent-lab-midterm/0.1 (student project)" };
const TRENDS_RSS = "https://trends.google.com/trending/rss?geo=";
const SUGGEST_URL = "https://suggestqueries.google.com/complete/search";
const NEWS_RSS = "https://news.google.com/rss/search";
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

async function getText(url) {
  const response = await fetch(url, { headers: HEADERS });
  if (!response.ok) throw new Error(`HTTP ${response.status} from ${new URL(url).host}`);
  return response.text();
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

export async function collectSnapshot(geo = "KR", wiki = "ko") {
  const yesterday = addDays(new Date().toISOString().slice(0, 10), -1);
  const [trends, wikiTop] = await Promise.all([fetchGoogleTrends(geo), fetchWikipediaTop(wiki, yesterday)]);
  return {
    collected_at: new Date().toISOString().slice(0, 19) + "+00:00",
    geo, wiki, wiki_day: yesterday,
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

async function fetchNews(query, lang, geo) {
  const params = new URLSearchParams({ q: query, hl: lang, gl: geo, ceid: `${geo}:${lang}` });
  const xml = await getText(`${NEWS_RSS}?${params}`);
  const articles = [];
  for (const item of items(xml)) {
    const source = tag(item, "source");
    let title = tag(item, "title");
    // Google appends " - Source" to every title.
    if (source && title.endsWith(` - ${source}`)) title = title.slice(0, -(source.length + 3));
    const published = new Date(tag(item, "pubDate"));
    if (isNaN(published)) continue;
    articles.push({ title, source, url: tag(item, "link"), published: published.toISOString() });
  }
  return articles;
}

// One query returns at most 100 articles, so ask per day (after:/before:) to keep
// each day's count accurate. Spam is dropped before counting.
// Returns [articles newest first, counts today first, spam headlines removed].
export async function newsByDay(topic, lang, geo, days = 7) {
  const today = dayIn(new Date(), geo);
  const dayList = Array.from({ length: days }, (_, d) => addDays(today, -d));
  const perDay = await Promise.all(dayList.map(async day => {
    const query = `${topic} after:${addDays(day, -1)} before:${addDays(day, 1)}`;
    return (await fetchNews(query, lang, geo)).filter(a => dayIn(new Date(a.published), geo) === day);
  }));

  const clean = perDay.map(list => list.filter(a => !isSpam(a.title, topic)));
  const spam = perDay.flat().length - clean.flat().length;
  const byUrl = new Map();
  clean.flat().forEach(a => byUrl.set(a.url, a));
  const articles = [...byUrl.values()].sort((a, b) => b.published.localeCompare(a.published));
  return [articles, clean.map(list => list.length), spam];
}

export function newsMomentum(perDay) {
  const [today, ...previous] = perDay;
  const baseline = previous.length ? previous.reduce((a, b) => a + b, 0) / previous.length : 0;
  return {
    today,
    previous_daily_average: Math.round(baseline * 10) / 10,
    momentum: baseline ? Math.round((today / baseline) * 100) / 100 : 0,
    per_day: perDay,
    capped_days: perDay.filter(n => n >= 100).length,
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

export async function collectTopic(topic, lang, geo) {
  const [related, [news, perDay, spam], trends] = await Promise.all([
    relatedSearches(topic, lang, geo),
    newsByDay(topic, lang, geo),
    fetchGoogleTrends(geo).catch(() => []),
  ]);
  return {
    topic, lang, geo,
    collected_at: new Date().toISOString().slice(0, 19) + "+00:00",
    related_searches: related,
    news_momentum: newsMomentum(perDay),
    news,
    news_spam_removed: spam,
    google_trends_matches: matchingTrends(trends, topic),
  };
}
