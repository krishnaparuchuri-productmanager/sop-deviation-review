/**
 * DashboardPage.jsx — 7-panel analytics dashboard for the SOP Deviation Review Assistant.
 *
 * Panels:
 *   1. Total Chats KPI card
 *   2. Escalation Rate KPI card
 *   3. Average Latency KPI card
 *   4. Estimated Cost KPI card  (total + per-review breakdown)
 *   5. Downvote Rate KPI card
 *   6. Chats per Day — SVG area/line chart (last 7 days)
 *   7. Severity Breakdown — SVG donut chart
 *
 * All data comes from GET /api/dashboard/metrics. No chart library is used.
 */

import { useState, useEffect } from 'react'
import { getDashboardMetrics } from '../api/client.js'
import { friendlyError } from '../utils/errors.js'

// ---------------------------------------------------------------------------
// Haiku pricing constants — must match backend/routes/dashboard.py
// Used to annotate the cost footer so reviewers can verify the calculation.
// ---------------------------------------------------------------------------
const INPUT_PRICE_PER_MTOK  = 0.80   // USD per million input tokens
const OUTPUT_PRICE_PER_MTOK = 4.00   // USD per million output tokens

// ---------------------------------------------------------------------------
// Severity colour palette — shared by donut chart + legend
// ---------------------------------------------------------------------------
const SEV_COLOR = { High: '#ef4444', Medium: '#f59e0b', Low: '#22c55e' }


// ─────────────────────────────────────────────────────────────────────────────
// Panel 1–5: KPI card
// ─────────────────────────────────────────────────────────────────────────────

