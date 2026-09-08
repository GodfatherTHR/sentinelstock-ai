# Implementation Roadmap

## Phase 1 — Core inventory platform (current)

- FastAPI contracts with demo adapter and approval-safe mutations.
- Inventory metrics, deterministic demand baseline, stockout risk, supplier selection, and recommendation explanation.
- Next.js operations dashboard, warehouse map, recommendation review, scenario simulator, and audit trail view.
- Supabase hardening migration and synthetic seed data.

## Phase 2 — Demand forecasting

- Persist sales/features, train XGBoost/LightGBM, quantile intervals, model registry, and monitoring endpoints.

## Phase 3 — Sentiment

- Multilingual ingestion adapters, aspect sentiment, regional aggregation, privacy filters, and drift monitoring.

## Phase 4 — Supplier/logistics

- Provider-neutral shipping adapter, ETA variance, supplier performance, and delay risk.

## Phase 5 — Optimization

- OR-Tools MILP, transfers, capacity, MOQ, case pack, temperature, shelf life, and budget constraints.

## Phase 6 — Agent orchestration

- Typed tool registry, approval-aware orchestrator, traceable explanations, and safe scenario planning.

## Phase 7 — Satellite intelligence

- Sentinel-2 ingestion, cloud masking, NDVI/crop health, and supply feature generation.

## Phase 8 — Autonomous workflows

- Policy-configured low-risk execution, manager/procurement approval queues, feedback capture, and continuous model monitoring.
