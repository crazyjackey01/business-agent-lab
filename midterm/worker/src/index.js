// Trend Signals on Cloudflare Workers: the server version of app.py.
//   GET  /             dashboard with a search box (same template as the Python version)
//   POST /api/analyze  {topic, region, password} -> collect + analyze + save, returns the analysis
// Analyses and the general-trends snapshot are kept in Workers KV (binding ANALYSES).
// Eval results come from the Python side (python midterm/eval/summary.py before deploying).
import template from "../../dashboard_template.html";
import evalSummary from "../../data/eval/summary.json";
import { analyze, analyzeOverview } from "./analyze.js";
import { collectSnapshot, collectTopic } from "./collect.js";

const MAX_TOPIC_LENGTH = 60;
const SHOWN_ANALYSES = 6;
const SNAPSHOT_MAX_AGE_MS = 60 * 60 * 1000; // refresh general trends at most hourly

const json = (obj, status = 200) => new Response(JSON.stringify(obj), {
  status, headers: { "Content-Type": "application/json; charset=utf-8" },
});

// Korean letters -> Korea; otherwise US English.
function guessRegion(topic) {
  return /[가-힣]/.test(topic) ? ["ko", "KR"] : ["en", "US"];
}

const slug = topic => topic.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "-").replace(/^-|-$/g, "");

// Constant-time comparison so the password can't be guessed by timing.
function samePassword(a, b) {
  const x = new TextEncoder().encode(a), y = new TextEncoder().encode(b);
  if (x.length !== y.length) return false;
  let diff = 0;
  for (let i = 0; i < x.length; i++) diff |= x[i] ^ y[i];
  return diff === 0;
}

async function latestSnapshot(env) {
  const stored = await env.ANALYSES.get("snapshot:KR", "json");
  if (stored && Date.now() - Date.parse(stored.collected_at) < SNAPSHOT_MAX_AGE_MS) return stored;
  try {
    const fresh = await collectSnapshot("KR", "ko");
    await env.ANALYSES.put("snapshot:KR", JSON.stringify(fresh));
    return fresh;
  } catch {
    return stored; // Google or Wikipedia down: show the older one
  }
}

async function recentAnalyses(env) {
  const { keys } = await env.ANALYSES.list({ prefix: "analysis:" });
  const newest = keys
    .sort((a, b) => (b.metadata?.analyzed_at || "").localeCompare(a.metadata?.analyzed_at || ""))
    .slice(0, SHOWN_ANALYSES);
  const analyses = await Promise.all(newest.map(k => env.ANALYSES.get(k.name, "json")));
  return analyses.filter(Boolean);
}

async function page(env) {
  const [analyses, snapshot, overview] = await Promise.all([
    recentAnalyses(env), latestSnapshot(env), env.ANALYSES.get("overview:KR", "json"),
  ]);
  const data = {
    built_at: new Date().toISOString().slice(0, 16),
    analyses, snapshot, overview,
    eval: evalSummary,
    live: true,
    needs_password: Boolean(env.SEARCH_PASSWORD),
  };
  // "</" inside the JSON would end the <script> tag early.
  const html = template.replace("__DATA__", JSON.stringify(data).replace(/<\//g, "<\\/"));
  return new Response(html, { headers: { "Content-Type": "text/html; charset=utf-8" } });
}

async function runSearch(request, env) {
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "bad request" }, 400);
  }
  if (env.SEARCH_PASSWORD && !samePassword(String(body.password || ""), env.SEARCH_PASSWORD)) {
    return json({ error: "wrong password" }, 401);
  }
  const topic = String(body.topic || "").split(/\s+/).filter(Boolean).join(" ");
  // No topic: explain what everyone is searching for right now.
  if (!topic) return runOverview(env, body.region === "US" ? "US" : "KR");
  if (topic.length > MAX_TOPIC_LENGTH) {
    return json({ error: `type a topic of 1-${MAX_TOPIC_LENGTH} characters` }, 400);
  }
  let [lang, geo] = guessRegion(topic);
  if (body.region === "KR") [lang, geo] = ["ko", "KR"];
  if (body.region === "US") [lang, geo] = ["en", "US"];

  try {
    // A per-search copy of env with a usage list that every model call adds to.
    const ctx = { ...env, usage: [] };
    const data = await collectTopic(ctx, topic, lang, geo);
    const result = await analyze(ctx, data);
    result.usage = ctx.usage;
    await env.ANALYSES.put(`analysis:${slug(topic)}:${geo}`, JSON.stringify(result), {
      metadata: { analyzed_at: result.analyzed_at },
    });
    return json(result);
  } catch (error) {
    return json({ error: `${error.name}: ${error.message}` }, 500);
  }
}

async function runOverview(env, geo) {
  try {
    const ctx = { ...env, usage: [] };
    const snapshot = await collectSnapshot(geo, geo === "KR" ? "ko" : "en");
    await env.ANALYSES.put(`snapshot:${geo}`, JSON.stringify(snapshot));
    const result = await analyzeOverview(ctx, snapshot, geo === "KR" ? "ko" : "en");
    result.usage = ctx.usage;
    await env.ANALYSES.put(`overview:${geo}`, JSON.stringify(result), { metadata: { analyzed_at: result.analyzed_at } });
    return json(result);
  } catch (error) {
    return json({ error: `${error.name}: ${error.message}` }, 500);
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "GET" && (url.pathname === "/" || url.pathname === "/index.html")) return page(env);
    if (request.method === "POST" && url.pathname === "/api/analyze") return runSearch(request, env);
    return json({ error: "not found" }, 404);
  },
};
