/**
 * evals.ts — LLM-as-judge evaluation (port of backend/eval_runner.py and the
 * results half of routes/evals.py).
 *
 * The Python endpoint ran all 15 cases in one 3–6 minute request. Here a run is
 * started, each case is scored in its own request (actual pipeline + always-escalate
 * baseline, both judged), and the run is then finished — same rows, same summary.
 */

import evalCases from "./data/eval_cases.json";
import { callHaiku, succeeded } from "./llm";
import { assessDeviation } from "./prompts";
import { searchSop } from "./retrieval";
import { Env, Row, pyRepr, pyRound } from "./util";

export interface EvalCase {
  case_id: string; scenario: string; area: string; type: string;
  severity_hint: string; expected_action: string; expected_output: string;
}
export const EVAL_CASES = evalCases as EvalCase[];

export const PASS_THRESHOLD = 6; // out of 8
const DIMENSIONS = ["groundedness", "classification", "escalation", "clarity"] as const;

const ALWAYS_ESCALATE_OUTPUT: Row = {
  classification: "Unknown",
  severity: "High",
  impact:
    "All deviations are treated as high-risk by this baseline. " +
    "No case-specific impact analysis has been performed.",
  immediate_action: "Escalate immediately to QA. Do not proceed without QA sign-off.",
  qa_escalation: true,
  missing_info: "All details require manual verification by a qualified QA person.",
  draft_summary:
    "This deviation has been automatically escalated to QA for manual review. " +
    "No risk-based assessment was performed. QA must review before any action is taken.",
};

const JUDGE_SYSTEM =
  "You are an expert evaluator of pharmaceutical GMP deviation review outputs. " +
  "Your task: compare an actual model response to a golden-reference expected output " +
  "and assign integer scores 0–2 for each of four rubric dimensions. " +
  "Be strict and consistent: award 2 only when the criterion is clearly met, " +
  "1 when partially met, and 0 when not met. " +
  "Call submit_eval_scores with your four scores and a brief explanation.";

const JUDGE_TOOL: Row = {
  name: "submit_eval_scores",
  description:
    "Submit numeric evaluation scores for a deviation review response " +
    "compared to the golden-set expected output.",
  input_schema: {
    type: "object",
    properties: {
      groundedness: {
        type: "integer",
        description:
          "Does the response cite only SOP sections, procedures, and document IDs " +
          "that appear explicitly in the supplied SOP context?\n" +
          "2 = fully grounded — no unsupported SOP citations\n" +
          "1 = mostly grounded — one or two minor unsupported claims\n" +
          "0 = hallucinated — cites SOP IDs, section numbers, or procedures " +
          "not present in the supplied context",
      },
      classification: {
        type: "integer",
        description:
          "Does the severity level match what the expected output indicates?\n" +
          "2 = exact match (e.g., both say High)\n" +
          "1 = one level off (e.g., Medium when High expected — borderline)\n" +
          "0 = clearly wrong (e.g., Low when High expected)",
      },
      escalation: {
        type: "integer",
        description:
          "Does the qa_escalation flag match the expected action, " +
          "and is the rationale sound?\n" +
          "2 = flag matches expected AND rationale clearly supports the recommended action\n" +
          "1 = flag matches expected but rationale is weak or incomplete\n" +
          "0 = flag does not match expected (e.g., true when false expected)",
      },
      clarity: {
        type: "integer",
        description:
          "Is the draft_summary clear, concise, and accurate?\n" +
          "2 = clear, factual, covers what happened + impact + recommended action\n" +
          "1 = adequate but missing some important details\n" +
          "0 = vague, inaccurate, or missing key information",
      },
      notes: { type: "string", description: "1–2 sentences explaining the key scoring decisions." },
    },
    required: ["groundedness", "classification", "escalation", "clarity", "notes"],
  },
};

// Python str(): strings as-is, everything else as repr (True, None, ...).
const pyStr = (v: unknown) => (typeof v === "string" ? v : pyRepr(v));

// Python int() on a JSON value; throws where Python would raise.
function pyInt(v: unknown): number {
  if (typeof v === "boolean") return v ? 1 : 0;
  if (typeof v === "number" && Number.isFinite(v)) return Math.trunc(v);
  if (typeof v === "string" && /^\s*[-+]?\d+\s*$/.test(v)) return parseInt(v, 10);
  throw new Error(`invalid literal for int(): ${pyRepr(v)}`);
}

const NEUTRAL = { groundedness: 1, classification: 1, escalation: 1, clarity: 1 };

