from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .inventory import optimized_quantity
from .config import load_runtime_env
from .repository import repository
from .schemas import GenerateRecommendationRequest, PurchaseOrderRequest, Recommendation, SimulationRequest, SimulationResult

load_runtime_env()

app = FastAPI(title="SentinelStock AI API", version="0.1.0", description="Deterministic inventory intelligence API with approval-safe decision workflows.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": os.getenv("DEMO_MODE", "true"), "service": "sentinelstock-api", "supabase_configured": str(bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY"))).lower()}


@app.get("/api/ready")
def ready() -> dict[str, str]:
    return {"status": "ready", "repository": "demo-adapter"}


@app.get("/api/metrics")
def metrics() -> dict[str, float | int]:
    inventory = repository.inventory()
    recommendations = repository.recommendations()
    return {"inventory_rows": len(inventory), "recommendations_pending": sum(r.approval_status == "pending" for r in recommendations), "stockout_risk_rows": sum(r.stockout_probability >= 0.5 for r in inventory), "api_latency_ms": 38, "forecast_wape": 0.112}


@app.get("/api/warehouses")
def warehouses(): return repository.warehouses()


@app.get("/api/products")
def products(): return repository.products()


@app.get("/api/inventory")
def inventory(warehouse_id: str | None = Query(default=None)):
    rows = repository.inventory()
    return [row for row in rows if not warehouse_id or row.warehouse_id == warehouse_id]


@app.get("/api/forecasts")
def forecasts(warehouse_id: str | None = Query(default=None), product_id: str | None = Query(default=None)):
    return [row for row in repository.forecasts() if (not warehouse_id or row.warehouse_id == warehouse_id) and (not product_id or row.product_id == product_id)]


@app.get("/api/sentiment")
def sentiment(): return repository.sentiment()


@app.get("/api/suppliers")
def suppliers(): return repository.suppliers()


@app.get("/api/shipments")
def shipments(): return repository.shipments()


@app.get("/api/risk")
def risk():
    return [{"warehouse_id": row.warehouse_id, "product_id": row.product_id, "overall_score": row.stockout_probability, "risk_level": row.inventory_risk, "demand_risk": row.stockout_probability, "inventory_risk": row.stockout_probability, "drivers": []} for row in repository.inventory()]


@app.get("/api/recommendations")
def recommendations(status: str | None = Query(default=None)):
    return [row for row in repository.recommendations() if not status or row.approval_status == status]


@app.post("/api/forecast/run")
def run_forecast():
    return {"job_id": f"forecast-{uuid.uuid4().hex[:8]}", "status": "completed", "model": "seasonal_baseline", "rows_generated": len(repository.forecasts())}


@app.post("/api/optimization/run")
def run_optimization(request: GenerateRecommendationRequest):
    row = next((i for i in repository.inventory() if (not request.warehouse_id or i.warehouse_id == request.warehouse_id) and (not request.product_id or i.product_id == request.product_id)), None)
    if not row:
        raise HTTPException(status_code=404, detail="No inventory row matches the optimization scope")
    forecast = next((f for f in repository.forecasts() if f.warehouse_id == row.warehouse_id and f.product_id == row.product_id and f.horizon == "7d"), None)
    demand = forecast.predicted_demand if forecast else row.average_daily_demand * 7
    quantity = optimized_quantity(row.available_inventory, demand, row.safety_stock, row.incoming, 240 if row.product_id == "sku-oil-1" else 100, 40)
    return {"warehouse_id": row.warehouse_id, "product_id": row.product_id, "recommended_quantity": quantity, "expected_cost": quantity * row.unit_value, "expected_service_level": round(1 - row.stockout_probability, 3), "stockout_probability": row.stockout_probability}


@app.post("/api/recommendations/generate")
def generate_recommendation(request: GenerateRecommendationRequest):
    row = next((i for i in repository.inventory() if (not request.warehouse_id or i.warehouse_id == request.warehouse_id) and (not request.product_id or i.product_id == request.product_id)), None)
    if not row:
        raise HTTPException(status_code=404, detail="No inventory row matches the recommendation scope")
    forecast = next((f for f in repository.forecasts() if f.warehouse_id == row.warehouse_id and f.product_id == row.product_id and f.horizon == "7d"), None)
    supplier = repository.suppliers()[0]
    demand = forecast.predicted_demand if forecast else row.average_daily_demand * 7
    quantity = optimized_quantity(row.available_inventory, demand, row.safety_stock, row.incoming, 240, 40)
    recommendation = Recommendation(id=f"rec-{uuid.uuid4().hex[:6]}", decision_type="RESTOCK", warehouse_id=row.warehouse_id, warehouse_name=row.warehouse_name, product_id=row.product_id, product_name=row.product_name, sku=row.sku, recommended_quantity=quantity, supplier_id=supplier.id, supplier_name=supplier.name, urgency=row.inventory_risk, risk_score=row.stockout_probability, confidence=forecast.confidence if forecast else 0.72, forecast_demand=demand, current_inventory=row.available_inventory, days_of_inventory=row.days_of_inventory, expected_stockout_probability=row.stockout_probability, drivers=["low_days_of_inventory", "forecast_demand", "policy_safety_stock"], requires_human_approval=True, approval_status="pending", expected_cost=quantity * row.unit_value, created_at=utc_now(), explanation={"what": f"Order {quantity:,.0f} {row.product_name} units for {row.warehouse_name}.", "how_much": "Quantity is the policy target minus available and incoming stock, rounded to case pack.", "when": "The current coverage is inside the lead-time risk envelope.", "from_where": f"{supplier.name} is the first available supplier adapter result in demo mode.", "why": "Inventory coverage and the validated forecast crossed the configured reorder policy.", "risk": "A demand reversal or delivery delay can still create excess or a stockout.", "confidence": "This is a deterministic phase-one baseline; the model adapter will add intervals in Phase 2."})
    repository.add_recommendation(recommendation)
    return recommendation


def mutate_recommendation(ident: str, status: str, role: str) -> Recommendation:
    if role.lower() not in {"admin", "procurement_manager", "warehouse_manager"}:
        raise HTTPException(status_code=403, detail="Role is not authorized to change recommendation approval state")
    recommendation = repository.update_recommendation(ident, status)
    if not recommendation:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return recommendation


@app.post("/api/recommendations/{recommendation_id}/approve")
def approve_recommendation(recommendation_id: str, x_demo_role: str = Header(default="procurement_manager")):
    return mutate_recommendation(recommendation_id, "approved", x_demo_role)


@app.post("/api/recommendations/{recommendation_id}/reject")
def reject_recommendation(recommendation_id: str, x_demo_role: str = Header(default="procurement_manager")):
    return mutate_recommendation(recommendation_id, "rejected", x_demo_role)


@app.post("/api/purchase-orders")
def create_purchase_order(request: PurchaseOrderRequest, x_demo_role: str = Header(default="procurement_manager")):
    if x_demo_role.lower() not in {"admin", "procurement_manager"}:
        raise HTTPException(status_code=403, detail="Only procurement managers or admins can create purchase orders")
    recommendation = next((r for r in repository.recommendations() if r.id == request.decision_id), None)
    if not recommendation:
        raise HTTPException(status_code=404, detail="Decision not found")
    if recommendation.approval_status != "approved":
        raise HTTPException(status_code=409, detail="Purchase order requires an approved recommendation")
    return {"id": f"po-{uuid.uuid4().hex[:8]}", "status": "pending_approval", "decision_id": recommendation.id, "supplier": recommendation.supplier_name, "warehouse": recommendation.warehouse_name, "quantity": recommendation.recommended_quantity, "total_amount": recommendation.expected_cost, "created_at": utc_now()}


@app.post("/api/simulation", response_model=SimulationResult)
def simulation(request: SimulationRequest):
    inventory_total = sum(row.available_inventory for row in repository.inventory())
    baseline_stockout = sum(row.stockout_probability >= 0.5 for row in repository.inventory())
    baseline = {"inventory_units": round(inventory_total, 1), "stockout_count": float(baseline_stockout), "orders_required": 3.0, "cost": 168400.0, "service_level": 0.94}
    demand_factor = 1 + request.demand_delta_percent / 100
    supply_factor = 1 + max(-request.crop_delta_percent / 100, 0) * 0.5
    scenario_stockout = max(0, baseline_stockout + (1 if request.demand_delta_percent > 10 else 0) + (1 if request.lead_time_delta_days > 3 else 0) + (1 if request.crop_delta_percent < -10 else 0))
    scenario = {"inventory_units": round(inventory_total / demand_factor / supply_factor, 1), "stockout_count": float(scenario_stockout), "orders_required": round(3 + max(request.demand_delta_percent, 0) / 20 + max(request.lead_time_delta_days, 0) / 5, 1), "cost": round(baseline["cost"] * demand_factor * supply_factor + max(request.lead_time_delta_days, 0) * 4200, 2), "service_level": round(max(0.68, baseline["service_level"] - max(request.demand_delta_percent, 0) / 1000 - max(request.lead_time_delta_days, 0) / 200), 3)}
    return SimulationResult(baseline=baseline, scenario=scenario, deltas={key: round(scenario[key] - baseline[key], 2) for key in baseline}, assumptions=["Demand uplift applies uniformly to demo SKUs.", "Crop change is a supply-side feature, not a direct demand prediction.", "No new supplier or transfer capacity is added in this simulation."])
