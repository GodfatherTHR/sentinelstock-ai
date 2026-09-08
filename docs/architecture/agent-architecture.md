# Agent and Tool Architecture

The orchestrator is a coordination layer, not the source of numerical truth. Specialized deep modules expose typed functions:

1. Forecast module: `get_forecast(scope)`
2. Sentiment module: `get_regional_sentiment(scope)`
3. Inventory module: `get_inventory(scope)`, `calculate_reorder_point(input)`
4. Logistics module: `get_shipping_status(scope)`
5. Risk module: `calculate_stockout_risk(input)`
6. Optimization module: `optimize_replenishment(problem)`
7. Procurement module: `create_purchase_order(input)`
8. Explanation module: `explain_decision(evidence)`

The orchestrator can only call allow-listed backend functions. Each tool validates input and tenant scope. `create_purchase_order` requires an approved decision and role authorization; the browser and LLM cannot bypass this precondition. Tool calls, inputs, outputs, and failures are recorded in `agent_runs` and `audit_logs`.

The explanation module receives only structured evidence and model attribution. It must not add unsupported drivers, numbers, suppliers, or confidence claims.
