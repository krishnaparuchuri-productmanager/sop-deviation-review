import { useState } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import NavBar from './components/NavBar.jsx'
import LoginPage from './pages/LoginPage.jsx'
import ChatPage from './pages/ChatPage.jsx'
import ResultsPage from './pages/ResultsPage.jsx'
import DashboardPage from './pages/DashboardPage.jsx'
import EvalsPage from './pages/EvalsPage.jsx'
import FeedbackPage from './pages/FeedbackPage.jsx'

/**
 * ProtectedRoute — redirects unauthenticated users to /login,
 * preserving the originally-requested path so they land there after signing in.
 */
function ProtectedRoute({ loggedIn, children }) {
  const location = useLocation()
  if (!loggedIn) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }
  return children
}

export default function App() {
  const [loggedIn, setLoggedIn] = useState(() => !!sessionStorage.getItem('gmp_user'))
  const [username, setUsername] = useState(() => sessionStorage.getItem('gmp_user') || '')

  function handleLogin(name) {
    sessionStorage.setItem('gmp_user', name)
    setUsername(name)
    setLoggedIn(true)
  }

  function handleLogout() {
    sessionStorage.removeItem('gmp_user')
    setUsername('')
    setLoggedIn(false)
  }

  return (
    <Routes>
      {/* Public: login page — already logged in sends to /chat */}
      <Route
        path="/login"
        element={
          loggedIn
            ? <Navigate to="/chat" replace />
            : <LoginPage onLogin={handleLogin} />
        }
      />

      {/* Protected shell — all app routes share the NavBar */}
      <Route
        path="/*"
        element={
          <ProtectedRoute loggedIn={loggedIn}>
            <div className="min-h-screen flex flex-col bg-gray-50">
              <NavBar username={username} onLogout={handleLogout} />
              <main className="flex-1">
                <Routes>
                  <Route path="/"          element={<Navigate to="/chat" replace />} />
                  <Route path="/chat"      element={<ChatPage />} />
                  <Route path="/results"   element={<ResultsPage />} />
                  <Route path="/dashboard" element={<DashboardPage />} />
                  <Route path="/evals"     element={<EvalsPage />} />
                  <Route path="/feedback"  element={<FeedbackPage />} />
                  <Route path="*"          element={<Navigate to="/chat" replace />} />
                </Routes>
              </main>
            </div>
          </ProtectedRoute>
        }
      />
    </Routes>
  )
}
