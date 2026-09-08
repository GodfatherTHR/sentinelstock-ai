# Kafka Event Schemas

All events use a CloudEvents-like envelope:

```json
{
  "event_id": "uuid",
  "event_type": "inventory.updated",
  "timestamp": "2026-09-08T12:00:00Z",
  "source": "inventory-service",
  "schema_version": "1.0",
  "tenant_id": "uuid",
  "payload": {}
}
```

Initial topics:

- `inventory.updated`: warehouse, product, quantity, reserved, incoming, movement reference.
- `sale.completed` / `sale.returned`: warehouse, product, quantity, price, promotion, occurred_at.
- `purchase_order.created`: order, supplier, destination, items, total, approval provenance.
- `shipment.updated`: provider, shipment, vessel, route, ETA, status, coordinates, risk.
- `sentiment.updated`: region, product/category, score, trend, volatility, sample size, confidence.
- `forecast.generated`: scope, horizon, point, lower/upper interval, model/version, metrics.
- `risk.updated`: scope, component risks, overall score, severity, drivers.
- `restock.recommended`: decision ID, source snapshots, optimized action, approval policy.

Consumers are idempotent on `event_id`; malformed events go to a dead-letter topic with a validation report and are never silently discarded.
