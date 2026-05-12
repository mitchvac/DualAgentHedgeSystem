// ═══════════════════════════════════════════════════════════════════════════════
// Environment Configuration — Vite injects env vars at build time
// ═══════════════════════════════════════════════════════════════════════════════

export const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL || '';
export const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY || '';

export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:3003';

// Validate that Supabase config is present
if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
  console.warn(
    '[Config] VITE_SUPABASE_URL and/or VITE_SUPABASE_ANON_KEY are not set. ' +
    'Authentication will not work until these environment variables are configured.'
  );
}
