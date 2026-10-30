/**
 * SOP Deviation Review Assistant — Cloudflare Worker API (port of the FastAPI
 * backend in backend/). Serves the same /api/* routes from the same Worker as
 * the React frontend (static assets), with D1 in place of SQLite.
 *
 * Endpoints:
 *   GET  /health, /api/health
 *   POST /api/review                  — retrieve SOPs, assess with Haiku, log trace
 *   GET  /api/traces                  — 20 most recent traces
 *   POST /api/feedback                — thumbs up/down on a trace
 *   GET  /api/feedback                — feedback joined with traces
 *   GET  /api/dashboard/metrics       — dashboard metrics
 *   POST /api/evals/runs              — start an eval run            (X-Eval-Token)
 *   POST /api/evals/runs/{run}/cases/{case} — score one case        (X-Eval-Token)
 *   POST /api/evals/runs/{run}/finish — summary + AgentOps push      (X-Eval-Token)
 *   GET  /api/evals/results           — results for a run (latest by default)
 *   POST /api/agentops/sync           — push the last 7 days of costs to AgentOps
 */

import { fullSync, INPUT_PRICE, OUTPUT_PRICE, pushDailyCost, pushEvalResults, pushTrace } from "./agentops";
import { computeSummary, EVAL_CASES, evalCase, fetchResults } from "./evals";
import { pushLangSmithRun } from "./langsmith";
import { assessDeviationTraced, SAFE_FALLBACK } from "./prompts";
import { searchSop, SopChunk } from "./retrieval";
import { Ctx, dumps, Env, HttpError, pyLen, pyRound, Row, utcStamp } from "./util";

const PROMPT_VERSION = "v1"; // increment when SYSTEM_PROMPT or tool schema changes
const RATE_LIMIT_PER_MINUTE = 10;

const ALLOWED_ORIGINS = [
  "http://localhost:5173",
  "http://localhost:5174",
  "http://localhost:3000",
  "https://gmpdeviationreview.krishnaparuchuri.com",
  "https://pharmacomplianceai.krishna1parchuri.workers.dev",
];

// ─────────────────────────────────────────────────────────────────────────────
//  Helpers
// ─────────────────────────────────────────────────────────────────────────────

function corsHeaders(request: Request): Record<string, string> {
  const origin = request.headers.get("Origin");
  if (!origin || !ALLOWED_ORIGINS.includes(origin)) return {};
  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization, Accept, X-Eval-Token",
    Vary: "Origin",
  };
}

const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });

// FastAPI-style 422 body: {"detail": [{type, loc, msg, input}]}
const invalid = (type: string, loc: (string | number)[], msg: string, input: unknown = null) =>
  new HttpError(422, [{ type, loc, msg, input }]);

async function readJson(request: Request): Promise<Row> {
  const text = await request.text();
  if (!text) throw invalid("missing", ["body"], "Field required");
  let body: unknown;
  try { body = JSON.parse(text); } catch { throw invalid("json_invalid", ["body", 0], "JSON decode error"); }
  if (typeof body !== "object" || body === null || Array.isArray(body)) {
    throw invalid("model_attributes_type", ["body"], "Input should be a valid dictionary or object to extract fields from", body);
  }
  return body as Row;
}

function strField(body: Row, name: string, opts: { required?: boolean; min?: number; max?: number } = {}): string | null {
  const v = body[name];
  if (v === undefined || (v === null && !opts.required)) {
    if (opts.required) throw invalid("missing", ["body", name], "Field required", body);
    return null;
  }
  if (typeof v !== "string") throw invalid("string_type", ["body", name], "Input should be a valid string", v);
  if (opts.min !== undefined && pyLen(v) < opts.min) {
    throw invalid("string_too_short", ["body", name], `String should have at least ${opts.min} characters`, v);
  }
  if (opts.max !== undefined && pyLen(v) > opts.max) {
    throw invalid("string_too_long", ["body", name], `String should have at most ${opts.max} characters`, v);
  }
  return v;
}

// Pydantic lax-mode int: ints, integral floats and integer strings.
function intField(body: Row, name: string): number {
  const v = body[name];
  if (v === undefined) throw invalid("missing", ["body", name], "Field required", body);
  if (typeof v === "number" && Number.isInteger(v)) return v;
  if (typeof v === "string" && /^\s*[-+]?\d+\s*$/.test(v)) return parseInt(v, 10);
  throw invalid("int_parsing", ["body", name], "Input should be a valid integer", v);
}

