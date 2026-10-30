/**
 * llm.ts — Anthropic Messages API client (port of backend/llm_client.py).
 *
 * call_haiku() semantics are kept: the system prompt carries a cache_control
 * breakpoint, tool_use responses come back as JSON text, transient failures are
 * retried like the Python SDK (2 retries), and the function never throws —
 * errors are reported through LLMResponse.error with the safe fallback as text.
 */

import { dumps, pyRepr, Env, Row } from "./util";

export const HAIKU_MODEL = "claude-haiku-4-5";
const MAX_RETRIES = 2; // anthropic SDK default

// Safe fallback returned when the LLM cannot complete the review (llm_client._SAFE_FALLBACK).
const LLM_SAFE_FALLBACK = {
  deviation_summary:
    "Automated review could not be completed due to a system error. " +
    "Manual QA review is required before any disposition decision is made.",
  sop_reference: "No directly applicable SOP section found",
  risk_level: "High",
  qa_review_required: true,
  rationale:
    "The automated assistant encountered an error and could not produce a " +
    "reliable assessment. All uncertain or failed reviews are treated as " +
    "High risk per the conservative escalation policy.",
  confidence: "Low",
};

export interface LLMResponse {
  text: string;            // raw text content OR JSON-serialised tool input
  input_tokens: number;
  output_tokens: number;
  latency_ms: number;
  error: string | null;    // null on success
  stop_reason: string | null;
  cached_tokens: number;
}

export const succeeded = (r: LLMResponse) => r.error === null;

class StatusError extends Error {
  constructor(public status: number, public body: string) {
    // Same text as anthropic.APIStatusError.message: "Error code: 500 - {'type': ...}"
    let shown = body;
    try { shown = pyRepr(JSON.parse(body)); } catch { /* keep raw text */ }
    super(`Error code: ${status} - ${shown}`);
  }
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function postMessages(env: Env, payload: Row): Promise<Row> {
  const base = (env.ANTHROPIC_BASE_URL || "https://api.anthropic.com").replace(/\/+$/, "");
  let lastErr: unknown;
  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    if (attempt > 0) await sleep(Math.min(500 * 2 ** (attempt - 1), 8000) * (0.75 + Math.random() * 0.25));
    let res: Response;
    try {
      res = await fetch(`${base}/v1/messages`, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-api-key": env.ANTHROPIC_API_KEY ?? "",
          "anthropic-version": "2023-06-01",
        },
        body: JSON.stringify(payload),
        signal: AbortSignal.timeout(120_000),
      });
    } catch (e) {
      lastErr = e;
      continue;              // connection error / timeout — retried like the SDK
    }
    const text = await res.text();
    if (res.ok) return JSON.parse(text);
    lastErr = new StatusError(res.status, text);
    if (![408, 409, 429].includes(res.status) && res.status < 500) break;
  }
  throw lastErr;
}

function extractContent(response: Row): [string, string | null] {
  for (const block of response.content ?? []) {
    if (block.type === "tool_use") return [dumps(block.input, false), "tool_use"];
    if (block.type === "text") return [block.text, response.stop_reason ?? null];
  }
  return ["", response.stop_reason ?? null];
}

/** Call Claude Haiku via the Messages API. Never throws. */
export async function callHaiku(
  env: Env,
  systemPrompt: string,
  userMessage: string,
  maxTokens = 1024,
  tools?: Row[],
  toolChoice?: Row,
): Promise<LLMResponse> {
  const t0 = Date.now();
  const fail = (error: string): LLMResponse => ({
    text: dumps(LLM_SAFE_FALLBACK), input_tokens: 0, output_tokens: 0,
    latency_ms: Date.now() - t0, error, stop_reason: null, cached_tokens: 0,
  });

  if (!(env.ANTHROPIC_API_KEY ?? "").trim()) {
    return fail(
      "Configuration error: ANTHROPIC_API_KEY is not set. " +
      "Add it to your .env file or set it in the shell environment.",
    );
  }

  const payload: Row = {
    model: HAIKU_MODEL,
    max_tokens: maxTokens,
    // Cache the system prompt — same prompt across all deviation reviews.
    system: [{ type: "text", text: systemPrompt, cache_control: { type: "ephemeral" } }],
    messages: [{ role: "user", content: userMessage }],
  };
  if (tools) payload.tools = tools;
  if (toolChoice) payload.tool_choice = toolChoice;

  try {
    const response = await postMessages(env, payload);
    const [text, stopReason] = extractContent(response);
    return {
      text,
      input_tokens: response.usage?.input_tokens ?? 0,
      output_tokens: response.usage?.output_tokens ?? 0,
      latency_ms: Date.now() - t0,
      error: null,
      stop_reason: stopReason,
      cached_tokens: response.usage?.cache_read_input_tokens ?? 0,
    };
  } catch (e) {
    if (e instanceof StatusError) {
      if (e.status === 401) return fail(`Authentication error — check ANTHROPIC_API_KEY: ${e.message}`);
      if (e.status === 429) return fail(`Rate limit exceeded — retry after a pause: ${e.message}`);
      return fail(`Anthropic API error ${e.status}: ${e.message}`);
    }
    if (e instanceof Error && (e.name === "TimeoutError" || e.name === "AbortError")) {
      return fail("Network error connecting to Anthropic API: Request timed out.");
    }
    if (e instanceof TypeError) return fail("Network error connecting to Anthropic API: Connection error.");
    return fail(`Unexpected error: ${e instanceof Error ? `${e.name}: ${e.message}` : String(e)}`);
  }
}
