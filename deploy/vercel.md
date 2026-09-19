# Deploying the web console to Vercel

The Next.js app is the only part that belongs on Vercel. The FastAPI services and the connectors run
in Docker on the `metademic` host and are reached over HTTPS (see `CREDENTIALS.md` for the current
public URL and how to redeploy them).

## Before you start

1. The API is running and reachable from the internet, e.g.
   `curl https://<host>:8443/api/health` returns `"service":"sentinelstock-api"`.
2. You know the Supabase URL and publishable key for the project.

## Import the project

1. **Add New → Project** in Vercel and import this repository.
2. Set **Root Directory** to `apps/web` (leave "Include files outside the root directory" enabled so
   the npm workspace at the repository root is installed).
3. Framework preset: **Next.js** (detected automatically). Build command `npm run build`, output
   directory `.next` — both defaults.
4. If the install step cannot find workspace dependencies, set **Install Command** to
   `npm install --workspace apps/web --include-workspace-root` and redeploy.

## Environment variables

Set these for Production and Preview:

| Name | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | `https://metademic.tail6cb521.ts.net:8443` (your deployed API) |
| `NEXT_PUBLIC_SUPABASE_URL` | `https://<project-ref>.supabase.co` |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | the project's publishable key |

`NEXT_PUBLIC_*` values are embedded in the browser bundle, so never put the service-role key or any
other private secret in them. The browser only ever holds the operator's Supabase session token.

Changing `NEXT_PUBLIC_API_URL` requires a **redeploy** — Next inlines the value at build time.

## After the first deploy

1. Sign in at `https://<your-app>.vercel.app/login` with an account from `CREDENTIALS.md`. The
   dashboard should load live rows; if it shows a red banner, the banner names the API URL the build
   is using, which is usually a wrong or missing `NEXT_PUBLIC_API_URL`.
2. Lock down CORS: `services/api/app/main.py` currently sets `allow_origins=["*"]`. Restrict it to
   your Vercel domain, then rebuild and restart the API container on the host:
   `docker compose up -d --build api`.
3. Optional: add a custom domain in Vercel and put it in the CORS allow-list.

## What does not go on Vercel

- `services/api` and `services/forecasting` — containers, hosted on `metademic`.
- `services/connectors` — long-running jobs; run them on the host (cron or
  `docker compose run --rm connectors python -m app.worker all`).
- The dashboard's "Ask the console" box needs the local Needle model's cache directory, which
  serverless platforms do not provide; it runs where the API runs.