function queryInt(url: URL, name: string, def: number, min: number, max: number): number {
  const raw = url.searchParams.get(name);
  if (raw === null) return def;
  if (!/^\s*[-+]?\d+\s*$/.test(raw)) {
    throw invalid("int_parsing", ["query", name], "Input should be a valid integer, unable to parse string as an integer", raw);
  }
  const n = parseInt(raw, 10);
  if (n < min) throw invalid("greater_than_equal", ["query", name], `Input should be greater than or equal to ${min}`, raw);
  if (n > max) throw invalid("less_than_equal", ["query", name], `Input should be less than or equal to ${max}`, raw);
  return n;
}

function requireEvalToken(request: Request, env: Env) {
  // Without this, any internet user could trigger 30+ LLM calls and drain credits.
  const expected = (env.EVAL_SECRET_TOKEN ?? "").trim();
  if (!expected || request.headers.get("X-Eval-Token") !== expected) throw new HttpError(403, "Forbidden");
}

/** Sliding-window limit of 10 requests/minute per IP; only allowed requests are recorded. */
async function isRateLimited(env: Env, ip: string): Promise<boolean> {
  const now = Date.now() / 1000;
  const [, count] = await env.DB.batch([
    env.DB.prepare("DELETE FROM rate_limit_hits WHERE ts <= ?").bind(now - 60),
    env.DB.prepare("SELECT COUNT(*) AS n FROM rate_limit_hits WHERE ip = ?").bind(ip),
  ]);
  if (Number(count.results[0]?.n ?? 0) >= RATE_LIMIT_PER_MINUTE) return true;
  await env.DB.prepare("INSERT INTO rate_limit_hits (ip, ts) VALUES (?, ?)").bind(ip, now).run();
  return false;
}

// ─────────────────────────────────────────────────────────────────────────────
//  POST /api/review
// ─────────────────────────────────────────────────────────────────────────────

