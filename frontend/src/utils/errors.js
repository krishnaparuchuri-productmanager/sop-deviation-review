/**
 * errors.js — Shared error-message humaniser for all API calls.
 *
 * Converts raw browser / HTTP error strings into user-facing messages
 * that contain no implementation details (stack traces, status codes,
 * or internal field names).
 *
 * Usage:
 *   import { friendlyError } from '../utils/errors.js'
 *   setError(friendlyError(err.message))
 */

/**
 * Map a raw error string to a friendly, one-sentence user message.
 *
 * @param {unknown} raw  - The caught error: Error object, string, or anything else.
 * @returns {string}     - A sentence suitable for display in a UI banner.
 */
export function friendlyError(raw) {
  // Normalise to a lower-case string for pattern matching
  const msg = raw instanceof Error
    ? raw.message
    : typeof raw === 'string'
    ? raw
    : String(raw ?? '')

  const lower = msg.toLowerCase()

  // ── Network / connectivity ─────────────────────────────────────────────────
  if (
    lower.includes('failed to fetch') ||
    lower.includes('networkerror') ||
    lower.includes('network request failed') ||
    lower.includes('load failed')           // Safari
  ) {
    return 'Unable to reach the service. Check your network connection and try again.'
  }

  if (lower.includes('timeout') || lower.includes('timed out')) {
    return 'The request timed out. The server may be busy — please try again.'
  }

  if (lower.includes('aborted') || lower.includes('abort')) {
    return 'The request was cancelled. Please try again.'
  }

  // ── HTTP 5xx server errors ─────────────────────────────────────────────────
  if (lower.includes('http 500') || lower.includes('500 internal')) {
    return 'The server encountered an unexpected error. Please try again in a moment.'
  }
  if (lower.includes('http 502') || lower.includes('http 503') || lower.includes('http 504')) {
    return 'The service is temporarily unavailable. Please try again shortly.'
  }

  // ── HTTP 4xx client errors ─────────────────────────────────────────────────
  if (lower.includes('http 404')) {
    return 'The requested data was not found.'
  }
  if (lower.includes('http 400') || lower.includes('http 422')) {
    return 'The request could not be processed. Please check your input and try again.'
  }
  if (lower.includes('http 401') || lower.includes('http 403')) {
    return 'You do not have permission to perform this action.'
  }
  if (lower.match(/http [45]\d\d/)) {
    return 'A server error occurred. Please try again.'
  }

  // ── Eval-runner specific ───────────────────────────────────────────────────
  if (lower.includes('eval run failed')) {
    return 'The evaluation run failed on the server. Check that the backend is running and try again.'
  }

  // ── Already-friendly messages (from FastAPI `detail` fields) ──────────────
  // FastAPI returns human-readable detail strings — pass them through as-is
  // if they contain no raw Python/HTTP internals.
  if (msg.length > 0 && msg.length < 200 && !lower.includes('traceback') && !lower.includes('exception')) {
    return msg
  }

  // ── Fallback ───────────────────────────────────────────────────────────────
  return 'Something went wrong. Please try again.'
}
