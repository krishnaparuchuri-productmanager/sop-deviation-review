/**
 * client.js — All fetch calls to the backend API.
 *
 * In production the API is served by the same Cloudflare Worker as this app,
 * so paths are relative. The Vite dev-server proxies /api/* to the local
 * backend. VITE_API_BASE_URL can still point at another origin if needed.
 */

const BASE = import.meta.env.VITE_API_BASE_URL ?? ''

// Eval token — set VITE_EVAL_TOKEN in your .env.local (never commit this value).
// The backend checks this against the EVAL_SECRET_TOKEN Worker secret.
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
      const raw = err?.detail
      // FastAPI 422 returns detail as an array of validation error objects
      if (Array.isArray(raw)) {
        detail = raw.map(d => d.msg ?? JSON.stringify(d)).join('; ')
      } else {
        detail = raw ?? JSON.stringify(err)
      }
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

async function evalPost(path) {
  const res = await fetch(`${BASE}/api/evals/runs${path}`, {
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
 * Run the full evaluation suite. Takes 3–6 minutes in total.
 *
 * The backend scores one case per request: POST /api/evals/runs starts a run,
 * POST /api/evals/runs/{run_id}/cases/{case_id} scores each case, and
 * POST /api/evals/runs/{run_id}/finish returns the summary.
 *
 * @param {(done: number, total: number) => void} onProgress - Called after each case.
 * @returns {Promise<object>} - EvalRunResponse {
 *   run_id, duration_s, total_rows,
 *   actual: DimensionSummary, baseline: DimensionSummary
 * }
 */
export async function runEvals(onProgress = () => {}) {
  const { run_id, case_ids } = await evalPost('')
  onProgress(0, case_ids.length)
  for (const [i, caseId] of case_ids.entries()) {
    await evalPost(`/${encodeURIComponent(run_id)}/cases/${encodeURIComponent(caseId)}`)
    onProgress(i + 1, case_ids.length)
  }
  return evalPost(`/${encodeURIComponent(run_id)}/finish`)
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
