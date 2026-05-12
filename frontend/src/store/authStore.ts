import { create } from 'zustand'
import { supabase } from '@/lib/supabase'

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

  logout: async () => {
    await supabase.auth.signOut()
    set({ token: null, userId: null, username: null, email: null, isLoading: false })
    window.location.href = '/login'
  },

  init: async () => {
    // Listen to auth state changes
    supabase.auth.onAuthStateChange((event, session) => {
      if (session) {
        set({
          token: session.access_token,
          userId: session.user.id,
          username: session.user.user_metadata?.username || session.user.email || '',
          email: session.user.email || '',
          isLoading: false,
        })
      } else {
        set({ token: null, userId: null, username: null, email: null, isLoading: false })
      }
    })

    // Check existing session
    const { data } = await supabase.auth.getSession()
    if (data.session) {
      set({
        token: data.session.access_token,
        userId: data.session.user.id,
        username: data.session.user.user_metadata?.username || data.session.user.email || '',
        email: data.session.user.email || '',
        isLoading: false,
      })
    } else {
      set({ isLoading: false })
    }
  },
}))
