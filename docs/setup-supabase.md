# Supabase Setup Guide

## 1. Create a Supabase Project

```bash
# Using CLI (requires Docker running)
supabase login
supabase projects create DualAgentHedgeSystem --org-id <your-org-id> --region us-east-1 --plan free

# Or use the web UI: https://app.supabase.com
```

## 2. Link Your Project

```bash
supabase link --project-ref <your-project-ref>
```

## 3. Push the Database Schema

```bash
supabase db push
```

This applies all migrations from `supabase/migrations/` including:
- All tables (trades, positions, equity_history, agent_votes, arb_opportunities, system_settings, custom_exchanges)
- Row Level Security (RLS) policies — **iron-clad per-user isolation**
- Realtime publication for live WebSocket updates
- Auto-create profile on signup trigger

## 4. Configure GitHub OAuth (Optional but Recommended)

1. Go to [GitHub Developer Settings](https://github.com/settings/developers)
2. Create a new OAuth App:
   - **Authorization callback URL**: `https://<your-project-ref>.supabase.co/auth/v1/callback`
3. Copy the **Client ID** and **Client Secret**
4. In Supabase Dashboard: **Authentication → Providers → GitHub**
   - Enable GitHub
   - Paste Client ID and Secret
   - Save

## 5. Get Your API Keys

In Supabase Dashboard → **Project Settings → API**:
- `SUPABASE_URL` — Project URL
- `SUPABASE_ANON_KEY` — `anon` public key (safe for frontend)
- `SUPABASE_SERVICE_ROLE_KEY` — `service_role` key (**server-side only**)

## 6. Environment Variables

Create `.env` from `.env.example` and fill in:

```bash
SUPABASE_URL=https://<your-project-ref>.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
GITHUB_CLIENT_ID=your-github-app-id
GITHUB_CLIENT_SECRET=your-github-app-secret
```

For the frontend (Vite), prefix with `VITE_`:
```bash
VITE_SUPABASE_URL=$SUPABASE_URL
VITE_SUPABASE_ANON_KEY=$SUPABASE_ANON_KEY
```

## 7. Verify RLS is Active

```sql
-- Run in Supabase SQL Editor
SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname = 'public';
-- Should show rowsecurity = true for all tables
```

## 8. Enable Realtime (if not already)

In Supabase Dashboard → **Database → Realtime**, ensure these tables are enabled:
- `trades`
- `positions`
- `equity_history`
- `arb_opportunities`

## Next Steps

- [Deploy to Vercel](./DEPLOY.md)
- [Backend Migration](./backend-migration.md) (SQLite → PostgreSQL)
