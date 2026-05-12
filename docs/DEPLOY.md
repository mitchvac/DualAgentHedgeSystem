# Deployment Guide

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│   Vercel    │────▶│   Supabase   │────▶│  FastAPI Backend│
│  (Frontend) │     │ (Auth + DB)  │     │  (Railway/etc)  │
└─────────────┘     └──────────────┘     └─────────────────┘
```

- **Frontend**: React + Vite → Vercel (auto-deploy on git push)
- **Auth**: Supabase Auth (email/password + GitHub OAuth)
- **Database**: Supabase PostgreSQL with RLS
- **Backend**: FastAPI (deploy to Railway, Render, or Fly.io)

## 1. Deploy Frontend to Vercel

### Option A: GitHub Actions (Recommended)

1. Push your code to GitHub
2. Add these secrets to your GitHub repo (**Settings → Secrets → Actions**):
   - `VERCEL_TOKEN` — from [vercel.com/account/tokens](https://vercel.com/account/tokens)
   - `VERCEL_ORG_ID` — from `vercel teams ls` or project settings
   - `VERCEL_PROJECT_ID` — from `vercel project ls` or project settings
   - `VITE_SUPABASE_URL` — your Supabase project URL
   - `VITE_SUPABASE_ANON_KEY` — your Supabase anon key

3. The workflow in `.github/workflows/deploy-vercel.yml` runs automatically on every push to `main`.

### Option B: Vercel CLI

```bash
npm i -g vercel
vercel --prod
# Set environment variables in Vercel dashboard: Project → Settings → Environment Variables
```

## 2. Deploy Backend (Choose One)

### Railway
```bash
npm i -g @railway/cli
railway login
railway init
railway up
# Add environment variables in Railway dashboard
```

### Render
1. Connect your GitHub repo on [render.com](https://render.com)
2. Create a new Web Service
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn app_fullstack:app --host 0.0.0.0 --port $PORT`
5. Add environment variables

### Fly.io
```bash
fly launch
fly deploy
# Add secrets: fly secrets set SUPABASE_URL=... SUPABASE_ANON_KEY=...
```

## 3. Environment Variables for Backend

```bash
SUPABASE_URL=https://<your-project>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<server-side-only>
JWT_SECRET_KEY=<legacy-fallback>
PAPER_TRADING=true
OPENAI_API_KEY=sk-...
```

## 4. Verify Deployment

1. Open your Vercel URL
2. Register/login via Supabase Auth
3. Check that trades, positions, and equity are user-scoped
4. Open browser DevTools → Network → verify `Authorization: Bearer <token>` headers

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `401 Unauthorized` | Check `VITE_SUPABASE_ANON_KEY` is set in Vercel env vars |
| `CORS error` | Add your Vercel domain to backend CORS origins |
| `RLS violation` | Ensure backend uses `service_role` key for admin ops |
| `Realtime not working` | Enable Realtime on tables in Supabase Dashboard |
