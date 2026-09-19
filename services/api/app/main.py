from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone
from typing import Iterator

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .agent import ask as ask_local_model
from .config import load_runtime_env
from .inventory import optimized_quantity
from .schemas import (
    AgentAskRequest,
    AgentAskResponse,
    AgriculturalObservation,
    AuditEntry,
    CropIndex,
    ExternalSignals,
    FoodCatalogItem,
    Forecast,
    GenerateRecommendationRequest,
    InventoryStatus,
    PurchaseOrderRequest,
    PurchaseOrderRow,
    Recommendation,
    SalesPoint,
    Sentiment,
    Shipment,
    SimulationRequest,
    SimulationResult,
    Supplier,
    Vessel,
    Warehouse,
)
from .supabase_repository import RepositoryError, SupabaseRepository

load_runtime_env()

# Roles allowed to mutate decision state, mirroring the RLS write policies.
DECISION_ROLES = {"admin", "procurement_manager", "warehouse_manager"}
PLANNING_ROLES = {"admin", "procurement_manager", "analyst"}

app = FastAPI(
    title="SentinelStock AI API",
    version="0.2.0",
    description="Inventory intelligence API backed by Supabase. Reads run under the caller's JWT so row level security applies.",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def access_token(authorization: str | None = Header(default=None)) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Authorization header must be a bearer token")
    return token.strip()


def claims_for(token: str) -> dict:
    try:
        payload = token.split(".")[1]
        padded = payload + "=" * (-len(payload) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded))
        return decoded if isinstance(decoded, dict) else {}
    except (IndexError, ValueError, json.JSONDecodeError):
        return {}


def get_repository(token: str | None = Depends(access_token)) -> Iterator[SupabaseRepository]:
    url = os.getenv("SUPABASE_URL", "")
    anon = os.getenv("SUPABASE_ANON_KEY", "") or os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
    service = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not (anon or service):
        raise HTTPException(status_code=503, detail="Supabase is not configured for this API")
    demo_mode = os.getenv("DEMO_MODE", "false").lower() in {"1", "true", "yes"}
    if token is None and not demo_mode:
        raise HTTPException(status_code=401, detail="Sign in to access this resource")
    repository = SupabaseRepository(url, anon or service, access_token=token or service)
    try:
        yield repository
    finally:
        repository.close()


def authorize(repository: SupabaseRepository, token: str | None, allowed: set[str]) -> dict:
    if token is None:
        raise HTTPException(status_code=401, detail="Sign in to change decision state")
    subject = str(claims_for(token).get("sub") or "")
    if not subject:
        raise HTTPException(status_code=401, detail="Token has no subject claim")
    profile = repository.profile(subject)
    if profile is None:
        raise HTTPException(status_code=403, detail="No operator profile is linked to this account")
    role = str(profile.get("role") or "viewer")
    if role not in allowed:
        raise HTTPException(status_code=403, detail=f"Role {role} cannot perform this action")
    return {"id": subject, "email": claims_for(token).get("email"), "role": role}


