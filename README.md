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

The original `database.sql` is preserved as the base schema. Apply the migrations in order:

1. `supabase/migrations/0002_phase1_hardening.sql` — organization-scoped RLS policies.
2. `supabase/migrations/0003_agricultural_observations.sql` — FAOSTAT-shaped observations and the source catalog.
3. `supabase/migrations/0004_external_intelligence.sql` — food catalog, nutrients, vessels, AIS positions, Sentinel-2 scenes and indices, AI enrichment, and ingestion run history.

Then optionally apply `supabase/seed.sql` for the synthetic demo network and
`supabase/seed_operations.sql` for 90 days of sales history plus inbound shipments (both label
their rows so real integrations stay distinguishable). Only the publishable key belongs in browser
configuration. The service-role key must stay in the API runtime secret store and is intentionally
absent from this repository.

## External data connectors

`services/connectors` ingests public reference data into Supabase — FAOSTAT food balance sheets and
crop/livestock production, Open Food Facts products, USDA FoodData Central foods and nutrients, live
AIS vessel tracking, and Sentinel-2 crop-health indices — and can classify products through
OpenRouter. See `services/connectors/README.md` for sources, configuration, and commands.

## Operator access

Sign-in uses Supabase Auth, and every API request carries the operator's access token so row level
security decides what is visible. An account also needs a `profiles` row that carries its
organization and role:

```sql
-- 1. create the user in Supabase Auth (dashboard or the admin API)
-- 2. link the account to its organization and role
insert into public.profiles (id, organization_id, full_name, role)
values ('<auth-user-id>', '<organization-id>', 'Operations Demo', 'admin');
```

The API exposes reads (`/api/inventory`, `/api/recommendations`, `/api/signals`, `/api/vessels`, …)
and role-gated writes (`/api/recommendations/{id}/approve`, `/api/forecast/run`,
`/api/purchase-orders`). `GET /api/ready` reports whether the repository can reach Supabase.

Architecture, ERD, API contracts, event schemas, ML pipeline, agent tools, Docker topology, and roadmap are in `docs/architecture/`.
