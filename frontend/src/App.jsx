import { useState } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import NavBar from './components/NavBar.jsx'
import LoginPage from './pages/LoginPage.jsx'
import ChatPage from './pages/ChatPage.jsx'
import ResultsPage from './pages/ResultsPage.jsx'
import DashboardPage from './pages/DashboardPage.jsx'
import EvalsPage from './pages/EvalsPage.jsx'
import FeedbackPage from './pages/FeedbackPage.jsx'

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

  if (!loggedIn) return <LoginPage onLogin={handleLogin} />

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      {/* Sticky top navigation */}
      <NavBar username={username} onLogout={handleLogout} />

      {/* Page content — grows to fill remaining height */}
      <main className="flex-1">
        <Routes>
          <Route path="/"          element={<Navigate to="/chat" replace />} />
          <Route path="/chat"      element={<ChatPage />} />
          <Route path="/results"   element={<ResultsPage />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/evals"     element={<EvalsPage />} />
          <Route path="/feedback"  element={<FeedbackPage />} />
          {/* Catch-all */}
          <Route path="*"          element={<Navigate to="/chat" replace />} />
        </Routes>
      </main>
    </div>
  )
}