async function review(request: Request, env: Env, ctx: Ctx): Promise<Response> {
  const body = await readJson(request);
  const userInput = strField(body, "user_input", { required: true, min: 10, max: 4000 })!;
  const caseId = strField(body, "case_id");

  const ip = request.headers.get("CF-Connecting-IP") ?? "unknown";
  if (await isRateLimited(env, ip)) {
    throw new HttpError(429, "Too many requests. Please wait a moment before trying again.");
  }

  const traceId = crypto.randomUUID();
  const timestamp = utcStamp();
  const t0 = Date.now();

  let retrievalError: string | null = null;
  let sopChunks: SopChunk[];
  try {
    sopChunks = searchSop(userInput, 3);
  } catch (e) {
    retrievalError = `Retrieval failed: ${e instanceof Error ? `${e.name}: ${e.message}` : e}`;
    sopChunks = [];
  }

  const [assessment, traceMeta] = await assessDeviationTraced(env, userInput, sopChunks);
  const latencyMs = Date.now() - t0;

  try {
    await env.DB.prepare(
      `INSERT INTO traces (id, timestamp, user_input, retrieved_chunks, prompt_version,
                           model_output, latency_ms, input_tokens, output_tokens, error)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    ).bind(
      traceId, timestamp, userInput,
      dumps(sopChunks.map((c) => c.chunk_id).filter(Boolean)),
      PROMPT_VERSION, traceMeta.model_output_raw || null, latencyMs,
      traceMeta.input_tokens, traceMeta.output_tokens, traceMeta.error ?? retrievalError,
    ).run();
  } catch (e) {
    // Tracing must never break a live review request.
    console.error(`[tracer] WARNING: failed to log trace ${traceId}: ${e}`);
  }

  // AgentOps + LangSmith pushes run after the response is sent.
  ctx.waitUntil((async () => {
    await pushTrace(env, {
      trace_id: traceId, timestamp, user_input: userInput, assessment,
      input_tokens: traceMeta.input_tokens, output_tokens: traceMeta.output_tokens,
      latency_ms: latencyMs, is_fallback: traceMeta.is_fallback,
    });
    await pushDailyCost(env);
  })());
  const end = new Date();
  ctx.waitUntil(pushLangSmithRun(env, {
    inputs: { user_input: userInput, case_id: caseId },
    outputs: { assessment },
    start: new Date(end.getTime() - latencyMs),
    end,
    metadata: {
      trace_id: traceId, prompt_version: PROMPT_VERSION, latency_ms: latencyMs,
      input_tokens: traceMeta.input_tokens, output_tokens: traceMeta.output_tokens,
      is_fallback: traceMeta.is_fallback,
    },
  }));

  const field = (k: string) => (k in assessment ? assessment[k] : SAFE_FALLBACK[k]);
  return json({
    classification: field("classification"),
    severity: field("severity"),
    impact: field("impact"),
    immediate_action: field("immediate_action"),
    qa_escalation: field("qa_escalation"),
    missing_info: field("missing_info"),
    draft_summary: field("draft_summary"),
    retrieved_sources: sopChunks.map((c) => ({
      chunk_id: c.chunk_id ?? null,
      section_title: c.section_title ?? null,
      source_file: c.source_file ?? null,
      score: c.score ?? null,
      text_excerpt: [...(c.text ?? "")].slice(0, 300).join("").trim(),
    })),
    trace_id: traceId,
    case_id: caseId,
    latency_ms: latencyMs,
    is_fallback: traceMeta.is_fallback,
  });
}

// ─────────────────────────────────────────────────────────────────────────────
//  Traces, feedback, dashboard
// ─────────────────────────────────────────────────────────────────────────────

async function listTraces(env: Env): Promise<Response> {
  const { results } = await env.DB.prepare(
    `SELECT id AS trace_id, timestamp, user_input, retrieved_chunks, prompt_version,
            model_output, latency_ms, input_tokens, output_tokens, error
     FROM traces ORDER BY timestamp DESC LIMIT ?`,
  ).bind(20).all();
  return json({ count: results.length, traces: results });
}

async function submitFeedback(request: Request, env: Env): Promise<Response> {
  const body = await readJson(request);
  const traceId = strField(body, "trace_id", { required: true })!;
  const rating = intField(body, "rating");
  const comment = strField(body, "comment", { max: 2000 });
  const correction = strField(body, "reviewer_correction", { max: 4000 });

  if (rating !== 1 && rating !== -1) throw new HttpError(400, "rating must be 1 (thumbs up) or -1 (thumbs down).");

  const exists = await env.DB.prepare("SELECT id FROM traces WHERE id = ?").bind(traceId).first();
  if (!exists) {
    throw new HttpError(404, `trace_id '${traceId}' not found. Submit a deviation review first.`);
  }
  const feedbackId = crypto.randomUUID();
  await env.DB.prepare(
    `INSERT INTO feedback (id, trace_id, rating, comment, reviewer_correction, created_at)
     VALUES (?, ?, ?, ?, ?, ?)`,
  ).bind(feedbackId, traceId, rating, comment ? comment.trim() : null, correction ? correction.trim() : null, utcStamp()).run();

  return json({
    feedback_id: feedbackId,
    trace_id: traceId,
    rating,
    has_correction: Boolean(correction),
    message: "Feedback recorded. Thank you.",
  });
}

async function listFeedback(url: URL, env: Env): Promise<Response> {
  const limit = queryInt(url, "limit", 50, 1, 500);
  const { results } = await env.DB.prepare(
    `SELECT f.id AS feedback_id, f.trace_id, f.rating, f.comment, f.reviewer_correction, f.created_at,
            t.user_input AS user_input, t.timestamp AS review_timestamp
     FROM feedback f LEFT JOIN traces t ON t.id = f.trace_id
     ORDER BY f.created_at DESC LIMIT ?`,
  ).bind(limit).all();
  return json({ count: results.length, feedback: results });
}

async function dashboardMetrics(env: Env): Promise<Response> {
  const today = new Date();
  const window = new Map<string, number>();
  for (let i = 6; i >= 0; i--) window.set(new Date(today.getTime() - i * 86_400_000).toISOString().slice(0, 10), 0);
  const cutoff = [...window.keys()][0];

  const [total, agg, outputs, fb, daily] = await env.DB.batch([
    env.DB.prepare("SELECT COUNT(*) AS n FROM traces"),
    env.DB.prepare(
      `SELECT AVG(CASE WHEN latency_ms IS NOT NULL THEN latency_ms END) AS avg_lat,
              SUM(COALESCE(input_tokens, 0)) AS in_tok, SUM(COALESCE(output_tokens, 0)) AS out_tok
       FROM traces`,
    ),
    env.DB.prepare("SELECT model_output FROM traces WHERE model_output IS NOT NULL"),
    env.DB.prepare("SELECT COUNT(*) AS total, SUM(CASE WHEN rating = -1 THEN 1 ELSE 0 END) AS downvotes FROM feedback"),
    env.DB.prepare(
      `SELECT SUBSTR(timestamp, 1, 10) AS day, COUNT(*) AS cnt FROM traces
       WHERE timestamp >= ? GROUP BY day ORDER BY day`,
    ).bind(cutoff),
  ]);

  const totalChats = Number(total.results[0]?.n ?? 0);
  const a = agg.results[0] ?? {};
  const inTok = Number(a.in_tok ?? 0);
  const outTok = Number(a.out_tok ?? 0);

  let escalations = 0;
  const severities = new Map<string, number>();
  for (const { model_output } of outputs.results) {
    let assessment: Row = {};
    try {
      const parsed = JSON.parse(model_output);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) assessment = parsed;
    } catch { /* unparseable output counts as empty */ }
    if (assessment.qa_escalation === true) escalations++;
    if (assessment.severity) severities.set(assessment.severity, (severities.get(assessment.severity) ?? 0) + 1);
  }
  const order: Record<string, number> = { High: 0, Medium: 1, Low: 2 };
  const breakdown = [...severities.entries()]
    .sort((x, y) => (order[x[0]] ?? 99) - (order[y[0]] ?? 99) || y[1] - x[1])
    .map(([severity, count]) => ({ severity, count }));

  const totalFb = Number(fb.results[0]?.total ?? 0);
  const downvotes = Number(fb.results[0]?.downvotes ?? 0);
  for (const r of daily.results) if (window.has(r.day)) window.set(r.day, Number(r.cnt));

  return json({
    total_chats: totalChats,
    escalation_rate: pyRound(totalChats > 0 ? (escalations / totalChats) * 100 : 0, 1),
    avg_latency_ms: pyRound(Number(a.avg_lat ?? 0), 1),
    total_tokens_used: inTok + outTok,
    estimated_cost_usd: pyRound(inTok * INPUT_PRICE + outTok * OUTPUT_PRICE, 6),
    downvote_rate: pyRound(totalFb > 0 ? (downvotes / totalFb) * 100 : 0, 1),
    top_severity_breakdown: breakdown,
    chats_last_7_days: [...window.entries()].map(([date, count]) => ({ date, count })),
  });
}

// ─────────────────────────────────────────────────────────────────────────────
//  Evals (one case per request)
// ─────────────────────────────────────────────────────────────────────────────

async function startEvalRun(request: Request, env: Env): Promise<Response> {
  requireEvalToken(request, env);
  const runId = crypto.randomUUID();
  const createdAt = utcStamp();
  await env.DB.prepare("INSERT INTO eval_runs (run_id, created_at, started_ms) VALUES (?, ?, ?)")
    .bind(runId, createdAt, Date.now()).run();
  return json({ run_id: runId, created_at: createdAt, case_ids: EVAL_CASES.map((c) => c.case_id) });
}

async function evalRunCase(request: Request, env: Env, runId: string, caseId: string): Promise<Response> {
  requireEvalToken(request, env);
  const run = await env.DB.prepare("SELECT * FROM eval_runs WHERE run_id = ?").bind(runId).first();
  if (!run) throw new HttpError(404, `Eval run '${runId}' not found`);
  const c = EVAL_CASES.find((x) => x.case_id === caseId);
  if (!c) throw new HttpError(404, `Eval case '${caseId}' not found`);

  const rows = [
    await evalCase(env, c, runId, "actual", run.created_at),
    await evalCase(env, c, runId, "baseline_always_escalate", run.created_at),
  ];
  // Re-running a case replaces its rows, so a retried request never double-counts.
  await env.DB.batch([
    env.DB.prepare("DELETE FROM eval_results WHERE run_id = ? AND case_id = ?").bind(runId, caseId),
    ...rows.map((r) => env.DB.prepare(
      `INSERT INTO eval_results (id, case_id, run_id, model_tag, groundedness, classification,
                                 escalation, clarity, overall_pass, notes, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    ).bind(crypto.randomUUID(), r.case_id, r.run_id, r.model_tag, r.groundedness, r.classification,
      r.escalation, r.clarity, r.overall_pass, r.notes, r.created_at)),
  ]);
  return json({ case_id: caseId, results: rows });
}

