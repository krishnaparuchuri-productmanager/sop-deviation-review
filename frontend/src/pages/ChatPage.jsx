import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { postReview } from '../api/client.js'
import { friendlyError } from '../utils/errors.js'

// ---------------------------------------------------------------------------
// Suggested prompt chips — clicking pre-fills the textarea
// ---------------------------------------------------------------------------
const CHIPS = [
  {
    label: 'Missing temperature log',
    text: 'The temperature monitoring log for Cold Room CR-03 is missing entries for the period 06:00–14:00 yesterday. The room holds finished product stability samples and three retained injectable batches. The continuous data logger alarm was not triggered, but the paper log was not completed by the morning shift operator.',
  },
  {
    label: 'SOP step skipped',
    text: 'An analyst completed the in-process dissolution test for Batch TAB-1177 without performing the required media deaeration step as specified in the validated test method STP-022. The step was omitted due to time pressure at end of shift. Results have already been entered into the LIMS and are pending QA approval.',
  },
  {
    label: 'Labelling mismatch',
    text: 'During final packaging inspection for Batch PKG-0892, the QA line inspector found that the secondary carton label shows Lot No. PKG-0829 instead of the correct PKG-0892. An estimated 3,200 units have already been labelled. No units have left the warehouse and the packaging line has been stopped pending investigation.',
  },
  {
    label: 'Equipment alarm',
    text: 'The autoclave used for sterilising equipment components in the aseptic fill suite triggered a high-pressure abort alarm mid-cycle during a sterilisation run for Batch INJ-0044. The cycle was automatically aborted at 78% completion. The root cause is unknown. The equipment has been taken out of service and all components from the aborted run are quarantined.',
  },
]

// ---------------------------------------------------------------------------
// Example deviation for the "Load Example" button
// ---------------------------------------------------------------------------
const EXAMPLE_TEXT =
  'During routine in-process checks on Packaging Line 3, an operator discovered that the printed expiry date on 1,800 blister packs of Batch ORL-0521 reads "MAR 2025" instead of the correct "MAR 2027". The packs were produced during the first two hours of today\'s shift. Approximately 600 units have already been transferred to the warehouse staging area. The packaging line has been stopped and the affected units have been placed on hold pending QA review.'

// ---------------------------------------------------------------------------
// Spinner component
// ---------------------------------------------------------------------------
function Spinner() {
  return (
    <svg
      className="animate-spin h-5 w-5 text-white"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
    </svg>
  )
}

