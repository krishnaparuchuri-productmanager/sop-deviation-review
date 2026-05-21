/**
 * client.js — All fetch calls to the FastAPI backend.
 *
 * The Vite dev-server proxies /api/* to http://localhost:8001, so we use
 * relative paths here. In production, point VITE_API_BASE_URL at the real
 * backend origin.
 */

const BASE = import.meta.env.VITE_API_BASE_URL ?? ''

// Eval token — set VITE_EVAL_TOKEN in your .env.local (never commit this value).
// The backend checks this against the EVAL_SECRET_TOKEN env var on Railway.
const EVAL_TOKEN = import.meta.env.VITE_EVAL_TOKEN ?? ''

/**
 * POST /api/review
 *
 * @param {string} userInput  - The deviation description text.
 * @param {string|null} caseId - Optional case ID for trace correlation.
 * @returns {Promise<object>}  - The ReviewResponse JSON on success.
 * @throws {Error}             - With a human-readable message on failure.
 */
export async function postReview(userInput, caseId = null) {
  const body = { user_input: userInput }
  if (caseId) body.case_id = caseId

  const res = await fetch(`${BASE}/api/review`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(body),
  })

  if (!res.ok) {
    // Try to surface the FastAPI error detail
    let detail = `HTTP ${res.status}`
    try {
      const err = await res.json()
      detail = err?.detail ?? JSON.stringify(err)
    } catch (_) { /* ignore */ }
    throw new Error(detail)
  }

  return res.json()
}

/**
 * GET /api/dashboard/metrics
 *
 * @returns {Promise<object>} - DashboardMetrics {
 *   total_chats, escalation_rate, avg_latency_ms, total_tokens_used,
 *   estimated_cost_usd, downvote_rate, top_severity_breakdown[], chats_last_7_days[]
 * }
 */
export async function getDashboardMetrics() {
  const res = await fetch(`${BASE}/api/dashboard/metrics`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

/**
 * GET /api/traces
 *
 * @param {number} limit - Max traces to return (default 20).
 * @returns {Promise<object>} - TracesResponse { count, traces[] }
 */
export async function getTraces(limit = 20) {
  const res = await fetch(`${BASE}/api/traces?limit=${limit}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

/**
 * POST /api/evals/run
 *
 * Triggers a full evaluation run. Takes 3–6 minutes to complete.
 * @returns {Promise<object>} - EvalRunResponse {
 *   run_id, duration_s, total_rows,
 *   actual: DimensionSummary, baseline: DimensionSummary
 * }
 */
export async function runEvals() {
  const res = await fetch(`${BASE}/api/evals/run`, {
    method: 'POST',
    headers: { 'X-Eval-Token': EVAL_TOKEN },
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const err = await res.json()
      detail = err?.detail ?? JSON.stringify(err)
    } catch (_) { /* ignore */ }
    throw new Error(detail)
  }
  return res.json()
}

/**
 * GET /api/evals/results
 *
 * @param {string|null} runId - Specific run UUID; omit for latest run.
 * @returns {Promise<object>} - EvalResultsResponse {
 *   run_id, available_runs[], actual_summary, baseline_summary, results[]
 * }
 */
export async function getEvalsResults(runId = null) {
  const url = runId
    ? `${BASE}/api/evals/results?run_id=${encodeURIComponent(runId)}`
    : `${BASE}/api/evals/results`
  const res = await fetch(url)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

/**
 * GET /api/feedback
 *
 * @param {number} limit - Max records to return (default 50).
 * @returns {Promise<object>} - FeedbackListResponse { count, feedback[] }
 *   Each item: feedback_id, trace_id, rating, comment, reviewer_correction,
 *              created_at, user_input, review_timestamp
 */
export async function getFeedback(limit = 50) {
  const res = await fetch(`${BASE}/api/feedback?limit=${limit}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

/**
 * POST /api/feedback
 *
 * @param {string}      traceId            - UUID of the review trace to rate.
 * @param {1|-1}        rating             - 1 = thumbs up, -1 = thumbs down.
 * @param {string|null} comment            - Optional reviewer note.
 * @param {string|null} reviewerCorrection - Optional corrected assessment (thumbs down only).
 * @returns {Promise<object>} - FeedbackResponse { feedback_id, trace_id, rating, has_correction, message }
 * @throws {Error}            - With a human-readable message on failure.
 */
export async function postFeedback(traceId, rating, comment = null, reviewerCorrection = null) {
  const body = { trace_id: traceId, rating }
  if (comment?.trim())            body.comment             = comment.trim()
  if (reviewerCorrection?.trim()) body.reviewer_correction = reviewerCorrection.trim()

  const res = await fetch(`${BASE}/api/feedback`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(body),
  })

  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const err = await res.json()
      detail = err?.detail ?? JSON.stringify(err)
    } catch (_) { /* ignore */ }
    throw new Error(detail)
  }

  return res.json()
}
