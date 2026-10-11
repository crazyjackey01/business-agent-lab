// Model calls shared by the analysis steps: the writer (OpenRouter) and Jev (OpenCode Zen).
// Every call adds a row to env.usage (one list per search) so the page can show the cost.

const OPENROUTER = "https://openrouter.ai/api/v1/chat/completions";
// Writes the analysis. Override with the OPENROUTER_MODEL variable.
export const DEFAULT_MODEL = "anthropic/claude-sonnet-5.5";
const MAX_REPLY_TOKENS = 4000; // analyses use about 2,000
const JEV_ENDPOINT = "https://opencode.ai/zen/v1/systemone";
const JEV_MAX_QUESTIONS = 100; // per request: Jev refuses requests over ~60k tokens (about 150 intent questions)
const JEV_INPUT_PRICE = 0.042 / 1e6; // dollars per input token for paid jev-1.13; output is free

function recordUsage(env, row) {
  if (env.usage) env.usage.push(row);
}

// Jev writes no text: it answers questions whose possible answers we fix in advance.
export async function askJev(env, state, questions, step) {
  const ids = Object.keys(questions), answers = {};
  // One batch at a time, and wait on 429.
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
      const model = env.JEV_MODEL || "jev-1.13-free";
      recordUsage(env, {
        step, model, questions: batch.length,
        input_tokens: data.usage?.input_tokens || 0, output_tokens: data.usage?.output_tokens || 0,
        cost: model.endsWith("-free") ? 0 : (data.usage?.input_tokens || 0) * JEV_INPUT_PRICE,
      });
      break;
    }
  }
  return answers;
}

export async function requestModel(env, messages, step) {
  // max_tokens caps the reply; without it OpenRouter reserves credit for a 65k-token reply.
  const body = JSON.stringify({ model: env.OPENROUTER_MODEL || DEFAULT_MODEL, messages, max_tokens: MAX_REPLY_TOKENS });
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
    recordUsage(env, {
      step, model: data.model || env.OPENROUTER_MODEL || DEFAULT_MODEL,
      input_tokens: data.usage?.prompt_tokens || 0, output_tokens: data.usage?.completion_tokens || 0,
      cost: data.usage?.cost ?? null,
    });
    return data.choices[0].message.content;
  }
}

export function parseJsonReply(text) {
  const match = (text || "").match(/\{[\s\S]*\}/);
  if (!match) throw new Error("the model did not reply with JSON");
  return JSON.parse(match[0]);
}
