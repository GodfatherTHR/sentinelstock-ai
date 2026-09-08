# SentinelStock AI

SentinelStock AI is a production-oriented inventory and supply-chain intelligence monorepo. The current implementation covers the Phase 1 operator dashboard and approval-safe decision API, plus the Phase 2 forecasting service seam.

## Run locally

```powershell
Copy-Item .env.example .env.local
npm install
npm run dev
```

The dashboard runs at `http://localhost:3000`. If `NEXT_PUBLIC_API_URL` is not set, it uses clearly labeled synthetic demo data. To run the Python services directly:

```powershell
py -3 -m pip install -r services/api/requirements.txt
py -3 -m uvicorn app.main:app --app-dir services/api --reload --port 8000
py -3 -m uvicorn app.main:app --app-dir services/forecasting --reload --port 8001
```

Or use Docker Compose:

```powershell
docker compose up --build
```

## Verify

```powershell
npm run build
npm run lint
py -3 -m pytest -q services/api
py -3 -m pytest -q services/forecasting
py -3 -m pytest -q services/connectors
```

## Supabase setup

The original `database.sql` is preserved as the base schema. Apply `supabase/migrations/0002_phase1_hardening.sql` to complete organization-scoped RLS policies, then optionally apply `supabase/seed.sql` for synthetic data. Only the publishable key belongs in browser configuration. The service-role key must stay in the API runtime secret store and is intentionally absent from this repository.

Architecture, ERD, API contracts, event schemas, ML pipeline, agent tools, Docker topology, and roadmap are in `docs/architecture/`.