async function finishEvalRun(request: Request, env: Env, runId: string): Promise<Response> {
  requireEvalToken(request, env);
  const run = await env.DB.prepare("SELECT * FROM eval_runs WHERE run_id = ?").bind(runId).first();
  if (!run) throw new HttpError(404, `Eval run '${runId}' not found`);
  const { results } = await env.DB.prepare("SELECT * FROM eval_results WHERE run_id = ?").bind(runId).all();
  const summary: Row = {
    run_id: runId,
    actual: computeSummary(results.filter((r) => r.model_tag === "actual") as any[]),
    baseline: computeSummary(results.filter((r) => r.model_tag === "baseline_always_escalate") as any[]),
    duration_s: pyRound((Date.now() - Number(run.started_ms)) / 1000, 1),
    total_rows: results.length,
  };
  // Push results to AgentOps (errors are logged, not raised)
  await pushEvalResults(env, summary);
  return json({
    run_id: summary.run_id,
    duration_s: summary.duration_s,
    total_rows: summary.total_rows,
    actual: summary.actual,
    baseline: summary.baseline,
  });
}

// ─────────────────────────────────────────────────────────────────────────────
//  Router
// ─────────────────────────────────────────────────────────────────────────────

type Handler = (request: Request, env: Env, ctx: Ctx, url: URL, params: string[]) => Promise<Response>;

