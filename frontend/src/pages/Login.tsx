import { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { TrendingUp, Lock, User, Eye, EyeOff, Chrome, Github } from 'lucide-react'
import { useAuthStore } from '@/store/authStore'

export default function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPass, setShowPass] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const { setAuth } = useAuthStore()

  // Handle OAuth callback token in URL
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const token = params.get('token')
    const user = params.get('username')
    if (token && user) {
      localStorage.setItem('hedgeswarm_token', token)
      setAuth(token, user, user, '')
      // Clean URL
      window.history.replaceState({}, '', '/')
      navigate('/')
    }
  }, [navigate, setAuth])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      const formData = new URLSearchParams()
      formData.append('username', username)
      formData.append('password', password)

      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: formData.toString(),
      })

      if (!res.ok) {
        const body = await res.text()
        throw new Error(body || 'Login failed')
      }

      const data = await res.json()
      localStorage.setItem('hedgeswarm_token', data.access_token)
      setAuth(data.access_token, data.username, data.username, '')
      navigate('/')
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleOAuth = async (provider: string) => {
    setError('')
    setLoading(true)
    try {
      const res = await fetch(`/api/auth/oauth/${provider}`)
      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.detail || `${provider} login not configured`)
      }
      const data = await res.json()
      window.location.href = data.auth_url
    } catch (err: any) {
      setError(err.message)
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#0a0a0f] flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-orange-500 to-orange-600 flex items-center justify-center mx-auto mb-4 shadow-lg shadow-orange-500/20">
            <TrendingUp className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-white mb-1">HedgeSwarm</h1>
          <p className="text-sm text-gray-500">Dual-Agent Composite Hedge System</p>
        </div>

        <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-6">
          {/* Social Login */}
          <div className="grid grid-cols-3 gap-2 mb-4">
            <button
              onClick={() => handleOAuth('google')}
              disabled={loading}
              className="flex items-center justify-center gap-2 bg-[#0a0a0f] border border-[#2a2a35] hover:border-gray-600 text-white py-2.5 rounded-xl transition-all duration-200 disabled:opacity-50"
              title="Sign in with Google"
            >
              <Chrome className="w-4 h-4 text-red-400" />
              <span className="text-xs">Google</span>
            </button>
            <button
              onClick={() => handleOAuth('github')}
              disabled={loading}
              className="flex items-center justify-center gap-2 bg-[#0a0a0f] border border-[#2a2a35] hover:border-gray-600 text-white py-2.5 rounded-xl transition-all duration-200 disabled:opacity-50"
              title="Sign in with GitHub"
            >
              <Github className="w-4 h-4" />
              <span className="text-xs">GitHub</span>
            </button>
            <button
              onClick={() => handleOAuth('facebook')}
              disabled={loading}
              className="flex items-center justify-center gap-2 bg-[#0a0a0f] border border-[#2a2a35] hover:border-gray-600 text-white py-2.5 rounded-xl transition-all duration-200 disabled:opacity-50"
              title="Sign in with Facebook"
            >
              <svg className="w-4 h-4 text-blue-400" fill="currentColor" viewBox="0 0 24 24">
                <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/>
              </svg>
              <span className="text-xs">Facebook</span>
            </button>
          </div>

          <div className="flex items-center gap-3 mb-4">
            <div className="flex-1 h-px bg-[#2a2a35]" />
            <span className="text-xs text-gray-600">or with username</span>
            <div className="flex-1 h-px bg-[#2a2a35]" />
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-gray-400 uppercase tracking-wider mb-2">
                Username
              </label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full bg-[#0a0a0f] border border-[#2a2a35] rounded-xl py-2.5 pl-10 pr-4 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-orange-500/50 focus:ring-1 focus:ring-orange-500/20 transition-all"
                  placeholder="Username"
                  required
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-400 uppercase tracking-wider mb-2">
                Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
                <input
                  type={showPass ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full bg-[#0a0a0f] border border-[#2a2a35] rounded-xl py-2.5 pl-10 pr-10 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-orange-500/50 focus:ring-1 focus:ring-orange-500/20 transition-all"
                  placeholder="Password"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPass(!showPass)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
                >
                  {showPass ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {error && (
              <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-2.5 text-sm text-red-400">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-400 hover:to-orange-500 text-white font-semibold py-2.5 rounded-xl transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-orange-500/20"
            >
              {loading ? 'Signing in...' : 'Sign In'}
            </button>
          </form>

          <div className="mt-4 pt-4 border-t border-[#2a2a35] flex flex-col items-center gap-2">
            <Link
              to="/register"
              className="text-sm text-orange-400 hover:text-orange-300 transition-colors font-medium"
            >
              Create Account
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}
