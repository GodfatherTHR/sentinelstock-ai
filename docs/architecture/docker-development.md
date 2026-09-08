# Docker Development Architecture

Compose runs a FastAPI API and Next.js web app in demo mode. PostgreSQL/Supabase, Redis, and Kafka remain optional local infrastructure in Phase 1 because the API's adapter seams are already defined and the user's managed Supabase schema exists. Phase 2 adds local Postgres/Redis/Kafka profiles and worker processes without changing browser contracts.

```text
web :3000 -> api :8000
api -> Supabase/PostgreSQL (optional)
api -> Redis (Phase 2 cache/job adapter)
api -> Kafka (Phase 2 event adapter)
```

Health checks are `/api/health` and `/api/ready`. Secrets are environment variables or deployment-secret references only.
