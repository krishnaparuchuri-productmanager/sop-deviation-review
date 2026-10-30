/**
 * agentops.ts — Bridge to the AgentOps governance dashboard (port of
 * backend/agentops_push.py). Every call is best-effort: failures are logged and
 * swallowed so the review flow never depends on AgentOps being reachable.
 *
 * Talks to AgentOps through the AGENTOPS service binding when configured,
 * otherwise through AGENTOPS_API_URL; with neither, pushes are skipped.
 */

import { Env, Row } from "./util";

// Haiku pricing — must match the dashboard route
export const INPUT_PRICE = 0.80 / 1_000_000;
export const OUTPUT_PRICE = 4.00 / 1_000_000;

const agentId = (env: Env) => env.AGENTOPS_AGENT_ID || "gmp-deviation-review";
const configured = (env: Env) => Boolean(env.AGENTOPS || env.AGENTOPS_API_URL);

async function api(env: Env, method: string, path: string, body?: Row): Promise<Row | null> {
  if (!configured(env)) return null;
  const init: RequestInit = {
    method,
    headers: { "Content-Type": "application/json", "User-Agent": "sop-deviation-review/1.0" },
    body: body ? JSON.stringify(body) : undefined,
  };
  try {
    const res = env.AGENTOPS
      ? await env.AGENTOPS.fetch(`https://agentops/api${path}`, init)
      : await fetch(`${env.AGENTOPS_API_URL!.replace(/\/+$/, "")}${path}`, { ...init, signal: AbortSignal.timeout(10_000) });
    const text = await res.text();
    if (!res.ok) {
      console.warn(`AgentOps ${method} ${path} → HTTP ${res.status}: ${text.slice(0, 200)}`);
      return null;
    }
    return JSON.parse(text);
  } catch (e) {
    console.warn(`AgentOps ${method} ${path} → error: ${e}`);
    return null;
  }
}

// Registration only needs to happen once per isolate; AgentOps answers 400 if it exists.
let registered = false;

async function ensureAgentRegistered(env: Env): Promise<void> {
  if (registered || !configured(env)) return;
  await api(env, "POST", "/agents", {
    id: agentId(env),
    name: "GMP Deviation Review - AI Assistant",
    description:
      "Pharmaceutical GMP deviation-review assistant. Accepts a structured deviation " +
      "report, retrieves applicable SOPs via TF-IDF retrieval over 5 validated documents, " +
      "classifies deviation severity (Critical / Major / Minor), identifies the primary " +
      "applicable SOP and clause, proposes root cause hypothesis, recommends CAPA actions, " +
      "and escalates by default when evidence is ambiguous or a patient-impacting process " +
      "is involved. Built with Claude Haiku. Eval-gated before production.",
    owner: "Quality Assurance / Krishna Paruchuri",
    classification: {
      pii_access: false,
      production_critical: true,
      regulated_domain: true,
      data_classification: "confidential",
      escalates_to_human: true,
      product: "GMP Deviation Review",
      workflow: "Pharmaceutical QA Team Review",
      domain: "Pharmaceutical",
      environment: "production",
      model: "claude-haiku-4-5",
      eval_threshold: 0.75,
      guardrails: [
        "No patient data or PII in output — mask or reject if present in input",
        "Always escalate when evidence is ambiguous, conflicting, or missing",
        "Do not make regulatory submission decisions — flag for Regulatory Affairs",
        "Output must be structured JSON with all 7 required fields",
        "If SOP documents are not retrievable, return escalate_flag=true",
        "For Critical deviations: identify containment actions before CAPA",
        "Refuse Minor classification if a released batch or patient-impacting step is involved",
      ],
      golden_rules: [
        "Cite the applicable SOP by full document ID and clause (e.g. SOP-QA-042, Clause 5.3.1)",
        "State severity (Critical/Major/Minor) with explicit justification from the deviation report",
        "For Critical deviations, list containment actions as the first CAPA item",
        "Every CAPA must include: owner role, target date, effectiveness check criteria",
        "If root cause is unknown, state 'Root cause undetermined — investigation required'",
        "Flag Regulatory Affairs if deviation involves a released batch or validated process step",
        "Never recommend closing a deviation without a stated root cause or investigation plan",
      ],
    },
  });
  registered = true;
}