// ---------------------------------------------------------------------------
// ChatPage
// ---------------------------------------------------------------------------
export default function ChatPage() {
  const navigate   = useNavigate()
  const [text, setText]             = useState('')
  const [loading, setLoading]       = useState(false)
  const [error, setError]           = useState(null)
  const [coldStart, setColdStart]   = useState(false)   // shows after 5s of loading
  const coldStartTimer              = useRef(null)

  // Show a "server waking up" hint if the backend takes more than 5 seconds.
  // Railway free tier cold-starts can take 20–30 s after a period of inactivity.
  useEffect(() => {
    if (loading) {
      coldStartTimer.current = setTimeout(() => setColdStart(true), 5000)
    } else {
      clearTimeout(coldStartTimer.current)
      setColdStart(false)
    }
    return () => clearTimeout(coldStartTimer.current)
  }, [loading])

  const charCount  = text.length
  const canSubmit  = charCount >= 20 && !loading

  // Pre-fill textarea from a chip or the example button
  function fillText(value) {
    setText(value)
    setError(null)
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (!canSubmit) return
    setLoading(true)
    setError(null)

    try {
      const result = await postReview(text.trim())
      // Pass the full API response as router state → ResultsPage reads it
      navigate('/results', { state: { result, userInput: text.trim() } })
    } catch (err) {
      setError(friendlyError(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-10">

      {/* Page header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">GMP Deviation Review</h1>
        <p className="mt-1 text-sm text-gray-500">
          Paste or type a deviation description. The assistant will retrieve relevant
          SOP sections and return a structured GMP assessment.
        </p>
      </div>

      <form onSubmit={handleSubmit} noValidate>

        {/* ── Suggested chips ─────────────────────────────────────────── */}
        <div className="mb-4">
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
            Common scenarios
          </p>
          <div className="flex flex-wrap gap-2">
            {CHIPS.map((chip) => (
              <button
                key={chip.label}
                type="button"
                onClick={() => fillText(chip.text)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium
                           bg-indigo-50 text-indigo-700 ring-1 ring-inset ring-indigo-200
                           hover:bg-indigo-100 hover:ring-indigo-300
                           transition-colors duration-150 select-none"
              >
                <svg className="w-3 h-3 flex-shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                </svg>
                {chip.label}
              </button>
            ))}
          </div>
        </div>

        {/* ── Textarea ────────────────────────────────────────────────── */}
        <div className="relative">
          <textarea
            id="deviation-input"
            value={text}
            onChange={(e) => { setText(e.target.value); setError(null) }}
            rows={9}
            placeholder="Describe the deviation in as much detail as possible — what happened, when, which batch or equipment was involved, and what procedure was departed from…"
            className={[
              'w-full rounded-xl border px-4 py-3 text-sm text-gray-800 placeholder-gray-400',
              'resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent',
              'transition-colors duration-150',
              error
                ? 'border-red-300 bg-red-50 focus:ring-red-400'
                : 'border-gray-300 bg-white hover:border-gray-400',
            ].join(' ')}
            aria-label="Deviation description"
            aria-describedby={error ? 'input-error' : undefined}
            disabled={loading}
          />
          {/* Character counter */}
          <span className={`absolute bottom-3 right-3 text-xs select-none ${charCount < 20 ? 'text-gray-300' : 'text-gray-400'}`}>
            {charCount}
          </span>
        </div>

        {/* ── Error banner ────────────────────────────────────────────── */}
        {error && (
          <div
            id="input-error"
            role="alert"
            className="mt-3 flex items-start gap-2 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700"
          >
            <svg className="w-4 h-4 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
            </svg>
            <span><strong className="font-semibold">Request failed:</strong> {error}</span>
          </div>
        )}

        {/* ── Cold-start notice ───────────────────────────────────────── */}
        {coldStart && (
          <div className="mt-3 flex items-start gap-2 rounded-lg bg-blue-50 border border-blue-200 px-4 py-3 text-sm text-blue-700">
            <svg className="w-4 h-4 mt-0.5 flex-shrink-0 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
            </svg>
            <span>
              <strong className="font-semibold">Server is waking up…</strong>{' '}
              The backend runs on a free hosting tier and may take up to 30 seconds
              after a period of inactivity. Please wait — your request is on its way.
            </span>
          </div>
        )}

        {/* ── Action row ──────────────────────────────────────────────── */}
        <div className="mt-4 flex items-center justify-between gap-3">
          {/* Load Example */}
          <button
            type="button"
            onClick={() => fillText(EXAMPLE_TEXT)}
            disabled={loading}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium
                       text-gray-600 bg-gray-100 hover:bg-gray-200
                       disabled:opacity-50 disabled:cursor-not-allowed
                       transition-colors duration-150"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 0 0 6 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 0 1 6 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 0 1 6-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0 0 18 18a8.967 8.967 0 0 0-6 2.292m0-14.25v14.25" />
            </svg>
            Load Example
          </button>

          {/* Submit */}
          <button
            type="submit"
            disabled={!canSubmit}
            className={[
              'inline-flex items-center gap-2 px-6 py-2.5 rounded-lg text-sm font-semibold',
              'transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500',
              canSubmit
                ? 'bg-indigo-600 text-white hover:bg-indigo-700 shadow-sm hover:shadow'
                : 'bg-indigo-300 text-white cursor-not-allowed',
            ].join(' ')}
          >
            {loading ? (
              <>
                <Spinner />
                Analysing…
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09Z" />
                </svg>
                Review Deviation
              </>
            )}
          </button>
        </div>

        {/* Minimum length hint */}
        {charCount > 0 && charCount < 20 && (
          <p className="mt-2 text-xs text-amber-600">
            Add at least {20 - charCount} more character{20 - charCount !== 1 ? 's' : ''} to submit.
          </p>
        )}
      </form>
    </div>
  )
}
