# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

delegated: Next.js + TypeScript + Tailwind CSS for the operator dashboard; FastAPI + PostgreSQL/Supabase + Redis/Kafka-ready Python services for the backend.

## Users

Primary users are warehouse managers and procurement managers working daily across several distribution centers. Analysts inspect trends and risk, while viewers consume operational status without taking actions.

## Product Purpose

SentinelStock AI is an inventory and supply-chain intelligence platform that turns warehouse, demand, sentiment, agricultural, and logistics signals into explainable replenishment decisions. Success means a manager can move from current inventory to a reviewed, auditable purchase order without relying on invented AI numbers.

## Positioning

The platform separates numerical truth from language reasoning: specialized forecasting models predict demand, deterministic policy code calculates inventory state, and an optimizer chooses quantities while the AI layer coordinates tools and explains the evidence.

## Operating Context

Managers scan a multi-warehouse control room dashboard, open a high-risk SKU, inspect its forecast and evidence, compare supplier or transfer options, approve or reject a recommendation, and trace the action in an audit log. Demo data is acceptable until external connectors are configured.

## Capabilities and Constraints

- MVP must cover multiple warehouses, products, inventory, sales, suppliers, purchase orders, demand forecasting, regional sentiment, reorder point, stockout risk, recommendations, approval, and dashboard views.
- External providers are adapters; provider outages must not stop the core application.
- LLMs may orchestrate and explain structured results but may not invent forecast values, execute arbitrary SQL, or bypass approval controls.
- Consumer data is aggregated by region/product/category and must not expose individuals.
- Production deployment is expected to be Kubernetes-ready, with Docker Compose for local development.
- Open decision: exact shipping, weather, satellite, and consumer-signal providers remain adapter choices for later phases.

## Brand Commitments

The product name is SentinelStock AI. The UI should feel like a calm, high-signal operations console: serious enough for procurement decisions, readable under pressure, and explicit about uncertainty.

## Evidence on Hand

- `database.sql` is an existing Supabase/PostgreSQL schema draft with multi-tenant entities, inventory triggers, a stockout probability helper, and partial RLS policies.
- No existing application code, brand assets, or production data are present in the repository.
- Synthetic data is the initial evidence source and must be labeled as demo data.

## Product Principles

1. Numerical truth lives in deterministic services and validated models.
2. Every recommendation is inspectable, bounded by policy, and auditable.
3. Risk is prioritized by actionability, not decoration.
4. External intelligence enriches decisions without becoming a single point of failure.
5. Human approval remains the control surface for consequential procurement actions.

## Accessibility & Inclusion

Use semantic controls, keyboard navigation, visible focus states, non-color severity labels, readable contrast, and responsive layouts. Risk must never be communicated by color alone.