/** Push an eval run summary (shape of run_full_eval()'s return value). */
export async function pushEvalResults(env: Env, runSummary: Row): Promise<void> {
  await ensureAgentRegistered(env);
  if (!configured(env)) return;
  const actual = runSummary.actual ?? {};
  if (!Object.keys(actual).length) return;

  // GMP rubric is 4 dimensions × 0–2 = 0–8; AgentOps uses 0–10.
  const avgScore10 = Math.round((actual.avg_total_score ?? 0) * 10 / 8 * 100) / 100;
  const totalCases = actual.cases ?? 15;
  const passedCases = actual.pass_count ?? 0;
  const passRate = totalCases ? Math.round((passedCases / totalCases) * 1e4) / 1e4 : 0;
  const to10 = (v: number) => Math.round(v * 10 / 2 * 100) / 100;

  await api(env, "POST", `/agents/${agentId(env)}/evals`, {
    version: "1.0.0",
    run_by: "eval_runner (automated)",
    pass_rate: passRate,
    avg_score: avgScore10,
    total_cases: totalCases,
    passed_cases: passedCases,
    threshold_met: passRate >= 0.75,
    dimensions: {
      groundedness: to10(actual.avg_groundedness ?? 0),
      classification: to10(actual.avg_classification ?? 0),
      escalation: to10(actual.avg_escalation ?? 0),
      clarity: to10(actual.avg_clarity ?? 0),
      baseline_pass_rate: (runSummary.baseline?.pass_rate_pct ?? 0) / 100,
    },
  });
}

/** Push the day's token/cost totals, computed from the traces table (replaces the day). */
export async function pushDailyCost(env: Env, day?: string): Promise<void> {
  await ensureAgentRegistered(env);
  if (!configured(env)) return;
  const d = day ?? new Date().toISOString().slice(0, 10);
  const row = await env.DB.prepare(
    `SELECT COUNT(*) AS review_count,
            SUM(COALESCE(input_tokens, 0))  AS input_tokens,
            SUM(COALESCE(output_tokens, 0)) AS output_tokens
     FROM traces WHERE SUBSTR(timestamp, 1, 10) = ?`,
  ).bind(d).first();
  const reviewCount = Number(row?.review_count ?? 0);
  if (!reviewCount) return;
  const inputTokens = Number(row?.input_tokens ?? 0);
  const outputTokens = Number(row?.output_tokens ?? 0);
  await api(env, "POST", `/agents/${agentId(env)}/costs`, {
    recorded_date: d,
    total_tokens: inputTokens + outputTokens,
    input_tokens: inputTokens,
    output_tokens: outputTokens,
    cost_usd: Math.round((inputTokens * INPUT_PRICE + outputTokens * OUTPUT_PRICE) * 1e6) / 1e6,
    review_count: reviewCount,
  });
}

/** Push one /api/review execution trace. */
export async function pushTrace(env: Env, t: {
  trace_id: string; timestamp: string; user_input: string; assessment: Row;
  input_tokens: number; output_tokens: number; latency_ms: number; is_fallback: boolean;
}): Promise<void> {
  await ensureAgentRegistered(env);
  if (!configured(env)) return;
  await api(env, "POST", `/agents/${agentId(env)}/traces`, {
    trace_id: t.trace_id,
    timestamp: t.timestamp,
    user_input: t.user_input,
    severity: t.assessment.severity ?? null,
    qa_escalation: Boolean(t.assessment.qa_escalation ?? false),
    classification: t.assessment.classification ?? null,
    input_tokens: t.input_tokens,
    output_tokens: t.output_tokens,
    cost_usd: Math.round((t.input_tokens * INPUT_PRICE + t.output_tokens * OUTPUT_PRICE) * 1e6) / 1e6,
    latency_ms: t.latency_ms,
    is_fallback: t.is_fallback,
    model_output: null,
    source_app: "sop-deviation-review",
  });
}

/** POST /api/agentops/sync — daily cost records for the last 7 days. */
export async function fullSync(env: Env): Promise<Row> {
  await ensureAgentRegistered(env);
  const pushed: string[] = [];
  const today = new Date();
  for (let daysAgo = 0; daysAgo < 7; daysAgo++) {
    const d = new Date(today.getTime() - daysAgo * 86_400_000).toISOString().slice(0, 10);
    await pushDailyCost(env, d);
    pushed.push(d);
  }
  return {
    agent_id: agentId(env),
    synced_dates: pushed,
    agentops_url: env.AGENTOPS ? "service binding: agentops" : env.AGENTOPS_API_URL || "(not configured)",
    timestamp: new Date().toISOString(),
  };
}
