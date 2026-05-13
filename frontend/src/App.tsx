import { Routes, Route, Navigate } from 'react-router-dom'
import { useEffect } from 'react'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Portfolio from './pages/Portfolio'
import Analytics from './pages/Analytics'
import Trades from './pages/Trades'
import Agents from './pages/Agents'
import Leaderboard from './pages/Leaderboard'
import ExchangeMonitor from './pages/ExchangeMonitor'
import Settings from './pages/Settings'
import Wallet from './pages/Wallet'
import Billing from './pages/Billing'
import Login from './pages/Login'
import Register from './pages/Register'
import { useAuthStore } from './store/authStore'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { token } = useAuthStore()
  if (!token) return <Navigate to="/login" replace />
  return <>{children}</>
}

function AppInitializer({ children }: { children: React.ReactNode }) {
  const { init } = useAuthStore()
  useEffect(() => { init() }, [init])
  return <>{children}</>
}

export default function App() {
  return (
    <AppInitializer>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route
          path="/*"
          element={
            <ProtectedRoute>
              <Layout>
                <Routes>
                  <Route path="/" element={<Dashboard />} />
                  <Route path="/portfolio" element={<Portfolio />} />
                  <Route path="/analytics" element={<Analytics />} />
                  <Route path="/trades" element={<Trades />} />
                  <Route path="/agents" element={<Agents />} />
                  <Route path="/leaderboard" element={<Leaderboard />} />
                  <Route path="/exchange-monitor" element={<ExchangeMonitor />} />
                  <Route path="/wallet" element={<Wallet />} />
                  <Route path="/billing" element={<Billing />} />
                  <Route path="/settings" element={<Settings />} />
                </Routes>
              </Layout>
            </ProtectedRoute>
          }
        />
      </Routes>
    </AppInitializer>
  )
}