def _guard(callable_, *args, **kwargs):
    try:
        return callable_(*args, **kwargs)
    except RepositoryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "sentinelstock-api",
        "repository": "supabase",
        "supabase_configured": str(bool(os.getenv("SUPABASE_URL") and (os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")))).lower(),
        "demo_mode": os.getenv("DEMO_MODE", "false").lower(),
    }


@app.get("/api/ready")
def ready(repository: SupabaseRepository = Depends(get_repository)) -> dict:
    return {"status": "ready", **_guard(repository.health)}


@app.get("/api/metrics")
def metrics(repository: SupabaseRepository = Depends(get_repository)) -> dict[str, int]:
    inventory = _guard(repository.inventory)
    recommendations = _guard(repository.recommendations)
    return {
        "inventory_rows": len(inventory),
        "recommendations_pending": sum(row.approval_status == "pending" for row in recommendations),
        "stockout_risk_rows": sum(row.stockout_probability >= 0.5 for row in inventory),
        "purchase_orders": len(_guard(repository.purchase_orders)),
        "inbound_shipments": len(_guard(repository.shipments)),
        "vessels_tracked": _guard(repository.external_signals).vessels,
    }


@app.get("/api/warehouses")
def warehouses(repository: SupabaseRepository = Depends(get_repository)) -> list[Warehouse]:
    return _guard(repository.warehouses)


@app.get("/api/products")
def products(repository: SupabaseRepository = Depends(get_repository)) -> list[dict]:
    return _guard(repository.products)


@app.get("/api/inventory")
def inventory(warehouse_id: str | None = Query(default=None), repository: SupabaseRepository = Depends(get_repository)) -> list[InventoryStatus]:
    rows = _guard(repository.inventory)
    return [row for row in rows if not warehouse_id or row.warehouse_id == warehouse_id]


@app.get("/api/forecasts")
def forecasts(warehouse_id: str | None = Query(default=None), product_id: str | None = Query(default=None), repository: SupabaseRepository = Depends(get_repository)) -> list[Forecast]:
    rows = _guard(repository.forecasts)
    return [row for row in rows if (not warehouse_id or row.warehouse_id == warehouse_id) and (not product_id or row.product_id == product_id)]


@app.get("/api/sentiment")
def sentiment(repository: SupabaseRepository = Depends(get_repository)) -> list[Sentiment]:
    return _guard(repository.sentiment)


@app.get("/api/suppliers")
def suppliers(repository: SupabaseRepository = Depends(get_repository)) -> list[Supplier]:
    return _guard(repository.suppliers)


@app.get("/api/shipments")
def shipments(repository: SupabaseRepository = Depends(get_repository)) -> list[Shipment]:
    return _guard(repository.shipments)


@app.get("/api/sales")
def sales(days: int = Query(default=14, ge=1, le=90), warehouse_id: str | None = Query(default=None), product_id: str | None = Query(default=None), repository: SupabaseRepository = Depends(get_repository)) -> list[SalesPoint]:
    rows = _guard(repository.sales_series, days=days, warehouse_id=warehouse_id, product_id=product_id)
    return [SalesPoint(**row) for row in rows]


@app.get("/api/vessels")
def vessels(limit: int = Query(default=40, ge=1, le=200), repository: SupabaseRepository = Depends(get_repository)) -> list[Vessel]:
    return _guard(repository.vessels, limit)


@app.get("/api/signals")
def signals(repository: SupabaseRepository = Depends(get_repository)) -> dict:
    return {
        "summary": _guard(repository.external_signals).model_dump(),
        "agricultural": [row.model_dump() for row in _guard(repository.agricultural_observations, 20)],
        "crop_health": [row.model_dump() for row in _guard(repository.crop_indices, 12)],
        "food_catalog": [row.model_dump() for row in _guard(repository.food_catalog, 20)],
    }


@app.get("/api/risk")
def risk(repository: SupabaseRepository = Depends(get_repository)) -> list[dict]:
    return [
        {
            "warehouse_id": row.warehouse_id,
            "warehouse_name": row.warehouse_name,
            "product_id": row.product_id,
            "sku": row.sku,
            "overall_score": row.stockout_probability,
            "risk_level": row.inventory_risk,
            "days_of_inventory": row.days_of_inventory,
            "drivers": ["coverage_below_lead_time"] if row.days_of_inventory < 7 else [],
        }
        for row in _guard(repository.inventory)
    ]


@app.get("/api/recommendations")
def recommendations(status: str | None = Query(default=None), repository: SupabaseRepository = Depends(get_repository)) -> list[Recommendation]:
    rows = _guard(repository.recommendations)
    return [row for row in rows if not status or row.approval_status == status]


@app.post("/api/forecast/run")
def run_forecast(repository: SupabaseRepository = Depends(get_repository), token: str | None = Depends(access_token)) -> dict:
    authorize(repository, token, PLANNING_ROLES)
    result = _guard(repository.run_baseline_forecast)
    return {"status": "completed", "rows_written": result["rows_written"], "model_sources": result["model_sources"]}


@app.post("/api/optimization/run")
def run_optimization(request: GenerateRecommendationRequest, repository: SupabaseRepository = Depends(get_repository)) -> dict:
    rows = [row for row in _guard(repository.inventory) if (not request.warehouse_id or row.warehouse_id == request.warehouse_id) and (not request.product_id or row.product_id == request.product_id)]
    if not rows:
        raise HTTPException(status_code=404, detail="No inventory row matches the optimization scope")
    row = rows[0]
    suppliers = _guard(repository.suppliers)
    supplier = suppliers[0] if suppliers else None
    demand = row.average_daily_demand * 7
    quantity = optimized_quantity(row.available_inventory, demand, row.safety_stock, row.incoming, supplier.minimum_order_quantity if supplier else 0)
    return {
        "warehouse_id": row.warehouse_id,
        "product_id": row.product_id,
        "recommended_quantity": quantity,
        "expected_cost": round(quantity * row.unit_value, 2),
        "expected_service_level": round(1 - row.stockout_probability, 3),
        "stockout_probability": row.stockout_probability,
        "policy": "inventory_policy_v1",
    }


def mutate_recommendation(recommendation_id: str, status: str, repository: SupabaseRepository, token: str | None) -> Recommendation:
    actor = authorize(repository, token, DECISION_ROLES)
    return _guard(repository.set_decision_status, recommendation_id, status, user_id=actor["id"], user_email=actor["email"])


@app.post("/api/recommendations/{recommendation_id}/approve")
def approve_recommendation(recommendation_id: str, repository: SupabaseRepository = Depends(get_repository), token: str | None = Depends(access_token)) -> Recommendation:
    return mutate_recommendation(recommendation_id, "approved", repository, token)


@app.post("/api/recommendations/{recommendation_id}/reject")
def reject_recommendation(recommendation_id: str, repository: SupabaseRepository = Depends(get_repository), token: str | None = Depends(access_token)) -> Recommendation:
    return mutate_recommendation(recommendation_id, "rejected", repository, token)


@app.post("/api/recommendations/generate")
def generate_recommendation(request: GenerateRecommendationRequest, repository: SupabaseRepository = Depends(get_repository), token: str | None = Depends(access_token)) -> Recommendation:
    rows = [row for row in _guard(repository.recommendations) if (not request.warehouse_id or row.warehouse_id == request.warehouse_id) and (not request.product_id or row.product_id == request.product_id)]
    if not rows:
        raise HTTPException(status_code=404, detail="No actionable recommendation matches the requested scope")
    actor = authorize(repository, token, PLANNING_ROLES)
    return _guard(repository.set_decision_status, rows[0].id, "pending", user_id=actor["id"], user_email=actor["email"])


@app.get("/api/purchase-orders")
def purchase_orders(repository: SupabaseRepository = Depends(get_repository)) -> list[PurchaseOrderRow]:
    return _guard(repository.purchase_orders)


@app.post("/api/purchase-orders")
def create_purchase_order(request: PurchaseOrderRequest, repository: SupabaseRepository = Depends(get_repository), token: str | None = Depends(access_token)) -> PurchaseOrderRow:
    actor = authorize(repository, token, {"admin", "procurement_manager"})
    return _guard(repository.create_purchase_order, request.decision_id, user_id=actor["id"])


@app.post("/api/agent/ask", response_model=AgentAskResponse)
def ask_console(request: AgentAskRequest, repository: SupabaseRepository = Depends(get_repository)) -> AgentAskResponse:
    """Route a natural-language question to a read-only tool with the local Needle model."""
    return AgentAskResponse(**ask_local_model(repository, request.query))


@app.get("/api/audit-log")
def audit_log(limit: int = Query(default=50, ge=1, le=200), repository: SupabaseRepository = Depends(get_repository)) -> list[AuditEntry]:
    return _guard(repository.audit_log, limit)


@app.post("/api/simulation", response_model=SimulationResult)
def simulation(request: SimulationRequest, repository: SupabaseRepository = Depends(get_repository)) -> SimulationResult:
    inventory = _guard(repository.inventory)
    recommendations = _guard(repository.recommendations)
    if not inventory:
        raise HTTPException(status_code=409, detail="No inventory rows are available to simulate")
    units = sum(row.available_inventory for row in inventory)
    stockouts = float(sum(1 for row in inventory if row.stockout_probability >= 0.5))
    baseline = {
        "inventory_units": round(units, 1),
        "stockout_count": stockouts,
        "orders_required": float(len(recommendations)),
        "cost": round(sum(row.expected_cost for row in recommendations), 2),
        "service_level": round(1 - sum(row.stockout_probability for row in inventory) / len(inventory), 3),
    }
    demand_factor = 1 + request.demand_delta_percent / 100
    supply_factor = 1 + max(-request.crop_delta_percent / 100, 0) * 0.5
    scenario = {
        "inventory_units": round(units / demand_factor / supply_factor, 1),
        "stockout_count": stockouts + (1 if request.demand_delta_percent > 10 else 0) + (1 if request.lead_time_delta_days > 3 else 0) + (1 if request.crop_delta_percent < -10 else 0),
        "orders_required": round(baseline["orders_required"] + max(request.demand_delta_percent, 0) / 20 + max(request.lead_time_delta_days, 0) / 5, 1),
        "cost": round(baseline["cost"] * demand_factor * supply_factor + max(request.lead_time_delta_days, 0) * 4200, 2),
        "service_level": round(max(0.5, baseline["service_level"] - max(request.demand_delta_percent, 0) / 1000 - max(request.lead_time_delta_days, 0) / 200), 3),
    }
    return SimulationResult(
        baseline=baseline,
        scenario=scenario,
        deltas={key: round(scenario[key] - baseline[key], 2) for key in baseline},
        assumptions=[
            "Baseline is computed from the live inventory and recommendation read model.",
            "Demand uplift applies uniformly across SKUs; crop change is a supply-side factor.",
            "No new supplier or transfer capacity is added in this simulation.",
        ],
    )