function KpiCard({ label, value, sub, icon, accent = 'indigo' }) {
  const palette = {
    indigo:  'text-indigo-600  bg-indigo-50',
    red:     'text-red-600     bg-red-50',
    amber:   'text-amber-600   bg-amber-50',
    cyan:    'text-cyan-600    bg-cyan-50',
    emerald: 'text-emerald-600 bg-emerald-50',
    orange:  'text-orange-600  bg-orange-50',
    slate:   'text-slate-500   bg-slate-100',
  }
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm flex flex-col gap-3">
      <div className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 ${palette[accent] ?? palette.slate}`}>
        {icon}
      </div>
      <div>
        <p className="text-2xl font-bold text-gray-900 tabular-nums leading-tight">{value}</p>
        {sub && (
          <p className="text-xs text-gray-400 mt-0.5 tabular-nums leading-snug">{sub}</p>
        )}
        <p className="text-[11px] font-semibold text-gray-400 mt-1.5 uppercase tracking-wide">
          {label}
        </p>
      </div>
    </div>
  )
}


// ─────────────────────────────────────────────────────────────────────────────
// Panel 6: Chats per Day — SVG area + line chart
// ─────────────────────────────────────────────────────────────────────────────

function DailyLineChart({ data }) {
  // Fixed logical canvas; SVG scales to container via viewBox.
  const W = 480, H = 150
  const PAD = { top: 14, right: 14, bottom: 38, left: 34 }
  const cW = W - PAD.left - PAD.right   // 432
  const cH = H - PAD.top  - PAD.bottom  // 98

  const n      = data.length            // always 7
  const counts = data.map(d => d.count)
  const maxVal = Math.max(...counts, 1) // guard against all-zero

  // Map index → pixel x; value → pixel y (y increases downward)
  const xOf = (i) => PAD.left + (n > 1 ? (i / (n - 1)) * cW : cW / 2)
  const yOf = (v) => PAD.top  + cH - (v / maxVal) * cH

  const pts  = data.map((d, i) => [xOf(i), yOf(d.count)])
  const poly = pts.map(([x, y]) => `${x},${y}`).join(' ')

  // Closed path for the gradient-filled area below the line
  const area = [
    `M ${pts[0][0]},${pts[0][1]}`,
    ...pts.slice(1).map(([x, y]) => `L ${x},${y}`),
    `L ${pts[n - 1][0]},${PAD.top + cH}`,
    `L ${pts[0][0]},${PAD.top + cH}`,
    'Z',
  ].join(' ')

  // Y-axis ticks: 0, midpoint, max
  const yTicks = [...new Set([0, Math.round(maxVal / 2), maxVal])]

  // X-axis date labels: "May 7"
  const fmtDate = (iso) =>
    new Date(iso + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="w-full"
      aria-label="Reviews per day for the last 7 days"
      style={{ overflow: 'visible' }}
    >
      <defs>
        <linearGradient id="lineAreaGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor="#6366f1" stopOpacity="0.22" />
          <stop offset="100%" stopColor="#6366f1" stopOpacity="0"    />
        </linearGradient>
      </defs>

      {/* Horizontal grid lines + Y labels */}
      {yTicks.map((t) => (
        <g key={t}>
          <line
            x1={PAD.left} y1={yOf(t)}
            x2={PAD.left + cW} y2={yOf(t)}
            stroke="#e2e8f0" strokeWidth={1}
          />
          <text
            x={PAD.left - 6} y={yOf(t)}
            textAnchor="end" dominantBaseline="middle"
            fontSize="9" fill="#94a3b8"
          >
            {t}
          </text>
        </g>
      ))}

      {/* Gradient area */}
      <path d={area} fill="url(#lineAreaGrad)" />

      {/* Line */}
      <polyline
        points={poly}
        fill="none"
        stroke="#6366f1"
        strokeWidth={2.5}
        strokeLinejoin="round"
        strokeLinecap="round"
      />

      {/* Data-point dots */}
      {pts.map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r={3.5} fill="#6366f1" stroke="#fff" strokeWidth={1.5} />
      ))}

      {/* X-axis date labels */}
      {data.map((d, i) => (
        <text
          key={i}
          x={xOf(i)} y={H - 6}
          textAnchor="middle"
          fontSize="9" fill="#94a3b8"
        >
          {fmtDate(d.date)}
        </text>
      ))}
    </svg>
  )
}


// ─────────────────────────────────────────────────────────────────────────────
// Panel 7: Severity Breakdown — SVG donut chart
// ─────────────────────────────────────────────────────────────────────────────

function SeverityDonut({ breakdown }) {
  const total = breakdown.reduce((s, d) => s + d.count, 0)

  if (total === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-44 text-sm text-gray-400 gap-2">
        <svg className="w-8 h-8 text-gray-200" fill="none" viewBox="0 0 24 24"
             strokeWidth={1.5} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round"
            d="M10.5 6a7.5 7.5 0 1 0 7.5 7.5h-7.5V6Z" />
          <path strokeLinecap="round" strokeLinejoin="round"
            d="M13.5 10.5H21A7.5 7.5 0 0 0 13.5 3v7.5Z" />
        </svg>
        No data yet
      </div>
    )
  }

  // Donut parameters
  const R    = 52           // ring radius
  const SW   = 22           // stroke width (ring thickness)
  const CX   = 80, CY = 80  // centre of 160×160 SVG
  const CIRC = 2 * Math.PI * R

  // Build segments: each is a full-circle arc with stroke-dasharray trimmed to its slice,
  // rotated to start where the previous segment ended.
  let cumulativeDeg = -90   // start from 12 o'clock
  const segments = breakdown.map(({ severity, count }) => {
    const pct    = count / total
    const len    = pct * CIRC
    const start  = cumulativeDeg
    cumulativeDeg += pct * 360
    return { severity, count, len, start }
  })

  return (
    <div className="flex flex-col sm:flex-row items-center gap-5 w-full">
      {/* Donut SVG */}
      <div className="flex-shrink-0">
        <svg viewBox="0 0 160 160" width="148" height="148" aria-label="Severity donut chart">
          {/* Track ring */}
          <circle
            cx={CX} cy={CY} r={R}
            fill="none" stroke="#f1f5f9" strokeWidth={SW}
          />
          {/* Coloured segments */}
          {segments.map(({ severity, len, start }) => (
            <circle
              key={severity}
              cx={CX} cy={CY} r={R}
              fill="none"
              stroke={SEV_COLOR[severity] ?? '#94a3b8'}
              strokeWidth={SW}
              strokeDasharray={`${len} ${CIRC - len}`}
              strokeLinecap="butt"
              style={{
                transform: `rotate(${start}deg)`,
                transformOrigin: `${CX}px ${CY}px`,
              }}
            />
          ))}
          {/* Centre label */}
          <text
            x={CX} y={CY - 7}
            textAnchor="middle"
            fontSize="22" fontWeight="700" fill="#111827"
          >
            {total}
          </text>
          <text
            x={CX} y={CY + 11}
            textAnchor="middle"
            fontSize="10" fill="#9ca3af"
          >
            reviews
          </text>
        </svg>
      </div>

      {/* Legend */}
      <ul className="space-y-2.5 text-sm min-w-0">
        {segments.map(({ severity, count }) => (
          <li key={severity} className="flex items-center gap-2.5">
            <span
              className="w-2.5 h-2.5 rounded-full flex-shrink-0"
              style={{ background: SEV_COLOR[severity] ?? '#94a3b8' }}
            />
            <span className="font-medium text-gray-700">{severity}</span>
            <span className="ml-auto pl-3 text-gray-400 tabular-nums text-xs">
              {count}
              <span className="ml-1 text-gray-300">
                ({((count / total) * 100).toFixed(0)}%)
              </span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}


// ─────────────────────────────────────────────────────────────────────────────
// Loading skeleton
// ─────────────────────────────────────────────────────────────────────────────

function SkeletonCard() {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm animate-pulse">
      <div className="w-9 h-9 bg-gray-100 rounded-lg mb-3" />
      <div className="h-7 w-16 bg-gray-100 rounded mb-2" />
      <div className="h-2.5 w-24 bg-gray-100 rounded mb-3" />
      <div className="h-2.5 w-20 bg-gray-100 rounded" />
    </div>
  )
}

function SkeletonChart({ tall = false }) {
  return (
    <div className={`rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden animate-pulse ${tall ? 'h-60' : 'h-52'}`}>
      <div className="h-10 bg-gray-50 border-b border-gray-100" />
      <div className="p-5 space-y-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-3 bg-gray-100 rounded" style={{ width: `${75 - i * 10}%` }} />
        ))}
      </div>
    </div>
  )
}


// ─────────────────────────────────────────────────────────────────────────────
// Icons (Heroicons outline, 16 × 16)
// ─────────────────────────────────────────────────────────────────────────────

const IconChat = () => (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round"
      d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 0 1 .865-.501 48.172 48.172 0 0 0 3.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z" />
  </svg>
)
const IconAlert = () => (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round"
      d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
  </svg>
)
const IconClock = () => (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
  </svg>
)
const IconCoin = () => (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round"
      d="M12 6v12m-3-2.818.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
  </svg>
)
const IconThumbDown = () => (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round"
      d="M7.498 15.25H4.372c-1.026 0-1.945-.694-2.054-1.715a12.137 12.137 0 0 1-.068-1.285c0-2.848.992-5.464 2.649-7.521C5.287 4.247 5.886 4 6.504 4h4.016a4.5 4.5 0 0 1 1.423.23l3.114 1.04a4.5 4.5 0 0 0 1.423.23h1.294M7.498 15.25c.618 0 .991.724.725 1.282A7.471 7.471 0 0 0 7.5 19.75 2.25 2.25 0 0 0 9.75 22a.75.75 0 0 0 .75-.75v-.633c0-.573.11-1.14.322-1.672.304-.76.93-1.33 1.653-1.715a9.04 9.04 0 0 0 2.86-2.4c.498-.634 1.226-1.08 2.032-1.08h.384m-10.253 1.5H9.7m8.075-9.75c.01.05.027.1.05.148.593 1.2.925 2.55.925 3.977 0 1.487-.36 2.89-.999 4.125m.023-8.25c-.076-.365.183-.75.575-.75h.908c.889 0 1.713.518 1.972 1.368.339 1.11.521 2.287.521 3.507 0 1.553-.295 3.036-.832 4.398-.306.774-1.086 1.227-1.918 1.227h-1.053c-.472 0-.745-.556-.499-.96a8.957 8.957 0 0 0 1.302-4.665c0-1.194-.232-2.333-.654-3.375Z" />
  </svg>
)
const IconRefresh = () => (
  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round"
      d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99" />
  </svg>
)


// ─────────────────────────────────────────────────────────────────────────────
// DashboardPage — main export
// ─────────────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const [metrics, setMetrics] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)
  // Incrementing this triggers a re-fetch without changing the URL
  const [fetchKey, setFetchKey] = useState(0)

  useEffect(() => {
    setLoading(true)
    setError(null)
    getDashboardMetrics()
      .then(setMetrics)
      .catch((e) => setError(friendlyError(e)))
      .finally(() => setLoading(false))
  }, [fetchKey])

  const refresh = () => setFetchKey((k) => k + 1)

  // Cost per review: divide total estimated cost by review count
  const costPerReview = metrics && metrics.total_chats > 0
    ? metrics.estimated_cost_usd / metrics.total_chats
    : 0

  // Escalation count for KPI sub-label
  const escalationCount = metrics
    ? Math.round(metrics.total_chats * metrics.escalation_rate / 100)
    : 0

  return (
    <div className="max-w-7xl mx-auto px-4 py-8 space-y-5">

      {/* ── Page header ──────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Analytics Dashboard</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Metrics computed from all review traces and reviewer feedback
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
        <div
          role="alert"
          className="flex items-center gap-3 rounded-xl border border-red-200
                     bg-red-50 px-5 py-3 text-sm text-red-700"
        >
          <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24"
               strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
          </svg>
          <span className="flex-1">Failed to load metrics: {error}</span>
          <button onClick={refresh} className="underline font-semibold hover:text-red-900">
            Retry
          </button>
        </div>
      )}

      {/* ── Empty state — no reviews yet ────────────────────────────────── */}
      {!loading && !error && metrics && metrics.total_chats === 0 && (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed
                        border-indigo-200 bg-indigo-50/60 px-6 py-8 text-center">
          <svg className="w-10 h-10 text-indigo-300" fill="none" viewBox="0 0 24 24"
               strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166
                 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 0 1
                 .865-.501 48.172 48.172 0 0 0 3.423-.379c1.584-.233 2.707-1.626
                 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12
                 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z" />
          </svg>
          <div>
            <p className="text-sm font-semibold text-indigo-700">No reviews yet</p>
            <p className="text-xs text-indigo-500 mt-0.5">
              Metrics will appear here once you submit your first deviation review.
            </p>
          </div>
          <a href="/chat"
             className="mt-1 inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs
                        font-semibold bg-indigo-600 hover:bg-indigo-700 text-white
                        transition-colors shadow-sm">
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24"
                 strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
            Submit a deviation review
          </a>
        </div>
      )}

      {/* ── Panels 1–5: KPI cards ─────────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        {loading ? (
          Array.from({ length: 5 }).map((_, i) => <SkeletonCard key={i} />)
        ) : metrics ? (
          <>
            {/* 1 · Total Chats */}
            <KpiCard
              label="Total Chats"
              value={metrics.total_chats.toLocaleString()}
              sub={`${metrics.total_tokens_used.toLocaleString()} tokens used`}
              icon={<IconChat />}
              accent="indigo"
            />

            {/* 2 · Escalation Rate */}
            <KpiCard
              label="Escalation Rate"
              value={`${metrics.escalation_rate}%`}
              sub={`${escalationCount} review${escalationCount !== 1 ? 's' : ''} escalated`}
              icon={<IconAlert />}
              accent={metrics.escalation_rate >= 50 ? 'red' : 'amber'}
            />

            {/* 3 · Avg Latency */}
            <KpiCard
              label="Avg Latency"
              value={`${(metrics.avg_latency_ms / 1000).toFixed(1)}s`}
              sub={`${metrics.avg_latency_ms.toFixed(0)} ms per review`}
              icon={<IconClock />}
              accent="cyan"
            />

            {/* 4 · Estimated Cost */}
            <KpiCard
              label="Est. API Cost"
              value={`$${metrics.estimated_cost_usd.toFixed(4)}`}
              sub={`$${costPerReview.toFixed(5)} / review`}
              icon={<IconCoin />}
              accent="emerald"
            />

            {/* 5 · Downvote Rate */}
            <KpiCard
              label="Downvote Rate"
              value={`${metrics.downvote_rate}%`}
              sub={metrics.downvote_rate === 0 ? 'No negative ratings' : 'of rated reviews'}
              icon={<IconThumbDown />}
              accent={metrics.downvote_rate >= 30 ? 'orange' : 'slate'}
            />
          </>
        ) : null}
      </div>

      {/* ── Panels 6 + 7: Charts ─────────────────────────────────────────── */}
      {loading ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <SkeletonChart tall className="lg:col-span-2" />
          <SkeletonChart />
        </div>
      ) : metrics ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

          {/* 6 · Chats per Day line chart */}
          <div className="lg:col-span-2 rounded-xl border border-gray-200 bg-white
                          shadow-sm overflow-hidden">
            <div className="flex items-center gap-2 px-5 py-3 border-b border-gray-100 bg-gray-50">
              <span aria-hidden="true" className="text-sm">📈</span>
              <h2 className="text-sm font-semibold text-gray-700">Reviews per Day</h2>
              <span className="ml-auto text-xs text-gray-400">last 7 days</span>
            </div>
            <div className="px-5 py-5">
              <DailyLineChart data={metrics.chats_last_7_days} />
            </div>
          </div>

          {/* 7 · Severity breakdown donut */}
          <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">
            <div className="flex items-center gap-2 px-5 py-3 border-b border-gray-100 bg-gray-50">
              <span aria-hidden="true" className="text-sm">🎯</span>
              <h2 className="text-sm font-semibold text-gray-700">Severity Breakdown</h2>
            </div>
            <div className="px-5 py-5 flex items-center justify-center min-h-[11rem]">
              <SeverityDonut breakdown={metrics.top_severity_breakdown} />
            </div>
          </div>

        </div>
      ) : null}

      {/* ── Cost methodology footnote ─────────────────────────────────────── */}
      {metrics && (
        <p className="text-[11px] text-gray-400 text-center pb-2">
          Cost estimate: input tokens × ${INPUT_PRICE_PER_MTOK}/MTok +
          output tokens × ${OUTPUT_PRICE_PER_MTOK}/MTok (Claude Haiku pricing).
          {' '}Total: {metrics.total_tokens_used.toLocaleString()} tokens across{' '}
          {metrics.total_chats} review{metrics.total_chats !== 1 ? 's' : ''}.
        </p>
      )}

    </div>
  )
}
