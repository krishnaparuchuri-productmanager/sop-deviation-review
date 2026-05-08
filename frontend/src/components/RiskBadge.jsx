/**
 * RiskBadge — coloured pill for severity levels.
 *
 * Props:
 *   severity  {string}  "High" | "Medium" | "Low"
 *   size      {string}  "sm" | "md" (default "md")
 */

const STYLES = {
  High:   'bg-red-100   text-red-700   ring-red-200',
  Medium: 'bg-amber-100 text-amber-700 ring-amber-200',
  Low:    'bg-green-100 text-green-700 ring-green-200',
}

const DOTS = {
  High:   'bg-red-500',
  Medium: 'bg-amber-500',
  Low:    'bg-green-500',
}

export default function RiskBadge({ severity, size = 'md' }) {
  const colours = STYLES[severity] ?? 'bg-gray-100 text-gray-600 ring-gray-200'
  const dot     = DOTS[severity]   ?? 'bg-gray-400'
  const text    = size === 'sm' ? 'text-xs px-2 py-0.5' : 'text-sm px-3 py-1'

  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full font-semibold ring-1 ring-inset ${colours} ${text}`}>
      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${dot}`} aria-hidden="true" />
      {severity ?? 'Unknown'}
    </span>
  )
}
