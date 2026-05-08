import { Routes, Route, Navigate } from 'react-router-dom'
import NavBar from './components/NavBar.jsx'
import ChatPage from './pages/ChatPage.jsx'
import ResultsPage from './pages/ResultsPage.jsx'
import DashboardPage from './pages/DashboardPage.jsx'
import EvalsPage from './pages/EvalsPage.jsx'
import FeedbackPage from './pages/FeedbackPage.jsx'

export default function App() {
  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      {/* Sticky top navigation */}
      <NavBar />

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
