import { NavLink } from 'react-router-dom'

const NAV_LINKS = [
  { to: '/chat',      label: 'Chat' },
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/evals',     label: 'Evals' },
  { to: '/feedback',  label: 'Feedback Queue' },
]

export default function NavBar({ username = '', onLogout }) {
  return (
    <header className="sticky top-0 z-50 bg-indigo-900 shadow-lg">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">

          {/* Brand */}
          <div className="flex items-center gap-3 min-w-0">
            <span
              className="flex-shrink-0 w-8 h-8 rounded-full bg-indigo-400 flex items-center justify-center text-white text-xs font-bold select-none"
              aria-hidden="true"
            >
              Rx
            </span>
            <span className="text-white font-semibold text-sm sm:text-base leading-tight truncate">
              GMP Deviation Review — AI Assistant
            </span>
          </div>

          {/* Desktop nav + user */}
          <div className="hidden sm:flex items-center gap-1">
            <nav className="flex items-center gap-1" aria-label="Main navigation">
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

            {/* User badge + sign out */}
            {username && (
              <div className="flex items-center gap-3 ml-4 pl-4 border-l border-indigo-700">
                <span className="text-indigo-200 text-sm">👤 {username}</span>
                <button
                  onClick={onLogout}
                  className="text-xs text-indigo-300 hover:text-white transition-colors duration-150"
                >
                  Sign out
                </button>
              </div>
            )}
          </div>

          {/* Mobile nav — horizontal scroll strip below brand on small screens */}
        </div>

        {/* Mobile nav row */}
        <div className="sm:hidden flex items-center gap-1 pb-2 overflow-x-auto" aria-label="Main navigation">
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
          {username && (
            <button
              onClick={onLogout}
              className="flex-shrink-0 ml-auto text-xs text-indigo-300 hover:text-white transition-colors duration-150 px-2"
            >
              Sign out
            </button>
          )}
        </div>
      </div>
    </header>
  )
}
