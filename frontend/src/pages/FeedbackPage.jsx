/**
 * FeedbackPage.jsx — Feedback Queue: list of all reviewer ratings.
 *
 * Layout:
 *   • Header    : page title + Refresh button
 *   • Stats row : Total ratings, Thumbs-up %, Thumbs-down %
 *   • List      : One card per feedback item (newest first)
 *                 Each card shows rating badge, deviation excerpt, comment,
 *                 and (if present) the reviewer's suggested correction.
 *
 * Data source: GET /api/feedback (joined with traces for the deviation text)
 *
 * States:
 *   Loading — skeleton cards
 *   Error   — friendly banner with Retry
 *   Empty   — "No feedback yet" with CTA to /chat
 *   Data    — the card list
 */

import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { getFeedback } from '../api/client.js'
import { friendlyError } from '../utils/errors.js'


// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

/** Format an ISO-8601 UTC timestamp as a relative label ("2 hours ago") or absolute date. */
function relativeTime(iso) {
  if (!iso) return '—'
  try {
    const dt      = new Date(iso)
    const diffMs  = Date.now() - dt.getTime()
    const diffMin = Math.floor(diffMs / 60_000)
    if (diffMin < 1)   return 'just now'
    if (diffMin < 60)  return `${diffMin}m ago`
    const diffH = Math.floor(diffMin / 60)
    if (diffH < 24)    return `${diffH}h ago`
    const diffD = Math.floor(diffH / 24)
    if (diffD < 7)     return `${diffD}d ago`
    return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
  } catch {
    return iso
  }
}

/** Truncate a string to `max` characters, appending an ellipsis if needed. */
function truncate(text, max = 160) {
  if (!text) return ''
  return text.length <= max ? text : text.slice(0, max).trimEnd() + '…'
}


// ─────────────────────────────────────────────────────────────────────────────
// Icons
// ─────────────────────────────────────────────────────────────────────────────

const IconThumbUp = ({ filled }) => (
  <svg className="w-4 h-4" fill={filled ? 'currentColor' : 'none'}
       viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" aria-hidden="true">
    <path strokeLinecap="round" strokeLinejoin="round"
      d="M6.633 10.25c.806 0 1.533-.446 2.031-1.08a9.041 9.041 0 0 1 2.861-2.4c.723-.384
         1.35-.956 1.653-1.715a4.498 4.498 0 0 0 .322-1.672V2.75a.75.75 0 0 1 .75-.75
         2.25 2.25 0 0 1 2.25 2.25c0 1.152-.26 2.243-.723 3.218-.266.558.107 1.282.725
         1.282m0 0h3.126c1.026 0 1.945.694 2.054 1.715.045.422.068.85.068 1.285a11.95
         11.95 0 0 1-2.649 7.521c-.388.482-.987.729-1.605.729H13.48c-.483 0-.964-.078
         -1.423-.23l-3.114-1.04a4.501 4.501 0 0 0-1.423-.23H5.904m10.598-9.75H14.25M5.904
         18.5c.083.205.173.405.27.602.197.4-.078.898-.523.898h-.908c-.889 0-1.713-.518
         -1.972-1.368a12 12 0 0 1-.521-3.507c0-1.553.295-3.036.831-4.398C3.387 9.953
         4.167 9.5 5 9.5h1.053c.472 0 .745.556.5.96a8.958 8.958 0 0 0-1.302 4.665c0
         1.194.232 2.333.654 3.375Z" />
  </svg>
)