async function scoreWithJudge(env: Env, c: EvalCase, actual: Row): Promise<[Record<string, number>, string]> {
  const get = (k: string) => pyStr(k in actual ? actual[k] : "N/A");
  const judgePrompt =
    `## Deviation Scenario\n${c.scenario}\n\n` +
    `## Expected Assessment (golden reference)\n${c.expected_output}\n\n` +
    "## Actual Model Response\n" +
    `Severity         : ${get("severity")}\n` +
    `Classification   : ${get("classification")}\n` +
    `QA Escalation    : ${get("qa_escalation")}\n` +
    `Impact           : ${get("impact")}\n` +
    `Immediate Action : ${get("immediate_action")}\n` +
    `Draft Summary    : ${get("draft_summary")}\n\n` +
    "Score the actual response on the four rubric dimensions by calling submit_eval_scores.";

  const response = await callHaiku(
    env, JUDGE_SYSTEM, judgePrompt, 400, [JUDGE_TOOL], { type: "tool", name: "submit_eval_scores" },
  );
  if (!succeeded(response)) return [{ ...NEUTRAL }, `Judge call failed: ${response.error}`];

  try {
    const raw = JSON.parse(response.text);
    if (typeof raw !== "object" || raw === null || Array.isArray(raw)) throw new Error("judge output is not an object");
    const scores: Record<string, number> = {};
    for (const dim of DIMENSIONS) scores[dim] = Math.max(0, Math.min(2, pyInt(dim in raw ? raw[dim] : 1)));
    return [scores, pyStr("notes" in raw ? raw.notes : "")];
  } catch (e) {
    return [{ ...NEUTRAL }, `Judge parse error: ${e instanceof Error ? e.message : e}`];
  }
}

export interface EvalResult {
  case_id: string; run_id: string; model_tag: string;
  groundedness: number; classification: number; escalation: number; clarity: number;
  overall_pass: number; notes: string; created_at: string;
}

/** Score one case for one model tag ("actual" runs retrieval + LLM; baseline is static). */
export async function evalCase(env: Env, c: EvalCase, runId: string, modelTag: string, createdAt: string): Promise<EvalResult> {
  let actual: Row;
  if (modelTag === "actual") {
    let chunks: ReturnType<typeof searchSop> = [];
    try { chunks = searchSop(c.scenario, 3); } catch { chunks = []; }
    actual = await assessDeviation(env, c.scenario, chunks);
  } else {
    actual = { ...ALWAYS_ESCALATE_OUTPUT };
  }
  const [scores, notes] = await scoreWithJudge(env, c, actual);
  const total = DIMENSIONS.reduce((s, d) => s + scores[d], 0);
  return {
    case_id: c.case_id, run_id: runId, model_tag: modelTag,
    groundedness: scores.groundedness, classification: scores.classification,
    escalation: scores.escalation, clarity: scores.clarity,
    overall_pass: total >= PASS_THRESHOLD ? 1 : 0, notes, created_at: createdAt,
  };
}

/** compute_summary(): metrics for a list of scored rows. */
export function computeSummary(results: Pick<EvalResult, (typeof DIMENSIONS)[number] | "overall_pass">[]): Row {
  const avg = (vals: number[]) => (vals.length ? pyRound(vals.reduce((a, b) => a + b, 0) / vals.length, 2) : 0);
  const totals = results.map((r) => r.groundedness + r.classification + r.escalation + r.clarity);
  const passCount = results.reduce((s, r) => s + r.overall_pass, 0);
  return {
    cases: results.length,
    pass_count: passCount,
    pass_rate_pct: results.length ? pyRound((passCount / results.length) * 100, 1) : 0,
    avg_total_score: avg(totals),
    avg_groundedness: avg(results.map((r) => r.groundedness)),
    avg_classification: avg(results.map((r) => r.classification)),
    avg_escalation: avg(results.map((r) => r.escalation)),
    avg_clarity: avg(results.map((r) => r.clarity)),
  };
}

/** GET /api/evals/results — rows and per-tag summaries for one run (latest by default). */
export async function fetchResults(env: Env, requestedRun: string | null): Promise<Row> {
  const runRows = await env.DB.prepare("SELECT DISTINCT run_id FROM eval_results ORDER BY created_at DESC").all();
  const availableRuns = runRows.results.map((r) => r.run_id as string);
  if (!availableRuns.length) {
    return { run_id: null, available_runs: [], actual_summary: null, baseline_summary: null, results: [] };
  }
  const targetRun = requestedRun && availableRuns.includes(requestedRun) ? requestedRun : availableRuns[0];
  const { results } = await env.DB.prepare(
    `SELECT id, case_id, run_id, model_tag,
            groundedness, classification, escalation, clarity,
            groundedness + classification + escalation + clarity AS total_score,
            overall_pass, notes, created_at
     FROM eval_results WHERE run_id = ?
     ORDER BY model_tag, case_id`,
  ).bind(targetRun).all();

  const actualRows = results.filter((r) => r.model_tag === "actual") as any[];
  const baselineRows = results.filter((r) => r.model_tag === "baseline_always_escalate") as any[];
  return {
    run_id: targetRun,
    available_runs: availableRuns,
    actual_summary: actualRows.length ? computeSummary(actualRows) : null,
    baseline_summary: baselineRows.length ? computeSummary(baselineRows) : null,
    results,
  };
}
