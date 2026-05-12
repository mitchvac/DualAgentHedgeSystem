import { create } from 'zustand'

interface AuthState {
  token: string | null
  userId: string | null
  username: string | null
  email: string | null
  isLoading: boolean
  setAuth: (token: string, userId: string, username: string, email: string) => void
  logout: () => void
  init: () => Promise<void>
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  userId: null,
  username: null,
  email: null,
  isLoading: true,

  setAuth: (token, userId, username, email) => {
    set({ token, userId, username, email, isLoading: false })
  },

  logout: () => {
    localStorage.removeItem('hedgeswarm_token')
    set({ token: null, userId: null, username: null, email: null, isLoading: false })
    window.location.href = '/login'
  },

  init: async () => {
    const token = localStorage.getItem('hedgeswarm_token')
    if (token) {
      try {
        const res = await fetch('/api/auth/me', {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (res.ok) {
          const data = await res.json()
          set({
            token,
            userId: data.username,
            username: data.username,
            email: '',
            isLoading: false,
          })
          return
        }
      } catch {
        // fall through
      }
      localStorage.removeItem('hedgeswarm_token')
    }
    set({ isLoading: false })
  },
}))
