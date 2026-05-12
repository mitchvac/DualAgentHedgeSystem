// ═══════════════════════════════════════════════════════════════════════════════
// Supabase Client — Authentication & Database
// ═══════════════════════════════════════════════════════════════════════════════

import { createClient, SupabaseClient, AuthChangeEvent, Session } from '@supabase/supabase-js';
import { SUPABASE_URL, SUPABASE_ANON_KEY } from './config';

let supabase: SupabaseClient | null = null;

export function getSupabaseClient(): SupabaseClient {
  if (!supabase) {
    if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
      throw new Error(
        'Supabase is not configured. Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY environment variables.'
      );
    }
    supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
      auth: {
        autoRefreshToken: true,
        persistSession: true,
        detectSessionInUrl: true,
      },
    });
  }
  return supabase;
}

// ── Auth Helpers ──────────────────────────────────────────────────────────────

export async function signInWithEmail(email: string, password: string) {
  const client = getSupabaseClient();
  const { data, error } = await client.auth.signInWithPassword({ email, password });
  if (error) throw error;
  return data;
}

export async function signUpWithEmail(email: string, password: string, metadata?: { username?: string }) {
  const client = getSupabaseClient();
  const { data, error } = await client.auth.signUp({
    email,
    password,
    options: { data: metadata },
  });
  if (error) throw error;
  return data;
}

export async function signInWithOAuth(provider: 'github' | 'google' | 'twitter') {
  const client = getSupabaseClient();
  const { data, error } = await client.auth.signInWithOAuth({
    provider,
    options: {
      redirectTo: `${window.location.origin}/auth/callback`,
    },
  });
  if (error) throw error;
  return data;
}

export async function signOut() {
  const client = getSupabaseClient();
  const { error } = await client.auth.signOut();
  if (error) throw error;
}

export async function getCurrentSession(): Promise<Session | null> {
  const client = getSupabaseClient();
  const { data, error } = await client.auth.getSession();
  if (error) {
    console.error('[Supabase] getSession error:', error.message);
    return null;
  }
  return data.session;
}

export async function getCurrentUser() {
  const session = await getCurrentSession();
  return session?.user ?? null;
}

export function getAuthToken(): string | null {
  const client = getSupabaseClient();
  // Access token from current session
  const session = client.auth.getSession();
  // Note: getSession is async; for synchronous access use localStorage
  return localStorage.getItem('sb-' + new URL(SUPABASE_URL).hostname + '-auth-token')
    ? JSON.parse(localStorage.getItem('sb-' + new URL(SUPABASE_URL).hostname + '-auth-token')!).access_token
    : null;
}

// ── Auth State Listener ───────────────────────────────────────────────────────

export function onAuthStateChange(
  callback: (event: AuthChangeEvent, session: Session | null) => void
) {
  const client = getSupabaseClient();
  const { data } = client.auth.onAuthStateChange(callback);
  return data.subscription;
}

// ── Database Helpers (RLS-protected) ──────────────────────────────────────────

export async function getTrades(userId: string, limit = 100) {
  const client = getSupabaseClient();
  const { data, error } = await client
    .from('trades')
    .select('*')
    .eq('user_id', userId)
    .order('created_at', { ascending: false })
    .limit(limit);
  if (error) throw error;
  return data;
}

export async function getPositions(userId: string) {
  const client = getSupabaseClient();
  const { data, error } = await client.from('positions').select('*').eq('user_id', userId);
  if (error) throw error;
  return data;
}

export async function getEquityHistory(userId: string, limit = 100) {
  const client = getSupabaseClient();
  const { data, error } = await client
    .from('equity_history')
    .select('*')
    .eq('user_id', userId)
    .order('created_at', { ascending: false })
    .limit(limit);
  if (error) throw error;
  return data;
}

export async function upsertSetting(userId: string, key: string, value: unknown) {
  const client = getSupabaseClient();
  const { error } = await client
    .from('system_settings')
    .upsert({ user_id: userId, key, value }, { onConflict: 'user_id,key' });
  if (error) throw error;
}

export async function getSettings(userId: string) {
  const client = getSupabaseClient();
  const { data, error } = await client.from('system_settings').select('*').eq('user_id', userId);
  if (error) throw error;
  return data;
}