const IconThumbDown = ({ filled }) => (
  <svg className="w-4 h-4" fill={filled ? 'currentColor' : 'none'}
       viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" aria-hidden="true">
    <path strokeLinecap="round" strokeLinejoin="round"
      d="M7.498 15.25H4.372c-1.026 0-1.945-.694-2.054-1.715a12.137 12.137 0 0 1-.068
         -1.285c0-2.848.992-5.464 2.649-7.521C5.287 4.247 5.886 4 6.504 4h4.016a4.5 4.5
         0 0 1 1.423.23l3.114 1.04a4.5 4.5 0 0 0 1.423.23h1.294M7.498 15.25c.618 0
         .991.724.725 1.282A7.471 7.471 0 0 0 7.5 19.75 2.25 2.25 0 0 0 9.75 22a.75.75
         0 0 0 .75-.75v-.633c0-.573.11-1.14.322-1.672.304-.76.93-1.33 1.653-1.715a9.04
         9.04 0 0 0 2.86-2.4c.498-.634 1.226-1.08 2.032-1.08h.384m-10.253 1.5H9.7
         m8.075-9.75c.01.05.027.1.05.148.593 1.2.925 2.55.925 3.977 0 1.487-.36 2.89
         -.999 4.125m.023-8.25c-.076-.365.183-.75.575-.75h.908c.889 0 1.713.518 1.972
         1.368.339 1.11.521 2.287.521 3.507 0 1.553-.295 3.036-.832 4.398-.306.774
         -1.086 1.227-1.918 1.227h-1.053c-.472 0-.745-.556-.499-.96a8.957 8.957 0 0 0
         1.302-4.665c0-1.194-.232-2.333-.654-3.375Z" />
  </svg>
)

const IconRefresh = () => (
  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round"
      d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0
         3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1
         13.803-3.7l3.181 3.182m0-4.991v4.99" />
  </svg>
)

const IconPencil = () => (
  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round"
      d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582
         16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1
         1.13-1.897l8.932-8.931Zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0 1
         15.75 21H5.25A2.25 2.25 0 0 1 3 18.75V8.25A2.25 2.25 0 0 1
         5.25 6H10" />
  </svg>
)


// ─────────────────────────────────────────────────────────────────────────────
// RatingBadge
// ─────────────────────────────────────────────────────────────────────────────

function RatingBadge({ rating }) {
  return rating === 1 ? (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs
                     font-semibold bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200">
      <IconThumbUp filled />
      Helpful
    </span>
  ) : (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs
                     font-semibold bg-red-50 text-red-700 ring-1 ring-red-200">
      <IconThumbDown filled />
      Not helpful
    </span>
  )
}


// ─────────────────────────────────────────────────────────────────────────────
// StatCard
// ─────────────────────────────────────────────────────────────────────────────

function StatCard({ value, label, accent }) {
  const palette = {
    slate:   'text-gray-700   bg-gray-50    border-gray-200',
    emerald: 'text-emerald-700 bg-emerald-50 border-emerald-200',
    red:     'text-red-700    bg-red-50     border-red-200',
  }
  return (
    <div className={`rounded-xl border p-5 flex flex-col gap-1 ${palette[accent] ?? palette.slate}`}>
      <p className="text-3xl font-extrabold tabular-nums leading-none">{value}</p>
      <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mt-1">{label}</p>
    </div>
  )
}


// ─────────────────────────────────────────────────────────────────────────────
// FeedbackCard — single feedback item
// ─────────────────────────────────────────────────────────────────────────────

