# API Contracts (Phase 1)

Base URL: `/api`. All responses are JSON. IDs are UUIDs in production; demo mode uses stable readable IDs.

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/health` | Liveness and mode |
| GET | `/metrics` | Basic service metrics |
| GET | `/warehouses` | Warehouse summaries and coordinates |
| GET | `/inventory` | Inventory status with derived metrics |
| GET | `/products` | Product catalog |
| GET | `/forecasts` | Forecast points by warehouse/product |
| GET | `/sentiment` | Aggregated regional sentiment |
| GET | `/suppliers` | Supplier options and constraints |
| GET | `/recommendations` | Pending and historical decisions |
| GET | `/risk` | Risk scores by warehouse/SKU |
| POST | `/forecast/run` | Run forecast job for a scope |
| POST | `/optimization/run` | Solve a replenishment problem |
| POST | `/recommendations/generate` | Create an auditable recommendation |
| POST | `/recommendations/{id}/approve` | Approve a pending recommendation |
| POST | `/recommendations/{id}/reject` | Reject a pending recommendation |
| POST | `/purchase-orders` | Create an order only from approved/authorized input |
| POST | `/simulation` | Run a baseline vs scenario comparison |

## Recommendation response

```json
{
  "id": "rec-1001",
  "decision_type": "RESTOCK",
  "warehouse_id": "wh-dhaka",
  "product_id": "sku-oil-1",
  "recommended_quantity": 2400,
  "supplier_id": "sup-aci",
  "urgency": "HIGH",
  "risk_score": 0.73,
  "confidence": 0.91,
  "forecast_demand": 9850,
  "current_inventory": 4200,
  "days_of_inventory": 6.2,
  "expected_stockout_probability": 0.084,
  "drivers": ["regional_demand_increase", "positive_consumer_sentiment", "supplier_lead_time_increase"],
  "requires_human_approval": true,
  "approval_status": "pending",
  "explanation": {"what": "...", "how_much": "...", "when": "...", "from_where": "...", "why": "...", "risk": "...", "confidence": "..."}
}
```

Mutating endpoints require an authenticated user context in production. Demo mode uses `X-Demo-Role`; the API still rejects purchase-order creation when the decision is not approved.
