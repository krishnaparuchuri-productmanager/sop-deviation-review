import { NavLink } from 'react-router-dom'

const NAV_LINKS = [
  { to: '/chat',      label: 'Chat' },
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/evals',     label: 'Evals' },
  { to: '/feedback',  label: 'Feedback Queue' },
]

export default function NavBar() {
  return (
    <header className="sticky top-0 z-50 bg-indigo-900 shadow-lg">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">

          {/* Brand */}
          <div className="flex items-center gap-3 min-w-0">
            {/* Pill icon */}
            <span
              className="flex-shrink-0 w-8 h-8 rounded-full bg-indigo-400 flex items-center justify-center text-white text-xs font-bold select-none"
              aria-hidden="true"
            >
              Rx
            </span>
            <span className="text-white font-semibold text-sm sm:text-base leading-tight truncate">
              SOP Deviation Review Assistant
            </span>
          </div>

          {/* Desktop nav */}
          <nav className="hidden sm:flex items-center gap-1" aria-label="Main navigation">
            {NAV_LINKS.map(({ to, label }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  [
                    'px-3 py-2 rounded-md text-sm font-medium transition-colors duration-150',
                    isActive
                      ? 'bg-indigo-700 text-white'
                      : 'text-indigo-200 hover:bg-indigo-800 hover:text-white',
                  ].join(' ')
                }
              >
                {label}
              </NavLink>
            ))}
          </nav>

          {/* Mobile nav — horizontal scroll strip below brand on small screens */}
        </div>

        {/* Mobile nav row */}
        <div className="sm:hidden flex gap-1 pb-2 overflow-x-auto" aria-label="Main navigation">
          {NAV_LINKS.map(({ to, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                [
                  'flex-shrink-0 px-3 py-1.5 rounded-md text-sm font-medium transition-colors duration-150',
                  isActive
                    ? 'bg-indigo-700 text-white'
                    : 'text-indigo-200 hover:bg-indigo-800 hover:text-white',
                ].join(' ')
              }
            >
              {label}
            </NavLink>
          ))}
        </div>
      </div>
    </header>
  )
}
