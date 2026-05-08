/**
 * EvalsPage.jsx — Evaluation suite runner and results viewer.
 *
 * Layout:
 *   • Header  : page title + "Run Evals" button + run-selector dropdown
 *   • Summary : side-by-side actual vs baseline metric cards
 *   • Table   : one row per eval case; failed rows highlighted red
 *
 * Data flow:
 *   Mount  → GET /api/evals/results  (show previous run if one exists)
 *   Button → POST /api/evals/run     (≈3-6 min; spinner shown)
 *          → GET /api/evals/results  (refresh table with new run)
 */

import { useState, useEffect, useCallback } from 'react'
import { runEvals, getEvalsResults } from '../api/client.js'
import { friendlyError } from '../utils/errors.js'


// ─────────────────────────────────────────────────────────────────────────────
// Dimension colour helpers
// ─────────────────────────────────────────────────────────────────────────────

/** Return a Tailwind text-colour class for a 0-2 dimension score. */
function scoreColor(v) {
  if (v === 2) return 'text-emerald-600'
  if (v === 1) return 'text-amber-500'
  return 'text-red-500'
}

/** Return Tailwind ring/bg/text classes for a 0-2 score pill. */
function scorePillClass(v) {
  if (v === 2) return 'bg-emerald-50 text-emerald-700 ring-emerald-200'
  if (v === 1) return 'bg-amber-50  text-amber-700  ring-amber-200'
  return             'bg-red-50    text-red-700    ring-red-200'
}


// ─────────────────────────────────────────────────────────────────────────────
// ScorePill — small badge for a single 0-2 dimension value
// ─────────────────────────────────────────────────────────────────────────────

function ScorePill({ value }) {
  return (
    <span
      className={`inline-flex items-center justify-center w-6 h-6 rounded-full
                  text-[11px] font-bold ring-1 ${scorePillClass(value)}`}
    >
      {value}
    </span>
  )
}


// ─────────────────────────────────────────────────────────────────────────────
// PassBadge — PASS / FAIL chip
// ─────────────────────────────────────────────────────────────────────────────

function PassBadge({ pass }) {
  return pass ? (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full
                     bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200 text-[11px] font-semibold">
      ✓ PASS
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full
                     bg-red-50 text-red-700 ring-1 ring-red-200 text-[11px] font-semibold">
      ✗ FAIL
    </span>
  )
}


// ─────────────────────────────────────────────────────────────────────────────
// SummaryCard — metrics for one model tag (actual or baseline)
// ─────────────────────────────────────────────────────────────────────────────