const ROUTES: [string, RegExp, Handler][] = [
  ["GET", /^\/(?:api\/)?health$/, async () =>
    json({ status: "ok", service: "SOP Deviation Review Assistant", version: "1.0.0" })],
  ["POST", /^\/api\/review$/, (req, env, ctx) => review(req, env, ctx)],
  ["GET", /^\/api\/traces$/, (_req, env) => listTraces(env)],
  ["POST", /^\/api\/feedback$/, (req, env) => submitFeedback(req, env)],
  ["GET", /^\/api\/feedback$/, (_req, env, _ctx, url) => listFeedback(url, env)],
  ["GET", /^\/api\/dashboard\/metrics$/, (_req, env) => dashboardMetrics(env)],
  ["POST", /^\/api\/evals\/runs$/, (req, env) => startEvalRun(req, env)],
  ["POST", /^\/api\/evals\/runs\/([^/]+)\/cases\/([^/]+)$/, (req, env, _ctx, _url, p) => evalRunCase(req, env, p[0], p[1])],
  ["POST", /^\/api\/evals\/runs\/([^/]+)\/finish$/, (req, env, _ctx, _url, p) => finishEvalRun(req, env, p[0])],
  ["POST", /^\/api\/evals\/run$/, async () => {
    throw new HttpError(410,
      "Eval runs now go one case at a time: POST /api/evals/runs, then /api/evals/runs/{run_id}/cases/{case_id} " +
      "for each case, then /api/evals/runs/{run_id}/finish.");
  }],
  ["GET", /^\/api\/evals\/results$/, async (_req, env, _ctx, url) =>
    json(await fetchResults(env, url.searchParams.get("run_id")))],
  ["POST", /^\/api\/agentops\/sync$/, async (_req, env) => json(await fullSync(env))],
];

export default {
  async fetch(request: Request, env: Env, ctx: Ctx): Promise<Response> {
    const cors = corsHeaders(request);
    if (request.method === "OPTIONS") return new Response(null, { status: 200, headers: cors });

    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";
    let response: Response | null = null;
    let pathMatched = false;
    for (const [method, pattern, handler] of ROUTES) {
      const m = path.match(pattern);
      if (!m) continue;
      pathMatched = true;
      if (method !== request.method) continue;
      try {
        response = await handler(request, env, ctx, url, m.slice(1).map(decodeURIComponent));
      } catch (e) {
        if (e instanceof HttpError) response = json({ detail: e.detail }, e.status);
        else {
          console.error(e);
          response = json({ detail: "Internal Server Error" }, 500);
        }
      }
      break;
    }
    response ??= json({ detail: pathMatched ? "Method Not Allowed" : "Not Found" }, pathMatched ? 405 : 404);
    for (const [k, v] of Object.entries(cors)) response.headers.set(k, v);
    return response;
  },
};
