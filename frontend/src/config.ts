// ═══════════════════════════════════════════════════════════════════════════════
// Environment Configuration — Vite injects env vars at build time
// ═══════════════════════════════════════════════════════════════════════════════

/// <reference types="vite/client" />

export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:3003';