function SummaryCard({ title, summary, accent }) {
  if (!summary) return null

  const passRate = summary.pass_rate_pct.toFixed(0)

  const dims = [
    { key: 'avg_groundedness',   label: 'Groundedness'   },
    { key: 'avg_classification', label: 'Classification'  },
    { key: 'avg_escalation',     label: 'Escalation'     },
    { key: 'avg_clarity',        label: 'Clarity'        },
  ]

  const accentRing = accent === 'indigo' ? 'ring-indigo-200' : 'ring-slate-200'
  const accentBg   = accent === 'indigo' ? 'bg-indigo-600'   : 'bg-slate-400'
  const accentText = accent === 'indigo' ? 'text-indigo-600' : 'text-slate-500'
  const headerBg   = accent === 'indigo' ? 'bg-indigo-50'    : 'bg-slate-50'
  const barColor   = accent === 'indigo' ? 'bg-indigo-500'   : 'bg-slate-400'
  const passColor  = parseFloat(passRate) >= 60 ? 'text-emerald-600' : 'text-red-500'

  return (
    <div className={`rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden ring-1 ${accentRing}`}>
      {/* Card header */}
      <div className={`flex items-center gap-2 px-4 py-3 border-b border-gray-100 ${headerBg}`}>
        <span className={`w-2 h-2 rounded-full flex-shrink-0 ${accentBg}`} />
        <h3 className={`text-sm font-semibold ${accentText}`}>{title}</h3>
        <span className="ml-auto text-xs text-gray-400 tabular-nums">
          {summary.pass_count} / {summary.cases} passed
        </span>
      </div>

      <div className="px-5 py-4 space-y-4">
        {/* Big pass-rate number */}
        <div className="flex items-end gap-2">
          <span className={`text-4xl font-extrabold tabular-nums leading-none ${passColor}`}>
            {passRate}%
          </span>
          <span className="text-sm text-gray-400 mb-0.5">pass rate</span>
        </div>

        {/* Avg total score bar */}
        <div>
          <div className="flex justify-between text-xs text-gray-500 mb-1">
            <span>Avg total score</span>
            <span className="font-semibold tabular-nums text-gray-700">
              {summary.avg_total_score.toFixed(2)} / 8
            </span>
          </div>
          <div className="w-full bg-gray-100 rounded-full h-2">
            <div
              className={`h-2 rounded-full transition-all duration-700 ${barColor}`}
              style={{ width: `${(summary.avg_total_score / 8) * 100}%` }}
            />
          </div>
        </div>

        {/* Per-dimension rows */}
        <div className="space-y-1.5">
          {dims.map(({ key, label }) => {
            const val = summary[key]
            const dimBarColor = val >= 1.5 ? 'bg-emerald-400' : val >= 1 ? 'bg-amber-400' : 'bg-red-400'
            return (
              <div key={key} className="flex items-center gap-2 text-xs">
                <span className="w-28 text-gray-500 flex-shrink-0">{label}</span>
                <div className="flex-1 bg-gray-100 rounded-full h-1.5">
                  <div
                    className={`h-1.5 rounded-full ${dimBarColor}`}
                    style={{ width: `${(val / 2) * 100}%` }}
                  />
                </div>
                <span className={`w-7 text-right font-semibold tabular-nums ${scoreColor(Math.round(val))}`}>
                  {val.toFixed(2)}
                </span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}


// ─────────────────────────────────────────────────────────────────────────────
// ResultsTable — scored rows; failed rows highlighted red
// ─────────────────────────────────────────────────────────────────────────────

function ResultsTable({ results, activeTab }) {
  if (!results || results.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-gray-300 bg-gray-50
                      py-16 text-center text-sm text-gray-400">
        No results yet — click <strong>Run Evals</strong> to generate scores.
      </div>
    )
  }

  // Which model_tag to display based on the active tab
  const tagKey = activeTab === 'actual' ? 'actual' : 'baseline_always_escalate'

  // Build a map of case_id → { actual: row, baseline_always_escalate: row }
  const byCase = {}
  for (const r of results) {
    if (!byCase[r.case_id]) byCase[r.case_id] = {}
    byCase[r.case_id][r.model_tag] = r
  }

  const caseIds    = [...new Set(results.map(r => r.case_id))].sort()
  const visibleRows = caseIds.map(cid => byCase[cid]?.[tagKey]).filter(Boolean)

  return (
    <div className="overflow-x-auto rounded-xl border border-gray-200 shadow-sm">
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-4 py-3 text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider w-24">
              Case
            </th>
            <th className="px-3 py-3 text-center text-[11px] font-semibold text-gray-500 uppercase tracking-wider w-10"
                title="Groundedness (0–2): are all SOP references real and relevant?">
              G
            </th>
            <th className="px-3 py-3 text-center text-[11px] font-semibold text-gray-500 uppercase tracking-wider w-10"
                title="Classification (0–2): does the severity match the expected level?">
              Cl
            </th>
            <th className="px-3 py-3 text-center text-[11px] font-semibold text-gray-500 uppercase tracking-wider w-10"
                title="Escalation (0–2): is the QA escalation flag and rationale correct?">
              Es
            </th>
            <th className="px-3 py-3 text-center text-[11px] font-semibold text-gray-500 uppercase tracking-wider w-10"
                title="Clarity (0–2): is the explanation clear and complete?">
              Cy
            </th>
            <th className="px-3 py-3 text-center text-[11px] font-semibold text-gray-500 uppercase tracking-wider w-16">
              Total
            </th>
            <th className="px-4 py-3 text-center text-[11px] font-semibold text-gray-500 uppercase tracking-wider w-20">
              Result
            </th>
            <th className="px-4 py-3 text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider">
              Judge notes
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 bg-white">
          {visibleRows.map((row) => {
            const failed = row.overall_pass === 0
            return (
              <tr
                key={`${row.case_id}-${row.model_tag}`}
                className={
                  failed
                    ? 'bg-red-50 hover:bg-red-100/70 transition-colors'
                    : 'hover:bg-gray-50/80 transition-colors'
                }
              >
                {/* Case ID + red dot on failure */}
                <td className="px-4 py-3 font-mono font-semibold text-gray-800 text-xs whitespace-nowrap">
                  <span className={failed ? 'text-red-700' : ''}>{row.case_id}</span>
                  {failed && (
                    <span className="ml-1.5 text-red-400" aria-hidden="true">●</span>
                  )}
                </td>

                {/* Dimension score pills */}
                <td className="px-3 py-3 text-center"><ScorePill value={row.groundedness} /></td>
                <td className="px-3 py-3 text-center"><ScorePill value={row.classification} /></td>
                <td className="px-3 py-3 text-center"><ScorePill value={row.escalation} /></td>
                <td className="px-3 py-3 text-center"><ScorePill value={row.clarity} /></td>

                {/* Total score */}
                <td className="px-3 py-3 text-center">
                  <span className={`font-bold tabular-nums text-sm ${
                    row.total_score >= 6 ? 'text-emerald-600' :
                    row.total_score >= 4 ? 'text-amber-500'   : 'text-red-500'
                  }`}>
                    {row.total_score}
                    <span className="text-gray-300 font-normal text-xs">/8</span>
                  </span>
                </td>

                {/* Pass / Fail badge */}
                <td className="px-4 py-3 text-center">
                  <PassBadge pass={row.overall_pass === 1} />
                </td>

                {/* Judge notes */}
                <td className={`px-4 py-3 text-xs leading-relaxed max-w-sm
                                ${failed ? 'text-red-600' : 'text-gray-500'}`}>
                  {row.notes || <span className="text-gray-300 italic">—</span>}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}


// ─────────────────────────────────────────────────────────────────────────────
// Loading skeleton for the table
// ─────────────────────────────────────────────────────────────────────────────

function TableSkeleton() {
  return (
    <div className="rounded-xl border border-gray-200 shadow-sm overflow-hidden animate-pulse">
      <div className="h-10 bg-gray-50 border-b border-gray-100" />
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 px-4 py-3 border-b border-gray-100">
          <div className="h-3 w-16 bg-gray-100 rounded" />
          {Array.from({ length: 4 }).map((__, j) => (
            <div key={j} className="h-6 w-6 bg-gray-100 rounded-full" />
          ))}
          <div className="h-3 w-10 bg-gray-100 rounded ml-2" />
          <div className="h-3 w-12 bg-gray-100 rounded" />
          <div className="h-3 flex-1 bg-gray-100 rounded" />
        </div>
      ))}
    </div>
  )
}


// ─────────────────────────────────────────────────────────────────────────────
// Icons (Heroicons outline)
// ─────────────────────────────────────────────────────────────────────────────

const IconPlay = () => (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round"
      d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.347a1.125 1.125 0 0 1 0 1.972l-11.54 6.347a1.125 1.125 0 0 1-1.667-.986V5.653Z" />
  </svg>
)

const IconSpinner = () => (
  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
    <path className="opacity-75" fill="currentColor"
      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
  </svg>
)

const IconChevronDown = () => (
  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
  </svg>
)

const IconInfo = () => (
  <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round"
      d="m11.25 11.25.041-.02a.75.75 0 0 1 1.063.852l-.708 2.836a.75.75 0 0 0 1.063.853l.041-.021M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9-3.75h.008v.008H12V8.25Z" />
  </svg>
)


// ─────────────────────────────────────────────────────────────────────────────
// EvalsPage — main export
// ─────────────────────────────────────────────────────────────────────────────

export default function EvalsPage() {
  const [data,       setData]       = useState(null)   // EvalResultsResponse
  const [loading,    setLoading]    = useState(true)   // initial GET fetch
  const [running,    setRunning]    = useState(false)  // POST /evals/run in progress
  const [runError,   setRunError]   = useState(null)
  const [fetchError, setFetchError] = useState(null)
  const [activeTab,  setActiveTab]  = useState('actual')
  const [elapsed,    setElapsed]    = useState(0)      // seconds ticker during run

  // ── Fetch results (latest or specific run_id) ──────────────────────────────
  const fetchResults = useCallback(async (runId = null) => {
    setFetchError(null)
    try {
      const res = await getEvalsResults(runId)
      setData(res)
    } catch (e) {
      setFetchError(friendlyError(e))
    }
  }, [])

  useEffect(() => {
    fetchResults().finally(() => setLoading(false))
  }, [fetchResults])

  // ── Elapsed-seconds ticker while running ───────────────────────────────────
  useEffect(() => {
    if (!running) { setElapsed(0); return }
    const t = setInterval(() => setElapsed(s => s + 1), 1000)
    return () => clearInterval(t)
  }, [running])

  // ── Trigger a new eval run ─────────────────────────────────────────────────
  async function handleRunEvals() {
    setRunning(true)
    setRunError(null)
    try {
      await runEvals()         // ≈3-6 min blocking call
      await fetchResults()     // refresh with new run data
    } catch (e) {
      setRunError(friendlyError(e))
    } finally {
      setRunning(false)
    }
  }

  // ── Derived counts ─────────────────────────────────────────────────────────
  const actualRows   = data?.results?.filter(r => r.model_tag === 'actual') ?? []
  const baselineRows = data?.results?.filter(r => r.model_tag === 'baseline_always_escalate') ?? []
  const failCount    = actualRows.filter(r => r.overall_pass === 0).length
  const passCount    = actualRows.filter(r => r.overall_pass === 1).length

  const fmtElapsed = (s) => {
    const m   = Math.floor(s / 60)
    const sec = s % 60
    return m > 0 ? `${m}m ${sec}s` : `${sec}s`
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="max-w-7xl mx-auto px-4 py-8 space-y-6">

      {/* ── Page header ──────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Eval Suite</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            15 golden cases · LLM-as-judge scoring · 4 rubric dimensions (0–2 each) · pass ≥ 6 / 8
          </p>
        </div>

        {/* Elapsed counter + Run button */}
        <div className="flex items-center gap-3">
          {running && (
            <span className="text-xs text-amber-600 tabular-nums font-medium animate-pulse">
              ⏱ {fmtElapsed(elapsed)} — typically 3–6 min…
            </span>
          )}
          <button
            onClick={handleRunEvals}
            disabled={running || loading}
            className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold
                        shadow-sm transition-all duration-150
                        ${running || loading
                          ? 'bg-indigo-300 text-white cursor-not-allowed'
                          : 'bg-indigo-600 hover:bg-indigo-700 active:scale-95 text-white'}`}
          >
            {running ? <IconSpinner /> : <IconPlay />}
            {running ? 'Running…' : 'Run Evals'}
          </button>
        </div>
      </div>

      {/* ── Long-run warning banner ───────────────────────────────────────── */}
      {running && (
        <div className="flex items-start gap-3 rounded-xl border border-amber-200
                        bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <IconInfo />
          <div>
            <strong>Eval run in progress.</strong>{' '}
            The pipeline calls Claude Haiku for each of the 15 cases, then scores every output
            with an LLM judge. This takes 3–6 minutes. Do not close or refresh this tab.
          </div>
        </div>
      )}

      {/* ── Run error ────────────────────────────────────────────────────── */}
      {runError && (
        <div role="alert" className="flex items-center gap-3 rounded-xl border border-red-200
                                      bg-red-50 px-5 py-3 text-sm text-red-700">
          <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24"
               strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
          </svg>
          <span className="flex-1">Run failed: {runError}</span>
          <button onClick={handleRunEvals} className="underline font-semibold hover:text-red-900">
            Retry
          </button>
        </div>
      )}

      {/* ── Fetch error ──────────────────────────────────────────────────── */}
      {fetchError && !running && (
        <div role="alert" className="flex items-center gap-3 rounded-xl border border-red-200
                                      bg-red-50 px-5 py-3 text-sm text-red-700">
          <span className="flex-1">Failed to load results: {fetchError}</span>
          <button onClick={() => fetchResults()} className="underline font-semibold hover:text-red-900">
            Retry
          </button>
        </div>
      )}

      {/* ── Run meta bar: run_id badge + pass/fail counts + run selector ──── */}
      {!loading && data?.run_id && (
        <div className="flex flex-wrap items-center gap-3 text-xs text-gray-500">
          <span className="flex items-center gap-1.5">
            <span className="text-gray-400">Run:</span>
            <code className="font-mono bg-gray-100 px-1.5 py-0.5 rounded text-gray-700">
              {data.run_id.slice(0, 8)}…
            </code>
          </span>

          {actualRows.length > 0 && (
            <>
              <span className="text-gray-300">|</span>
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-emerald-400 inline-block" />
                {passCount} passed
              </span>
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-red-400 inline-block" />
                {failCount} failed
              </span>
            </>
          )}

          {/* Run selector — only shown when > 1 run exists */}
          {data.available_runs.length > 1 && (
            <div className="ml-auto flex items-center gap-1.5">
              <span className="text-gray-400">Switch run:</span>
              <div className="relative">
                <select
                  className="appearance-none bg-white border border-gray-200 rounded-lg
                             pl-3 pr-7 py-1 text-xs text-gray-700 cursor-pointer
                             hover:border-gray-300 focus:outline-none focus:ring-2 focus:ring-indigo-300"
                  value={data.run_id}
                  onChange={e => fetchResults(e.target.value)}
                >
                  {data.available_runs.map((rid, i) => (
                    <option key={rid} value={rid}>
                      {i === 0 ? 'Latest' : `Run ${i + 1}`} — {rid.slice(0, 8)}
                    </option>
                  ))}
                </select>
                <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-gray-400">
                  <IconChevronDown />
                </span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Summary cards: actual vs baseline ───────────────────────────── */}
      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 animate-pulse">
          {[0, 1].map(i => (
            <div key={i} className="rounded-xl border border-gray-200 bg-white shadow-sm h-56" />
          ))}
        </div>
      ) : data?.run_id ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <SummaryCard
            title="Agent Pipeline (actual)"
            summary={data.actual_summary}
            accent="indigo"
          />
          <SummaryCard
            title="Baseline — Always Escalate"
            summary={data.baseline_summary}
            accent="slate"
          />
        </div>
      ) : null}

      {/* ── Rubric legend ─────────────────────────────────────────────────── */}
      {!loading && data?.run_id && (
        <div className="flex flex-wrap gap-x-6 gap-y-1.5 text-[11px] text-gray-400 bg-gray-50
                        rounded-lg px-4 py-2.5 border border-gray-100">
          <span><strong className="text-gray-600">G</strong> — Groundedness: SOP refs real &amp; relevant</span>
          <span><strong className="text-gray-600">Cl</strong> — Classification: severity matches expected</span>
          <span><strong className="text-gray-600">Es</strong> — Escalation: QA flag + rationale correct</span>
          <span><strong className="text-gray-600">Cy</strong> — Clarity: explanation clear &amp; complete</span>
          <span className="ml-auto flex items-center gap-3 flex-shrink-0">
            <span className="flex items-center gap-1">
              <span className="w-4 h-4 rounded-full bg-emerald-100 ring-1 ring-emerald-200 inline-flex items-center justify-center text-emerald-700 font-bold text-[9px]">2</span>
              Excellent
            </span>
            <span className="flex items-center gap-1">
              <span className="w-4 h-4 rounded-full bg-amber-100 ring-1 ring-amber-200 inline-flex items-center justify-center text-amber-700 font-bold text-[9px]">1</span>
              Partial
            </span>
            <span className="flex items-center gap-1">
              <span className="w-4 h-4 rounded-full bg-red-100 ring-1 ring-red-200 inline-flex items-center justify-center text-red-700 font-bold text-[9px]">0</span>
              Poor
            </span>
          </span>
        </div>
      )}

      {/* ── Model-tag tabs ────────────────────────────────────────────────── */}
      {!loading && data?.run_id && (
        <div className="flex gap-1 border-b border-gray-200 -mb-2">
          {[
            { id: 'actual',   label: 'Agent Pipeline',           count: actualRows.length   },
            { id: 'baseline', label: 'Always-Escalate Baseline', count: baselineRows.length },
          ].map(({ id, label, count }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              className={`px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors duration-100
                          ${activeTab === id
                            ? 'border-indigo-600 text-indigo-700'
                            : 'border-transparent text-gray-500 hover:text-gray-800 hover:border-gray-300'}`}
            >
              {label}
              <span className={`ml-2 text-xs px-1.5 py-0.5 rounded-full
                                ${activeTab === id
                                  ? 'bg-indigo-100 text-indigo-600'
                                  : 'bg-gray-100 text-gray-400'}`}>
                {count}
              </span>
            </button>
          ))}
        </div>
      )}

      {/* ── Results table ─────────────────────────────────────────────────── */}
      {loading ? (
        <TableSkeleton />
      ) : (
        <ResultsTable results={data?.results ?? []} activeTab={activeTab} />
      )}

      {/* ── Empty state — no runs yet ─────────────────────────────────────── */}
      {!loading && !data?.run_id && !running && !fetchError && (
        <div className="rounded-xl border border-dashed border-gray-300 bg-gray-50
                        py-20 text-center">
          <svg className="mx-auto w-10 h-10 text-gray-300 mb-4" fill="none" viewBox="0 0 24 24"
               strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M9.75 3.104v5.714a2.25 2.25 0 0 1-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 0 1 4.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0 1 12 15a9.065 9.065 0 0 1-6.23-.693L5 14.5m14.8.8 1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0 1 12 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5" />
          </svg>
          <p className="text-sm font-semibold text-gray-500">No eval runs yet</p>
          <p className="text-xs text-gray-400 mt-1 mb-5">
            Click <strong>Run Evals</strong> above to score all 15 golden cases.
          </p>
          <button
            onClick={handleRunEvals}
            className="inline-flex items-center gap-2 px-5 py-2 rounded-lg text-sm
                       font-semibold bg-indigo-600 hover:bg-indigo-700 text-white
                       shadow-sm active:scale-95 transition-all"
          >
            <IconPlay />
            Run Evals
          </button>
        </div>
      )}

    </div>
  )
}