function FeedbackCard({ item }) {
  const [correctionOpen, setCorrectionOpen] = useState(false)
  const isDown = item.rating === -1

  return (
    <article
      className={`rounded-xl border bg-white shadow-sm overflow-hidden transition-colors
                  ${isDown ? 'border-red-100' : 'border-gray-200'}`}
    >
      {/* Card header: rating badge + timestamp */}
      <div className={`flex items-center justify-between gap-3 px-5 py-3 border-b
                       ${isDown ? 'bg-red-50 border-red-100' : 'bg-gray-50 border-gray-100'}`}>
        <RatingBadge rating={item.rating} />
        <span className="text-xs text-gray-400 tabular-nums flex-shrink-0">
          {relativeTime(item.created_at)}
        </span>
      </div>

      <div className="px-5 py-4 space-y-3">
        {/* Deviation excerpt */}
        {item.user_input ? (
          <div>
            <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide mb-1">
              Deviation
            </p>
            <p className="text-sm text-gray-700 leading-relaxed">
              {truncate(item.user_input, 200)}
            </p>
          </div>
        ) : (
          <p className="text-xs text-gray-300 italic">Deviation text unavailable</p>
        )}

        {/* Reviewer comment */}
        {item.comment && (
          <div>
            <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide mb-1">
              Reviewer note
            </p>
            <p className="text-sm text-gray-600 italic leading-relaxed">
              "{item.comment}"
            </p>
          </div>
        )}

        {/* Reviewer correction — collapsible, only shown when rating = -1 */}
        {item.reviewer_correction && (
          <div>
            <button
              type="button"
              onClick={() => setCorrectionOpen(o => !o)}
              className="flex items-center gap-1.5 text-xs font-semibold text-red-600
                         hover:text-red-800 transition-colors"
            >
              <IconPencil />
              {correctionOpen ? 'Hide' : 'Show'} reviewer correction
              <svg
                className={`w-3 h-3 transition-transform ${correctionOpen ? 'rotate-180' : ''}`}
                fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor"
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
              </svg>
            </button>
            {correctionOpen && (
              <div className="mt-2 rounded-lg bg-red-50 border border-red-100 px-4 py-3">
                <p className="text-xs font-semibold text-red-500 uppercase tracking-wide mb-1.5">
                  Suggested correction
                </p>
                <p className="text-sm text-red-800 leading-relaxed whitespace-pre-wrap">
                  {item.reviewer_correction}
                </p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Footer: trace ID */}
      <div className="px-5 pb-3 flex items-center gap-3">
        <span className="text-[10px] text-gray-300 font-mono">
          trace {item.trace_id.slice(0, 8)}…
        </span>
      </div>
    </article>
  )
}


// ─────────────────────────────────────────────────────────────────────────────
// Skeleton — loading placeholder
// ─────────────────────────────────────────────────────────────────────────────

function FeedbackSkeleton() {
  return (
    <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden animate-pulse">
      <div className="flex items-center justify-between gap-3 px-5 py-3 border-b bg-gray-50 border-gray-100">
        <div className="h-5 w-20 bg-gray-200 rounded-full" />
        <div className="h-3 w-16 bg-gray-100 rounded" />
      </div>
      <div className="px-5 py-4 space-y-3">
        <div className="space-y-1.5">
          <div className="h-2.5 w-16 bg-gray-100 rounded" />
          <div className="h-3 w-full bg-gray-100 rounded" />
          <div className="h-3 w-5/6 bg-gray-100 rounded" />
          <div className="h-3 w-4/6 bg-gray-100 rounded" />
        </div>
      </div>
      <div className="px-5 pb-3">
        <div className="h-2 w-24 bg-gray-100 rounded" />
      </div>
    </div>
  )
}


// ─────────────────────────────────────────────────────────────────────────────
// FeedbackPage — main export
// ─────────────────────────────────────────────────────────────────────────────

export default function FeedbackPage() {
  const navigate = useNavigate()
  const [data,    setData]    = useState(null)   // FeedbackListResponse
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)
  const [fetchKey, setFetchKey] = useState(0)

  // ── Fetch feedback ──────────────────────────────────────────────────────────
  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await getFeedback(100)
      setData(res)
    } catch (e) {
      setError(friendlyError(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load, fetchKey])

  const refresh = () => setFetchKey(k => k + 1)

  // ── Derived stats ───────────────────────────────────────────────────────────
  const items     = data?.feedback ?? []
  const total     = items.length
  const upCount   = items.filter(i => i.rating === 1).length
  const downCount = items.filter(i => i.rating === -1).length
  const upPct     = total > 0 ? Math.round((upCount   / total) * 100) : 0
  const downPct   = total > 0 ? Math.round((downCount / total) * 100) : 0

  // Separate into downvotes (most useful for review) and upvotes
  const downItems = items.filter(i => i.rating === -1)
  const upItems   = items.filter(i => i.rating === 1)

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">

      {/* ── Page header ──────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Feedback Queue</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Reviewer ratings from the deviation review tool — use downvotes to identify
            cases where the model needs improvement.
          </p>
        </div>
        <button
          onClick={refresh}
          disabled={loading}
          className="inline-flex items-center gap-1.5 text-xs text-gray-500
                     hover:text-gray-800 px-3 py-1.5 rounded-lg border border-gray-200
                     hover:border-gray-300 bg-white transition-colors disabled:opacity-40"
        >
          <IconRefresh />
          Refresh
        </button>
      </div>

      {/* ── Error banner ─────────────────────────────────────────────────── */}
      {error && (
        <div role="alert"
             className="flex items-center gap-3 rounded-xl border border-red-200
                        bg-red-50 px-5 py-3 text-sm text-red-700">
          <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24"
               strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
          </svg>
          <span className="flex-1">{error}</span>
          <button onClick={refresh} className="underline font-semibold hover:text-red-900 flex-shrink-0">
            Retry
          </button>
        </div>
      )}

      {/* ── Stats row ────────────────────────────────────────────────────── */}
      {loading ? (
        <div className="grid grid-cols-3 gap-4 animate-pulse">
          {[0, 1, 2].map(i => (
            <div key={i} className="rounded-xl border border-gray-200 bg-white p-5 h-24" />
          ))}
        </div>
      ) : !error && (
        <div className="grid grid-cols-3 gap-4">
          <StatCard value={total}    label="Total ratings" accent="slate"   />
          <StatCard value={`${upPct}%`}   label="Thumbs up"     accent="emerald" />
          <StatCard value={`${downPct}%`} label="Thumbs down"   accent="red"     />
        </div>
      )}

      {/* ── Empty state ──────────────────────────────────────────────────── */}
      {!loading && !error && total === 0 && (
        <div className="rounded-xl border border-dashed border-gray-300 bg-gray-50
                        py-20 text-center">
          <svg className="mx-auto w-10 h-10 text-gray-300 mb-4" fill="none" viewBox="0 0 24 24"
               strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227
                 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133
                 a1.14 1.14 0 0 1 .865-.501 48.172 48.172 0 0 0 3.423-.379c1.584-.233
                 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394
                 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14
                 2.25 6.741v6.018Z" />
          </svg>
          <p className="text-sm font-semibold text-gray-500">No feedback yet</p>
          <p className="text-xs text-gray-400 mt-1 mb-6">
            Submit a deviation review, then rate the result with a thumbs-up or thumbs-down.
          </p>
          <button
            onClick={() => navigate('/chat')}
            className="inline-flex items-center gap-2 px-5 py-2 rounded-lg text-sm
                       font-semibold bg-indigo-600 hover:bg-indigo-700 text-white
                       shadow-sm active:scale-95 transition-all"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
            Review a deviation
          </button>
        </div>
      )}

      {/* ── Downvote section ─────────────────────────────────────────────── */}
      {!loading && !error && downItems.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-3">
            <span className="text-sm font-semibold text-gray-700">
              Needs review
            </span>
            <span className="inline-flex items-center justify-center px-2 py-0.5 rounded-full
                             bg-red-100 text-red-700 text-xs font-semibold">
              {downItems.length}
            </span>
            <span className="text-xs text-gray-400 ml-1">
              — cases where the reviewer disagreed with the assessment
            </span>
          </div>
          <div className="space-y-4">
            {downItems.map(item => (
              <FeedbackCard key={item.feedback_id} item={item} />
            ))}
          </div>
        </section>
      )}

      {/* ── Upvote section ───────────────────────────────────────────────── */}
      {!loading && !error && upItems.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-3">
            <span className="text-sm font-semibold text-gray-700">
              Positive ratings
            </span>
            <span className="inline-flex items-center justify-center px-2 py-0.5 rounded-full
                             bg-emerald-100 text-emerald-700 text-xs font-semibold">
              {upItems.length}
            </span>
          </div>
          <div className="space-y-4">
            {upItems.map(item => (
              <FeedbackCard key={item.feedback_id} item={item} />
            ))}
          </div>
        </section>
      )}

      {/* ── Loading skeletons ────────────────────────────────────────────── */}
      {loading && (
        <div className="space-y-4">
          {Array.from({ length: 5 }).map((_, i) => (
            <FeedbackSkeleton key={i} />
          ))}
        </div>
      )}

    </div>
  )
}
