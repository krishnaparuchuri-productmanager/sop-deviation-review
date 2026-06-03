/**
 * LoginPage.jsx — Demo login screen for the GMP Deviation Review Assistant.
 *
 * No real authentication — any username and password of ≥ 4 characters is
 * accepted. Session is persisted in sessionStorage so a page refresh keeps
 * the user logged in within the same browser tab.
 */

import { useState } from 'react'

export default function LoginPage({ onLogin }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [errors,   setErrors]   = useState({})
  const [shake,    setShake]    = useState(false)

  function validate() {
    const e = {}
    if (username.trim().length < 4) e.username = 'Username must be at least 4 characters.'
    if (password.length < 4)        e.password = 'Password must be at least 4 characters.'
    return e
  }

  function handleSubmit(ev) {
    ev.preventDefault()
    const e = validate()
    if (Object.keys(e).length) {
      setErrors(e)
      setShake(true)
      setTimeout(() => setShake(false), 500)
      return
    }
    setErrors({})
    onLogin(username.trim())
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-indigo-950 via-indigo-900 to-indigo-800">
      <div
        className={`bg-white rounded-2xl shadow-2xl w-full max-w-md px-10 py-10 ${shake ? 'animate-shake' : ''}`}
      >
        {/* Logo */}
        <div className="flex justify-center mb-6">
          <div className="w-14 h-14 rounded-2xl bg-indigo-600 flex items-center justify-center text-white font-bold text-2xl shadow-lg">
            Rx
          </div>
        </div>

        {/* Title */}
        <h1 className="text-center text-2xl font-bold text-gray-900 mb-1">
          GMP Deviation Review
        </h1>
        <p className="text-center text-sm text-gray-500 mb-8">
          AI-powered pharmaceutical compliance assistant
        </p>

        {/* Form */}
        <form onSubmit={handleSubmit} noValidate className="space-y-5">
          {/* Username */}
          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1.5">
              Username
            </label>
            <input
              type="text"
              autoComplete="username"
              placeholder="Enter username"
              value={username}
              onChange={e => setUsername(e.target.value)}
              className={`w-full px-4 py-2.5 rounded-lg border text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 transition
                ${errors.username ? 'border-red-400 bg-red-50' : 'border-gray-300'}`}
            />
            {errors.username && (
              <p className="mt-1 text-xs text-red-500">{errors.username}</p>
            )}
          </div>

          {/* Password */}
          <div>
            <label className="block text-xs font-semibold text-gray-600 mb-1.5">
              Password
            </label>
            <input
              type="password"
              autoComplete="current-password"
              placeholder="Enter password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              className={`w-full px-4 py-2.5 rounded-lg border text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 transition
                ${errors.password ? 'border-red-400 bg-red-50' : 'border-gray-300'}`}
            />
            {errors.password && (
              <p className="mt-1 text-xs text-red-500">{errors.password}</p>
            )}
          </div>

          <button
            type="submit"
            className="w-full py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold rounded-lg text-sm transition-colors duration-150 mt-2"
          >
            Sign In
          </button>
        </form>

        <p className="text-center text-xs text-gray-400 mt-6">
          Demo mode · any credentials (min 4 chars each)
        </p>
      </div>

      {/* Shake keyframe — injected once */}
      <style>{`
        @keyframes shake {
          0%, 100% { transform: translateX(0); }
          20%, 60%  { transform: translateX(-8px); }
          40%, 80%  { transform: translateX( 8px); }
        }
        .animate-shake { animation: shake 0.4s ease; }
      `}</style>
    </div>
  )
}
