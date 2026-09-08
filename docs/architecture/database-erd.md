# Database ERD

The existing `database.sql` already contains the core normalized tables and is treated as the starting migration. Phase 1 uses these entities:

```mermaid
erDiagram
  organizations ||--o{ warehouses : owns
  organizations ||--o{ products : catalogs
  organizations ||--o{ suppliers : contracts
  warehouses ||--o{ inventory : stores
  products ||--o{ inventory : tracks
  warehouses ||--o{ sales : fulfills
  sales ||--|{ sales_items : contains
  products ||--o{ sales_items : sold
  suppliers ||--o{ supplier_products : offers
  products ||--o{ supplier_products : sourced
  suppliers ||--o{ purchase_orders : receives
  warehouses ||--o{ purchase_orders : delivers
  purchase_orders ||--|{ purchase_order_items : contains
  products ||--o{ purchase_order_items : orders
  warehouses ||--o{ forecasts : scopes
  products ||--o{ forecasts : predicts
  products ||--o{ sentiment : maps
  warehouses ||--o{ risk_scores : scopes
  products ||--o{ risk_scores : scores
  agent_decisions }o--|| warehouses : recommends
  agent_decisions }o--|| products : concerns
  agent_decisions ||--o{ audit_logs : explains
```

## Phase 1 integrity notes

- `inventory` is unique on `(warehouse_id, product_id)` and stores quantity, reservations, incoming quantity, reorder point, safety stock, average daily demand, and derived coverage.
- `forecasts` is unique on `(warehouse_id, product_id, forecast_date)`.
- `purchase_orders` and `purchase_order_items` support approval status and AI provenance.
- `agent_decisions` is the immutable recommendation record; approval/execution is audit logged.
- The draft SQL enables RLS but only defines policies for warehouses, products, and inventory. The hardening migration adds organization-scoped policies for all remaining tables and explicit role checks.
