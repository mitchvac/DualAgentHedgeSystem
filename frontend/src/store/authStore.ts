import { create } from 'zustand'

interface AuthState {
  token: string | null
  username: string | null
  setAuth: (token: string, username: string) => void
  logout: () => void
  init: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  username: null,
  setAuth: (token, username) => {
    localStorage.setItem('hedgeswarm_token', token)
    localStorage.setItem('hedgeswarm_user', username)
    set({ token, username })
  },
  logout: () => {
    localStorage.removeItem('hedgeswarm_token')
    localStorage.removeItem('hedgeswarm_user')
    set({ token: null, username: null })
    window.location.href = '/login'
  },
  init: () => {
    const token = localStorage.getItem('hedgeswarm_token')
    const username = localStorage.getItem('hedgeswarm_user')
    if (token) set({ token, username })
  },
}))
