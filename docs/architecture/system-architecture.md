# SentinelStock AI — System Architecture

## Decision

SentinelStock is an event-driven modular monorepo. The browser talks to a FastAPI application interface. Domain modules behind that interface own inventory state, forecasts, risk, optimization, recommendations, and approval. Kafka is the durable event seam; PostgreSQL/Supabase is the system of record; Redis is the read-through/cache and job coordination layer.

```text
Next.js operator console
        |
        v
FastAPI application interface
  |       |        |       |
inventory forecast risk  decision/approval
  |       |        |       |
  +-------+--------+-------+--> PostgreSQL / Supabase
                    |
                    +--> Redis read models / job state
                    +--> Kafka event topics

Connector adapters --> validation --> normalization --> Kafka
  FAOSTAT / OFF / USDA / shipping / Sentinel-2 / consumer signals
```

## Module seams

- `InventoryPolicy`: calculates available inventory, velocity, coverage, reorder point, and derived risk from policy configuration. The caller supplies a snapshot; the module does not query the database.
- `ForecastProvider`: returns validated forecast points and intervals. XGBoost/LightGBM is the initial implementation; a deterministic seasonal baseline is the fallback.
- `RiskScorer`: combines demand, supply, logistics, sentiment, and inventory signals into bounded severity and score.
- `ReplenishmentOptimizer`: accepts a normalized decision problem and returns quantities, source, timing, cost, constraints, and service level. OR-Tools is the production adapter; a deterministic fallback is available for demo mode.
- `RecommendationCoordinator`: sequences those modules, writes an auditable decision, and enforces approval policy. The LLM, if enabled later, can only call this interface through typed tools.
- `ExternalDataProvider`: a connector interface with `pull()` + normalized event output; no provider-specific assumptions leak into domain modules.

## Trust boundaries

The browser may read public API responses and submit user actions. It never receives service-role credentials and never writes directly to Supabase. The API validates tenant, role, request schema, and approval status before mutating state. Agent tools are allow-listed backend functions; no arbitrary SQL or direct database tool is exposed.

## Deployment shape

Local development uses Docker Compose with a FastAPI API and Next.js web app, demo mode on, and optional managed Supabase. Production splits modules into deployable services, uses managed Postgres/Redis/Kafka, and emits OpenTelemetry-compatible traces and structured JSON logs.

## Current phase

Phase 1 implements the core read model and decision flow in demo mode with deterministic forecasting/risk logic and an approval-safe recommendation endpoint. The interfaces remain stable for Phase 2 model and database adapters.
