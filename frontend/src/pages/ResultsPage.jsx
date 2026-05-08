import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import RiskBadge from '../components/RiskBadge.jsx'
import { postFeedback } from '../api/client.js'

// ─────────────────────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────────────────────

/** Labelled section card used for Impact, Immediate Action, Draft Summary, etc. */
function Section({ title, icon, children, accent = 'slate' }) {
  const headerMap = {
    slate:  'border-gray-200   bg-gray-50',
    indigo: 'border-indigo-100 bg-indigo-50',
    red:    'border-red-100    bg-red-50',
    amber:  'border-amber-100  bg-amber-50',
    green:  'border-green-100  bg-green-50',
    violet: 'border-violet-100 bg-violet-50',
  }
  const header = headerMap[accent] ?? headerMap.slate
  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden shadow-sm">
      <div className={`flex items-center gap-2 px-5 py-3 border-b ${header}`}>
        <span className="text-sm leading-none" aria-hidden="true">{icon}</span>
        <h2 className="text-sm font-semibold text-gray-700">{title}</h2>
      </div>
      <div className="px-5 py-4 text-sm text-gray-700 leading-relaxed">
        {children}
      </div>
    </div>
  )
}

/** Individual expandable SOP source card — each source has its own toggle. */
function SourceCard({ source, index }) {
  const [open, setOpen] = useState(false)
  const title    = source.section_title?.replace(/^#+\s*/, '') ?? `Source ${index + 1}`
  const chunkId  = source.chunk_id
  const file     = source.source_file
  const score    = source.score
  const excerpt  = source.text_excerpt

  return (
    <div className="rounded-lg border border-gray-200 bg-white overflow-hidden">
      {/* Card header — always visible, clickable */}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left
                   hover:bg-gray-50 transition-colors duration-150 focus:outline-none
                   focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-indigo-400"
      >
        <div className="flex items-center gap-2 min-w-0">
          {/* Relevance rank badge */}
          <span className="flex-shrink-0 w-5 h-5 rounded-full bg-indigo-100 text-indigo-600
                           text-[10px] font-bold flex items-center justify-center">
            {index + 1}
          </span>
          <div className="min-w-0">
            <p className="text-xs font-semibold text-gray-800 truncate">{title}</p>
            {file && (
              <p className="text-[10px] text-gray-400 font-mono truncate">{file}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3 flex-shrink-0">
          {chunkId && (
            <span className="hidden sm:inline text-[10px] font-mono text-indigo-500
                             bg-indigo-50 px-1.5 py-0.5 rounded">
              {chunkId}
            </span>
          )}
          {score != null && (
            <span className="text-[10px] text-gray-400 tabular-nums w-14 text-right">
              {(score * 100).toFixed(1)}%
            </span>
          )}
          <svg
            className={`w-4 h-4 text-gray-400 flex-shrink-0 transition-transform duration-200
                        ${open ? 'rotate-180' : ''}`}
            fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"
            aria-hidden="true"
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
          </svg>
        </div>
      </button>

      {/* Expanded body */}
      {open && excerpt && (
        <div className="px-4 pb-4 pt-1 border-t border-gray-100">
          <p className="text-xs text-gray-600 leading-relaxed whitespace-pre-wrap font-mono
                        bg-gray-50 rounded-lg px-3 py-2.5 border border-gray-100">
            {excerpt}
          </p>
        </div>
      )}
      {open && !excerpt && (
        <p className="px-4 pb-3 pt-1 text-xs text-gray-400 border-t border-gray-100">
          No excerpt available.
        </p>
      )}
    </div>
  )
}

/** Feedback widget — thumbs up/down, comment, reviewer correction, submit, confirmation. */
function FeedbackWidget({ traceId }) {
  // rating: null | 1 (thumbs up) | -1 (thumbs down)
  const [rating,             setRating]             = useState(null)
  const [comment,            setComment]            = useState('')
  const [reviewerCorrection, setReviewerCorrection] = useState('')
  const [loading,            setLoading]            = useState(false)
  const [submitted,          setSubmitted]          = useState(false)
  const [error,              setError]              = useState(null)

  if (!traceId) return null

  if (submitted) {
    return (
      <div className="rounded-xl border border-green-200 bg-green-50 px-5 py-5 text-center shadow-sm">
        <div className="mx-auto mb-3 w-10 h-10 rounded-full bg-green-100 flex items-center justify-center">
          <svg className="w-5 h-5 text-green-600" fill="none" viewBox="0 0 24 24"
               strokeWidth={2.5} stroke="currentColor" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
          </svg>
        </div>
        <p className="text-sm font-semibold text-green-800">Feedback submitted — thank you!</p>
        <p className="mt-1 text-xs text-green-600">
          Your rating helps improve future assessments.
        </p>
      </div>
    )
  }

  async function handleSubmit() {
    if (rating === null || loading) return
    setLoading(true)
    setError(null)
    try {
      await postFeedback(
        traceId,
        rating,
        comment || null,
        reviewerCorrection || null,
      )
      setSubmitted(true)
    } catch (err) {
      setError(err.message ?? 'Could not save feedback. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const ThumbUp = ({ active }) => (
    <svg className="w-4 h-4" fill={active ? 'currentColor' : 'none'}
         viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round"
        d="M6.633 10.25c.806 0 1.533-.446 2.031-1.08a9.041 9.041 0 0 1 2.861-2.4c.723-.384 1.35-.956 1.653-1.715a4.498 4.498 0 0 0 .322-1.672V2.75a.75.75 0 0 1 .75-.75 2.25 2.25 0 0 1 2.25 2.25c0 1.152-.26 2.243-.723 3.218-.266.558.107 1.282.725 1.282m0 0h3.126c1.026 0 1.945.694 2.054 1.715.045.422.068.85.068 1.285a11.95 11.95 0 0 1-2.649 7.521c-.388.482-.987.729-1.605.729H13.48c-.483 0-.964-.078-1.423-.23l-3.114-1.04a4.501 4.501 0 0 0-1.423-.23H5.904m10.598-9.75H14.25M5.904 18.5c.083.205.173.405.27.602.197.4-.078.898-.523.898h-.908c-.889 0-1.713-.518-1.972-1.368a12 12 0 0 1-.521-3.507c0-1.553.295-3.036.831-4.398C3.387 9.953 4.167 9.5 5 9.5h1.053c.472 0 .745.556.5.96a8.958 8.958 0 0 0-1.302 4.665c0 1.194.232 2.333.654 3.375Z" />
    </svg>
  )
  const ThumbDown = ({ active }) => (
    <svg className="w-4 h-4" fill={active ? 'currentColor' : 'none'}
         viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round"
        d="M7.498 15.25H4.372c-1.026 0-1.945-.694-2.054-1.715a12.137 12.137 0 0 1-.068-1.285c0-2.848.992-5.464 2.649-7.521C5.287 4.247 5.886 4 6.504 4h4.016a4.5 4.5 0 0 1 1.423.23l3.114 1.04a4.5 4.5 0 0 0 1.423.23h1.294M7.498 15.25c.618 0 .991.724.725 1.282A7.471 7.471 0 0 0 7.5 19.75 2.25 2.25 0 0 0 9.75 22a.75.75 0 0 0 .75-.75v-.633c0-.573.11-1.14.322-1.672.304-.76.93-1.33 1.653-1.715a9.04 9.04 0 0 0 2.86-2.4c.498-.634 1.226-1.08 2.032-1.08h.384m-10.253 1.5H9.7m8.075-9.75c.01.05.027.1.05.148.593 1.2.925 2.55.925 3.977 0 1.487-.36 2.89-.999 4.125m.023-8.25c-.076-.365.183-.75.575-.75h.908c.889 0 1.713.518 1.972 1.368.339 1.11.521 2.287.521 3.507 0 1.553-.295 3.036-.832 4.398-.306.774-1.086 1.227-1.918 1.227h-1.053c-.472 0-.745-.556-.499-.96a8.957 8.957 0 0 0 1.302-4.665c0-1.194-.232-2.333-.654-3.375Z" />
    </svg>
  )

  const thumbBtn = (value, label, Icon) => {
    const active  = rating === value
    const colours = active
      ? value === 1
        ? 'bg-green-100 border-green-400 text-green-700 ring-2 ring-green-300'
        : 'bg-red-100   border-red-400   text-red-700   ring-2 ring-red-300'
      : 'bg-white border-gray-300 text-gray-500 hover:border-gray-400 hover:bg-gray-50'
    return (
      <button
        type="button"
        onClick={() => { setRating(active ? null : value); setError(null) }}
        aria-pressed={active}
        aria-label={label}
        className={`flex items-center gap-2 px-5 py-2.5 rounded-lg border text-sm
                    font-medium transition-all duration-150 focus:outline-none
                    focus-visible:ring-2 focus-visible:ring-offset-2
                    focus-visible:ring-indigo-400 ${colours}`}
      >
        <Icon active={active} />
        {label}
      </button>
    )
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden shadow-sm">
      {/* Header */}
      <div className="flex items-center gap-2 px-5 py-3 border-b border-gray-100 bg-gray-50">
        <span className="text-sm" aria-hidden="true">💬</span>
        <h2 className="text-sm font-semibold text-gray-700">Was this assessment helpful?</h2>
      </div>

      <div className="px-5 py-5 space-y-4">
        {/* Thumb buttons — 1 = agree, -1 = disagree */}
        <div className="flex items-center gap-3">
          {thumbBtn( 1, 'Agree',    ThumbUp)}
          {thumbBtn(-1, 'Disagree', ThumbDown)}
        </div>

        {/* Comment — always visible */}
        <div>
          <label htmlFor="feedback-comment" className="block text-xs font-medium text-gray-500 mb-1.5">
            Optional note
          </label>
          <textarea
            id="feedback-comment"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder={
              rating === -1
                ? 'What was incorrect or missing? (optional)'
                : 'Any additional comments? (optional)'
            }
            rows={2}
            maxLength={2000}
            disabled={loading}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-700
                       placeholder-gray-400 resize-none focus:outline-none focus:ring-2
                       focus:ring-indigo-400 focus:border-transparent transition-colors
                       disabled:opacity-50 disabled:bg-gray-50"
          />
          <p className="mt-0.5 text-right text-[10px] text-gray-300 tabular-nums">
            {comment.length} / 2000
          </p>
        </div>

        {/* Reviewer correction — only shown when thumbs down */}
        {rating === -1 && (
          <div>
            <label htmlFor="feedback-correction"
                   className="block text-xs font-medium text-gray-500 mb-1.5">
              Suggested correction
              <span className="ml-1 font-normal text-gray-400">(optional)</span>
            </label>
            <textarea
              id="feedback-correction"
              value={reviewerCorrection}
              onChange={(e) => setReviewerCorrection(e.target.value)}
              placeholder="Paste or type the corrected assessment text here…"
              rows={4}
              maxLength={4000}
              disabled={loading}
              className="w-full rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm
                         text-gray-700 placeholder-gray-400 resize-none focus:outline-none
                         focus:ring-2 focus:ring-red-300 focus:border-transparent transition-colors
                         disabled:opacity-50 disabled:bg-gray-50"
            />
            <p className="mt-0.5 text-right text-[10px] text-gray-300 tabular-nums">
              {reviewerCorrection.length} / 4000
            </p>
          </div>
        )}

        {/* Error banner */}
        {error && (
          <div role="alert" className="flex items-center gap-2 rounded-lg bg-red-50
                                       border border-red-200 px-3 py-2 text-xs text-red-700">
            <svg className="w-3.5 h-3.5 flex-shrink-0" fill="none" viewBox="0 0 24 24"
                 strokeWidth={2} stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
            </svg>
            {error}
          </div>
        )}

        {/* Submit row */}
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-gray-400">
            {rating === 1  && '👍 Marked as helpful'}
            {rating === -1 && '👎 Marked as not helpful'}
            {rating === null && 'Select a rating to submit'}
          </p>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={rating === null || loading}
            className={`inline-flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold
                        transition-all duration-150 focus:outline-none focus:ring-2
                        focus:ring-offset-2 focus:ring-indigo-400
                        ${rating !== null && !loading
                          ? 'bg-indigo-600 text-white hover:bg-indigo-700 shadow-sm'
                          : 'bg-gray-100 text-gray-400 cursor-not-allowed'}`}
          >
            {loading ? (
              <>
                <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24"
                     aria-hidden="true">
                  <circle className="opacity-25" cx="12" cy="12" r="10"
                          stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor"
                        d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                </svg>
                Saving…
              </>
            ) : (
              'Submit Feedback'
            )}
          </button>
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// ResultsPage
// ─────────────────────────────────────────────────────────────────────────────

export default function ResultsPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { result, userInput } = location.state ?? {}

  // Guard: if navigated to directly without review state, redirect to chat
  if (!result) {
    return (
      <div className="max-w-xl mx-auto px-4 py-20 text-center">
        <div className="mx-auto mb-4 w-12 h-12 rounded-full bg-gray-100 flex items-center justify-center">
          <svg className="w-6 h-6 text-gray-400" fill="none" viewBox="0 0 24 24"
               strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 5.25h.008v.008H12v-.008Z" />
          </svg>
        </div>
        <p className="text-gray-500 mb-6 text-sm">No review data found. Please submit a deviation first.</p>
        <button
          onClick={() => navigate('/chat')}
          className="px-5 py-2.5 rounded-lg bg-indigo-600 text-white text-sm
                     font-semibold hover:bg-indigo-700 transition-colors"
        >
          Go to Chat
        </button>
      </div>
    )
  }

  // Guard: result exists but is malformed (e.g. backend returned an error object)
  const hasRequiredFields = result.severity || result.impact || result.immediate_action
  if (!hasRequiredFields) {
    return (
      <div className="max-w-xl mx-auto px-4 py-20 text-center">
        <div className="mx-auto mb-4 w-12 h-12 rounded-full bg-red-100 flex items-center justify-center">
          <svg className="w-6 h-6 text-red-500" fill="none" viewBox="0 0 24 24"
               strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0
                 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697
                 16.126ZM12 15.75h.007v.008H12v-.008Z" />
          </svg>
        </div>
        <p className="text-sm font-semibold text-gray-700 mb-1">
          The review result is incomplete
        </p>
        <p className="text-gray-500 mb-6 text-sm">
          The assessment could not be fully parsed. Please submit the deviation again.
        </p>
        <button
          onClick={() => navigate('/chat')}
          className="px-5 py-2.5 rounded-lg bg-indigo-600 text-white text-sm
                     font-semibold hover:bg-indigo-700 transition-colors"
        >
          Try again
        </button>
      </div>
    )
  }

  const isHigh   = result.severity === 'High'
  const isMedium = result.severity === 'Medium'
  const sources  = result.retrieved_sources ?? []
  const hasMissingInfo = result.missing_info &&
    result.missing_info.toLowerCase() !== 'none' &&
    result.missing_info.trim().length > 0

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-4">

      {/* ─── 1 + 2 · Header: back · classification badge · severity badge ──── */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <button
          onClick={() => navigate('/chat')}
          className="inline-flex items-center gap-1.5 text-sm text-gray-500
                     hover:text-gray-800 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24"
               strokeWidth={2} stroke="currentColor" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M10.5 19.5 3 12m0 0 7.5-7.5M3 12h18" />
          </svg>
          New review
        </button>

        <div className="flex items-center gap-2 flex-wrap">
          {/* ① Classification badge */}
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs
                           font-semibold bg-indigo-50 text-indigo-700 ring-1 ring-inset
                           ring-indigo-200">
            <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24"
                 strokeWidth={2} stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M9.568 3H5.25A2.25 2.25 0 0 0 3 5.25v4.318c0 .597.237 1.17.659 1.591l9.581 9.581c.699.699 1.78.872 2.607.33a18.095 18.095 0 0 0 5.223-5.223c.542-.827.369-1.908-.33-2.607L11.16 3.66A2.25 2.25 0 0 0 9.568 3Z" />
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M6 6h.008v.008H6V6Z" />
            </svg>
            {result.classification}
          </span>

          {/* ② Severity badge */}
          <RiskBadge severity={result.severity} />

          {result.is_fallback && (
            <span className="text-xs text-amber-700 bg-amber-50 ring-1 ring-amber-200
                             px-2 py-1 rounded-full font-semibold">
              Fallback response
            </span>
          )}
        </div>
      </div>

      {/* ─── ⑤ QA Escalation alert ───────────────────────────────────────── */}
      {result.qa_escalation ? (
        <div
          role="alert"
          className={`flex items-start gap-3 rounded-xl px-5 py-4 border
            ${isHigh
              ? 'bg-red-50   border-red-300'
              : isMedium
              ? 'bg-amber-50 border-amber-300'
              : 'bg-amber-50 border-amber-300'}`}
        >
          <div className={`mt-0.5 flex-shrink-0 w-9 h-9 rounded-full flex items-center justify-center
            ${isHigh ? 'bg-red-100' : 'bg-amber-100'}`}>
            <svg className={`w-5 h-5 ${isHigh ? 'text-red-600' : 'text-amber-600'}`}
                 fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
            </svg>
          </div>
          <div>
            <p className={`text-sm font-bold ${isHigh ? 'text-red-700' : 'text-amber-800'}`}>
              QA Review Required
            </p>
            <p className={`text-xs mt-0.5 leading-relaxed ${isHigh ? 'text-red-600' : 'text-amber-700'}`}>
              This deviation must be reviewed by a qualified QA person before the batch or
              process can proceed. Do not release until QA sign-off is obtained.
            </p>
          </div>
        </div>
      ) : (
        <div
          role="status"
          className="flex items-start gap-3 rounded-xl px-5 py-4 border bg-green-50 border-green-200"
        >
          <div className="mt-0.5 flex-shrink-0 w-9 h-9 rounded-full bg-green-100
                          flex items-center justify-center">
            <svg className="w-5 h-5 text-green-600" fill="none" viewBox="0 0 24 24"
                 strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
            </svg>
          </div>
          <div>
            <p className="text-sm font-bold text-green-700">No Immediate QA Escalation Required</p>
            <p className="text-xs mt-0.5 text-green-600 leading-relaxed">
              Document the deviation per standard procedure and log for routine QA review
              at the next scheduled cycle.
            </p>
          </div>
        </div>
      )}

      {/* ─── ③ Impact Assessment ─────────────────────────────────────────── */}
      <Section
        title="Impact Assessment"
        icon="⚠️"
        accent={isHigh ? 'red' : isMedium ? 'amber' : 'slate'}
      >
        {result.impact ?? (
          <span className="text-gray-400 italic">Impact assessment not available.</span>
        )}
      </Section>

      {/* ─── ④ Recommended Immediate Action ──────────────────────────────── */}
      <Section title="Recommended Immediate Action" icon="🛑" accent="indigo">
        <p className="whitespace-pre-wrap">
          {result.immediate_action ?? (
            <span className="text-gray-400 italic">No immediate action specified.</span>
          )}
        </p>
      </Section>

      {/* ─── ⑦ Draft Deviation Summary ───────────────────────────────────── */}
      <Section title="Draft Deviation Summary" icon="📝" accent="violet">
        {result.draft_summary ? (
          <>
            <p className="italic text-gray-600 leading-relaxed">{result.draft_summary}</p>
            <p className="mt-3 text-xs text-gray-400">
              This draft is auto-generated for guidance only. Review and edit before
              entering into your eQMS.
            </p>
          </>
        ) : (
          <span className="text-gray-400 italic">Draft summary not available.</span>
        )}
      </Section>

      {/* ─── ⑥ Additional Information Needed ────────────────────────────── */}
      {hasMissingInfo && (
        <Section title="Additional Information Needed" icon="🔍" accent="amber">
          <p className="whitespace-pre-wrap">{result.missing_info}</p>
        </Section>
      )}

      {/* ─── ⑧ Retrieved SOP Sources — individual expandable cards ──────── */}
      {sources.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white overflow-hidden shadow-sm">
          <div className="flex items-center gap-2 px-5 py-3 border-b border-gray-100 bg-gray-50">
            <span className="text-sm" aria-hidden="true">📄</span>
            <h2 className="text-sm font-semibold text-gray-700">
              Retrieved SOP Sections
              <span className="ml-1.5 text-xs font-normal text-gray-400">
                ({sources.length} most relevant)
              </span>
            </h2>
          </div>
          <div className="p-3 space-y-2">
            {sources.map((src, i) => (
              <SourceCard key={src.chunk_id ?? i} source={src} index={i} />
            ))}
          </div>
          <p className="px-5 pb-3 text-[10px] text-gray-400">
            Only SOP sections supplied above were used in the assessment. Relevance
            scores are TF-IDF cosine similarity (0–100%).
          </p>
        </div>
      )}

      {/* ─── Original input — collapsed reference ───────────────────────── */}
      {userInput && (
        <details className="group rounded-xl border border-gray-200 bg-white
                            overflow-hidden shadow-sm">
          <summary
            className="flex items-center justify-between gap-2 px-5 py-3
                       bg-gray-50 border-b border-gray-100 cursor-pointer
                       select-none hover:bg-gray-100 text-sm font-semibold
                       text-gray-600 list-none"
          >
            <span className="flex items-center gap-2">
              <span aria-hidden="true">💬</span>
              Original Deviation Description
            </span>
            <svg
              className="w-4 h-4 text-gray-400 group-open:rotate-180 transition-transform"
              fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"
              aria-hidden="true"
            >
              <path strokeLinecap="round" strokeLinejoin="round"
                d="m19.5 8.25-7.5 7.5-7.5-7.5" />
            </svg>
          </summary>
          <div className="px-5 py-4 text-sm text-gray-600 whitespace-pre-wrap leading-relaxed">
            {userInput}
          </div>
        </details>
      )}

      {/* ─── Feedback widget ──────────────────────────────────────────────── */}
      <FeedbackWidget traceId={result.trace_id} />

      {/* ─── Footer: trace ID · latency · CTA ───────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-2
                      pt-2 pb-6 text-xs text-gray-400">
        <div className="flex items-center gap-4">
          {result.trace_id && (
            <span>
              Trace&nbsp;
              <span className="font-mono">{result.trace_id.slice(0, 8)}…</span>
            </span>
          )}
          {result.latency_ms != null && (
            <span>{(result.latency_ms / 1000).toFixed(1)}s response</span>
          )}
        </div>
        <button
          onClick={() => navigate('/chat')}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg
                     bg-indigo-600 text-white text-xs font-semibold
                     hover:bg-indigo-700 transition-colors"
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24"
               strokeWidth={2} stroke="currentColor" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          Review another deviation
        </button>
      </div>

    </div>
  )
}
