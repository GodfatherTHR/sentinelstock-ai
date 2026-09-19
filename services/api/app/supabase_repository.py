from __future__ import annotations

import hashlib
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from .inventory import InventoryPolicy, inventory_metrics, optimized_quantity
from .schemas import (
    AgriculturalObservation,
    AuditEntry,
    CropIndex,
    Explanation,
    ExternalSignals,
    FoodCatalogItem,
    Forecast,
    IngestionRun,
    InventoryStatus,
    PurchaseOrderRow,
    Recommendation,
    Sentiment,
    Shipment,
    Supplier,
    Vessel,
    Warehouse,
)

POLICY = InventoryPolicy()
POLICY_VERSION = "policy-v1"
FORECAST_MODEL = "baseline_demand_v1"
FORECAST_MODEL_VERSION = "phase1.1"
DEFAULT_LEAD_TIME_DAYS = 7
RECOMMENDATION_HORIZON_DAYS = 7


class RepositoryError(RuntimeError):
    """Raised when Supabase rejects a request."""


class SupabaseRepository:
    """Read/write model backed by Supabase PostgREST.

    Reads use the caller's access token when one is supplied, so row level security
    decides what the operator may see. Writes (decision records, audit entries,
    purchase orders) go through the same token and are additionally gated by role.
    """

    def __init__(self, base_url: str, api_key: str, access_token: str | None = None, *, timeout: float = 20.0) -> None:
        self._base = base_url.rstrip("/") + "/rest/v1"
        self._headers = {"apikey": api_key, "Accept": "application/json", "Authorization": f"Bearer {access_token or api_key}"}
        self._client = httpx.Client(timeout=timeout)

    # ---------------------------------------------------------------- transport

    def _get(self, table: str, params: dict[str, str] | None = None) -> list[dict[str, Any]]:
        response = self._client.get(f"{self._base}/{table}", params=params or {}, headers=self._headers)
        if response.status_code >= 400:
            raise RepositoryError(f"GET {table} failed ({response.status_code}): {response.text[:300]}")
        payload = response.json()
        return payload if isinstance(payload, list) else [payload]

    def _write(self, table: str, rows: list[dict[str, Any]], *, on_conflict: str | None = None, returning: bool = False) -> list[dict[str, Any]]:
        prefer = []
        if on_conflict:
            prefer.append("resolution=merge-duplicates")
        prefer.append("return=representation" if returning else "return=minimal")
        headers = {**self._headers, "Content-Type": "application/json", "Prefer": ",".join(prefer)}
        params = {"on_conflict": on_conflict} if on_conflict else None
        response = self._client.post(f"{self._base}/{table}", params=params, headers=headers, json=rows)
        if response.status_code >= 400:
            raise RepositoryError(f"POST {table} failed ({response.status_code}): {response.text[:300]}")
        return response.json() if returning and response.text else []

    def _count(self, table: str, params: dict[str, str] | None = None, *, column: str = "id") -> int:
        query = {**(params or {}), "select": column, "limit": "1"}
        headers = {**self._headers, "Prefer": "count=exact"}
        response = self._client.get(f"{self._base}/{table}", params=query, headers=headers)
        if response.status_code >= 400:
            raise RepositoryError(f"COUNT {table} failed ({response.status_code}): {response.text[:200]}")
        content_range = response.headers.get("content-range", "*/0")
        return int(content_range.split("/")[-1] or 0)

    def close(self) -> None:
        self._client.close()

    def _rpc(self, name: str, payload: dict[str, Any]) -> Any:
        headers = {**self._headers, "Content-Type": "application/json"}
        response = self._client.post(f"{self._base}/rpc/{name}", headers=headers, json=payload)
        if response.status_code >= 400:
            raise RepositoryError(f"RPC {name} failed ({response.status_code}): {response.text[:300]}")
        return response.json() if response.text else None

    # ---------------------------------------------------------------- catalog

    def _products(self) -> list[dict[str, Any]]:
        return self._get(
            "products",
            {"select": "id,sku,name,category,unit,shelf_life_days,is_perishable,unit_cost,temperature_zone", "order": "sku"},
        )

    def _warehouses(self) -> list[dict[str, Any]]:
        return self._get("warehouses", {"select": "id,name,region,latitude,longitude,capacity,temperature_zone,active", "order": "name"})

    def _suppliers(self) -> list[dict[str, Any]]:
        return self._get("suppliers", {"select": "id,name,region,lead_time_days,minimum_order_quantity,active", "order": "lead_time_days"})

    def _inventory_rows(self) -> list[dict[str, Any]]:
        return self._get(
            "inventory",
            {
                "select": "id,warehouse_id,product_id,quantity,reserved,incoming,reorder_point,safety_stock,average_daily_demand,days_of_inventory,stockout_probability,updated_at",
                "order": "updated_at.desc",
            },
        )

    def _supplier_products(self) -> list[dict[str, Any]]:
        return self._get("supplier_products", {"select": "supplier_id,product_id,unit_price,lead_time_days,minimum_order_quantity"})

    # ---------------------------------------------------------------- read model

    def products(self) -> list[dict[str, Any]]:
        return self._products()

    def inventory(self) -> list[InventoryStatus]:
        products = {row["id"]: row for row in self._products()}
        warehouses = {row["id"]: row for row in self._warehouses()}
        suppliers = self._suppliers() or []
        lead_time = min((supplier["lead_time_days"] for supplier in suppliers if supplier.get("active")), default=DEFAULT_LEAD_TIME_DAYS)
        rows = []
        for row in self._inventory_rows():
            product = products.get(row["product_id"])
            warehouse = warehouses.get(row["warehouse_id"])
            if product is None or warehouse is None:
                continue
            metrics = inventory_metrics(
                quantity=float(row["quantity"]),
                reserved=float(row["reserved"]),
                incoming=float(row["incoming"]),
                average_daily_demand=float(row["average_daily_demand"]),
                lead_time_days=lead_time,
                unit_value=float(product.get("unit_cost") or 0),
                policy=POLICY,
            )
            rows.append(
                InventoryStatus(
                    id=str(row["id"]),
                    warehouse_id=str(row["warehouse_id"]),
                    warehouse_name=warehouse["name"],
                    product_id=str(row["product_id"]),
                    sku=product["sku"],
                    product_name=product["name"],
                    category=product.get("category") or "Uncategorised",
                    quantity=float(row["quantity"]),
                    reserved=float(row["reserved"]),
                    incoming=float(row["incoming"]),
                    available_inventory=float(metrics["available_inventory"]),
                    average_daily_demand=float(row["average_daily_demand"]),
                    days_of_inventory=float(metrics["days_of_inventory"]),
                    safety_stock=float(metrics["safety_stock"]),
                    reorder_point=float(metrics["reorder_point"]),
                    stockout_probability=float(metrics["stockout_probability"]),
                    excess_inventory=float(metrics["excess_inventory"]),
                    inventory_risk=str(metrics["inventory_risk"]),
                    unit_value=float(product.get("unit_cost") or 0),
                    updated_at=row.get("updated_at") or datetime.now(timezone.utc).isoformat(),
                )
            )
        return rows

    def warehouses(self) -> list[Warehouse]:
        inventory = self.inventory()
        result = []
        for row in self._warehouses():
            rows = [item for item in inventory if item.warehouse_id == str(row["id"])]
            units = sum(item.quantity + item.incoming for item in rows)
            value = sum(item.available_inventory * item.unit_value for item in rows)
            capacity = float(row.get("capacity") or 0)
            utilization = min(units / capacity, 1.5) if capacity else 0.0
            probability = max((item.stockout_probability for item in rows), default=0.0)
            risk_score = round(max(probability, min(utilization, 1.0) * 0.6), 3)
            level = "CRITICAL" if risk_score >= 0.75 else "HIGH" if risk_score >= 0.5 else "MEDIUM" if risk_score >= 0.3 else "LOW"
            result.append(
                Warehouse(
                    id=str(row["id"]),
                    name=row["name"],
                    region=row.get("region") or "",
                    latitude=float(row.get("latitude") or 0.0),
                    longitude=float(row.get("longitude") or 0.0),
                    capacity=capacity,
                    utilization=round(utilization, 3),
                    inventory_value=round(value, 2),
                    risk_score=risk_score,
                    risk_level=level,
                    status="critical" if level == "CRITICAL" else "watch" if level in {"HIGH", "MEDIUM"} else "stable",
                )
            )
        return result

    def sentiment(self) -> list[Sentiment]:
        products = {row["id"]: row for row in self._products()}
        rows = self._get(
            "sentiment",
            {"select": "region,product_id,sentiment_score,demand_signal,confidence,sentiment_change,sample_count,source,timestamp", "order": "timestamp.desc", "limit": "60"},
        )
        result = []
        for row in rows:
            product = products.get(row.get("product_id") or "")
            change = float(row.get("sentiment_change") or 0)
            result.append(
                Sentiment(
                    region=row.get("region") or "Unassigned",
                    product_category=(product or {}).get("category") or "All categories",
                    sentiment_score=float(row.get("sentiment_score") or 0),
                    sentiment_change=change,
                    demand_signal=float(row.get("demand_signal") or 0),
                    confidence=float(row.get("confidence") or 0),
                    sample_count=int(row.get("sample_count") or 0),
                    trend="rising" if change > 0.02 else "falling" if change < -0.02 else "stable",
                )
            )
        return result

    def suppliers(self) -> list[Supplier]:
        counts: dict[str, int] = {}
        for link in self._supplier_products():
            counts[str(link["supplier_id"])] = counts.get(str(link["supplier_id"]), 0) + 1
        return [
            Supplier(
                id=str(row["id"]),
                name=row["name"],
                region=row.get("region") or "",
                lead_time_days=int(row.get("lead_time_days") or 0),
                minimum_order_quantity=float(row.get("minimum_order_quantity") or 0),
                active_products=counts.get(str(row["id"]), 0),
                active=bool(row.get("active", True)),
            )
            for row in self._suppliers()
        ]

    def shipments(self) -> list[Shipment]:
        suppliers = {row["id"]: row["name"] for row in self._suppliers()}
        warehouses = {row["id"]: row["name"] for row in self._warehouses()}
        rows = self._get(
            "shipments",
            {"select": "id,supplier_id,destination,vessel_id,origin,eta,status,latitude,longitude,risk_score,delay_days,source", "order": "eta"},
        )
        return [
            Shipment(
                id=str(row["id"]),
                supplier_name=suppliers.get(str(row.get("supplier_id")), row.get("origin") or "Unknown supplier"),
                destination=warehouses.get(str(row.get("destination")), row.get("origin") or "Unknown destination"),
                vessel_id=row.get("vessel_id") or "unassigned",
                eta=row.get("eta") or "",
                status=row.get("status") or "unknown",
                delay_days=float(row.get("delay_days") or 0),
                risk_score=float(row.get("risk_score") or 0),
                latitude=float(row.get("latitude") or 0),
                longitude=float(row.get("longitude") or 0),
                source=row.get("source"),
            )
            for row in rows
        ]

    def forecasts(self) -> list[Forecast]:
        products = {row["id"]: row for row in self._products()}
        rows = self._get(
            "forecasts",
            {"select": "warehouse_id,product_id,forecast_date,predicted_demand,lower_bound,upper_bound,confidence,model_name,model_version,created_at", "order": "forecast_date", "limit": "400"},
        )
        today = date.today()
        result = []
        for row in rows:
            product = products.get(str(row["product_id"]))
            horizon_days = (date.fromisoformat(str(row["forecast_date"])) - today).days
            horizon = "7d" if horizon_days <= 10 else "14d" if horizon_days <= 21 else "30d"
            result.append(
                Forecast(
                    warehouse_id=str(row["warehouse_id"]),
                    product_id=str(row["product_id"]),
                    product_name=(product or {}).get("name") or "Unknown product",
                    horizon=horizon,
                    predicted_demand=float(row["predicted_demand"]),
                    lower_bound=float(row.get("lower_bound") or row["predicted_demand"]),
                    upper_bound=float(row.get("upper_bound") or row["predicted_demand"]),
                    confidence=float(row.get("confidence") or 0),
                    model_name=row.get("model_name") or FORECAST_MODEL,
                    model_version=row.get("model_version") or FORECAST_MODEL_VERSION,
                    generated_at=row.get("created_at") or datetime.now(timezone.utc).isoformat(),
                )
            )
        return result

    def sales_statistics(self, days: int = 28) -> dict[tuple[str, str], dict[str, Any]]:
        """Observed demand statistics per warehouse × SKU from the sales history."""
        rows = self._rpc("sales_daily_average", {"p_days": days}) or []
        return {(str(row["warehouse_id"]), str(row["product_id"])): row for row in rows}

    def sales_series(self, *, days: int = 14, warehouse_id: str | None = None, product_id: str | None = None) -> list[dict[str, Any]]:
        """Daily sold quantity for the chart, optionally for one warehouse × SKU pair."""
        since = (datetime.now(timezone.utc) - timedelta(days=max(days, 1))).isoformat()
        params = {
            "select": "warehouse_id,product_id,quantity,timestamp",
            "timestamp": f"gte.{since}",
            "order": "timestamp.asc",
            "limit": "5000",
        }
        if warehouse_id:
            params["warehouse_id"] = f"eq.{warehouse_id}"
        if product_id:
            params["product_id"] = f"eq.{product_id}"
        totals: dict[str, float] = {}
        for row in self._get("sales", params):
            day = str(row["timestamp"])[:10]
            totals[day] = totals.get(day, 0.0) + float(row["quantity"])
        return [{"day": day, "quantity": round(total, 1)} for day, total in sorted(totals.items())]

    def run_baseline_forecast(self, *, horizons: tuple[int, ...] = (7, 14, 30)) -> dict[str, Any]:
        """Persist a demand baseline: observed sales history first, demand column as fallback."""
        statistics = self.sales_statistics(28)
        today = date.today()
        rows: list[dict[str, Any]] = []
        sources = {"sales_history": 0, "demand_column": 0}

        for item in self.inventory():
            stats = statistics.get((item.warehouse_id, item.product_id))
            for days in horizons:
                if stats and float(stats.get("avg_quantity") or 0) > 0:
                    mean = float(stats["avg_quantity"])
                    sigma = float(stats.get("stddev_quantity") or 0)
                    predicted = round(mean * days, 3)
                    band = round(1.28 * sigma * math.sqrt(days), 3)
                    confidence = min(0.95, 0.6 + min(int(stats.get("sample_days") or 0), 60) / 150)
                    model_name, model_version = "sales_history_baseline", "phase1.2"
                    sources["sales_history"] += 1
                else:
                    predicted = round(item.average_daily_demand * days, 3)
                    band = round(predicted * {7: 0.12, 14: 0.15, 30: 0.18}.get(days, 0.15), 3)
                    confidence = {7: 0.9, 14: 0.86, 30: 0.82}.get(days, 0.85)
                    model_name, model_version = "baseline_demand_v1", "phase1.1"
                    sources["demand_column"] += 1

                rows.append(
                    {
                        "warehouse_id": item.warehouse_id,
                        "product_id": item.product_id,
                        "forecast_date": (today + timedelta(days=days)).isoformat(),
                        "predicted_demand": predicted,
                        "lower_bound": round(max(predicted - band, 0), 3),
                        "upper_bound": round(predicted + band, 3),
                        "confidence": round(confidence, 3),
                        "model_name": model_name,
                        "model_version": model_version,
                    }
                )
        if rows:
            self._write("forecasts", rows, on_conflict="warehouse_id,product_id,forecast_date")
        return {"rows_written": len(rows), "model_sources": sources}

    # ---------------------------------------------------------------- decisions

    def recommendations(self) -> list[Recommendation]:
        decisions = self._decisions_by_key()
        suppliers = self.suppliers()
        supplier = suppliers[0] if suppliers else None
        sentiment_rows = self.sentiment()
        result = []
        for item in self.inventory():
            if item.inventory_risk not in {"HIGH", "CRITICAL"} and item.stockout_probability < 0.5:
                continue
            result.append(self._build_recommendation(item, supplier, sentiment_rows, decisions))
        result.sort(key=lambda row: row.risk_score, reverse=True)
        return result

    def _build_recommendation(self, item: InventoryStatus, supplier: Supplier | None, sentiment_rows: list[Sentiment], decisions: dict[str, str]) -> Recommendation:
        forecast_demand = item.average_daily_demand * RECOMMENDATION_HORIZON_DAYS
        quantity = optimized_quantity(
            available_inventory=item.available_inventory,
            forecast_demand=forecast_demand,
            safety_stock=item.safety_stock,
            incoming=item.incoming,
            minimum_order_quantity=supplier.minimum_order_quantity if supplier else 0,
        )
        key = hashlib.sha1(f"{item.warehouse_id}:{item.product_id}:{POLICY_VERSION}".encode()).hexdigest()[:10]
        drivers = ["forecast_demand", "policy_safety_stock"]
        if item.days_of_inventory < DEFAULT_LEAD_TIME_DAYS:
            drivers.append("coverage_below_lead_time")
        if item.stockout_probability >= 0.7:
            drivers.append("high_stockout_probability")
        if item.excess_inventory > 0:
            drivers.append("excess_inventory_pressure")
        matching = next((row for row in sentiment_rows if row.product_category == item.category), None)
        if matching and matching.demand_signal >= 0.6:
            drivers.append("positive_regional_sentiment")
        explanation = Explanation(
            what=f"Order {quantity:,.0f} {item.product_name} units for {item.warehouse_name}.",
            how_much="Quantity is the policy target (7-day demand plus safety stock) minus available and incoming stock, raised to the supplier minimum order quantity.",
            when=f"Coverage is {item.days_of_inventory:.1f} days against a {DEFAULT_LEAD_TIME_DAYS}-day lead-time default for the supplier mix.",
            from_where=f"{supplier.name} ({supplier.region or 'region n/a'}, MOQ {supplier.minimum_order_quantity:,.0f}) is the shortest lead-time active supplier." if supplier else "No active supplier is registered for this organization yet.",
            why="Inventory coverage, the deterministic demand baseline, and the replenishment policy crossed the reorder envelope for this warehouse and SKU.",
            risk="Demand can reverse or a shipment can slip; approval and the next inventory movement remain required before execution.",
            confidence=f"High for the policy math; the demand figure is a {FORECAST_MODEL} baseline from current average daily demand, not a trained model output.",
        )
        return Recommendation(
            id=f"rec-{key}",
            decision_type="RESTOCK",
            warehouse_id=item.warehouse_id,
            warehouse_name=item.warehouse_name,
            product_id=item.product_id,
            product_name=item.product_name,
            sku=item.sku,
            recommended_quantity=float(quantity),
            supplier_id=supplier.id if supplier else None,
            supplier_name=supplier.name if supplier else None,
            urgency=item.inventory_risk,
            risk_score=item.stockout_probability,
            confidence=0.9 if item.inventory_risk == "CRITICAL" else 0.82,
            forecast_demand=forecast_demand,
            current_inventory=item.available_inventory,
            days_of_inventory=item.days_of_inventory,
            expected_stockout_probability=item.stockout_probability,
            drivers=drivers,
            requires_human_approval=True,
            approval_status=decisions.get(f"rec-{key}", "pending"),  # type: ignore[arg-type]
            expected_cost=round(quantity * item.unit_value, 2),
            created_at=datetime.now(timezone.utc),
            explanation=explanation,
        )

    def _decision_rows(self, limit: int = 200) -> list[dict[str, Any]]:
        return self._get("agent_decisions", {"select": "id,recommendation,approval_status,created_at", "order": "created_at.desc", "limit": str(limit)})

    def _decisions_by_key(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for row in self._decision_rows():
            payload = row.get("recommendation") or {}
            key = payload.get("id") if isinstance(payload, dict) else None
            if key and key not in result:
                result[str(key)] = str(row.get("approval_status") or "pending")
        return result

    def set_decision_status(self, recommendation_id: str, status: str, *, user_id: str | None, user_email: str | None) -> Recommendation:
        match = next((row for row in self.recommendations() if row.id == recommendation_id), None)
        if match is None:
            raise RepositoryError("recommendation not found")
        existing_id = None
        for row in self._decision_rows():
            payload = row.get("recommendation") or {}
            if isinstance(payload, dict) and payload.get("id") == recommendation_id:
                existing_id = row["id"]
                break
        payload = {
            "organization_id": self._organization_id(user_id),
            "decision_type": "RESTOCK",
            "warehouse_id": match.warehouse_id,
            "product_id": match.product_id,
            "recommendation": match.model_dump(mode="json"),
            "reasoning": match.explanation.why,
            "drivers": match.drivers,
            "confidence": match.confidence,
            "risk_score": match.risk_score,
            "requires_human_approval": True,
            "approval_status": status,
            "approved_by": user_id,
            "approved_at": datetime.now(timezone.utc).isoformat() if status in {"approved", "rejected"} else None,
        }
        if existing_id:
            self._write("agent_decisions", [{**payload, "id": existing_id}], on_conflict="id")
        else:
            self._write("agent_decisions", [payload])
        self._write(
            "audit_logs",
            [
                {
                    "organization_id": self._organization_id(user_id),
                    "user_id": user_id,
                    "action": f"recommendation.{status}",
                    "entity_type": "agent_decision",
                    "new_data": {"recommendation_id": recommendation_id, "status": status, "quantity": match.recommended_quantity},
                    "metadata": {"actor": user_email or user_id, "sku": match.sku, "warehouse": match.warehouse_name},
                }
            ],
        )
        return match.model_copy(update={"approval_status": status})

    def purchase_orders(self) -> list[PurchaseOrderRow]:
        suppliers = {row["id"]: row["name"] for row in self._suppliers()}
        warehouses = {row["id"]: row["name"] for row in self._warehouses()}
        rows = self._get("purchase_orders", {"select": "id,status,supplier_id,warehouse_id,total_amount,created_at,expected_delivery_date", "order": "created_at.desc", "limit": "100"})
        return [
            PurchaseOrderRow(
                id=str(row["id"]),
                status=str(row.get("status") or "draft"),
                supplier_name=suppliers.get(str(row.get("supplier_id")), "Unknown supplier"),
                warehouse_name=warehouses.get(str(row.get("warehouse_id")), "Unknown warehouse"),
                total_amount=float(row.get("total_amount") or 0),
                created_at=row.get("created_at") or datetime.now(timezone.utc).isoformat(),
                expected_delivery_date=row.get("expected_delivery_date"),
            )
            for row in rows
        ]

    def create_purchase_order(self, recommendation_id: str, *, user_id: str | None) -> PurchaseOrderRow:
        match = next((row for row in self.recommendations() if row.id == recommendation_id), None)
        if match is None:
            raise RepositoryError("recommendation not found")
        if match.approval_status != "approved":
            raise RepositoryError("purchase order requires an approved recommendation")
        if not match.supplier_id:
            raise RepositoryError("recommendation has no supplier")
        created = self._write(
            "purchase_orders",
            [
                {
                    "organization_id": self._organization_id(user_id),
                    "supplier_id": match.supplier_id,
                    "warehouse_id": match.warehouse_id,
                    "status": "pending_approval",
                    "total_amount": match.expected_cost,
                    "ai_generated": True,
                    "created_by": user_id,
                }
            ],
            returning=True,
        )
        order_id = created[0]["id"] if created else None
        if order_id:
            self._write(
                "purchase_order_items",
                [
                    {
                        "order_id": order_id,
                        "product_id": match.product_id,
                        "quantity": match.recommended_quantity,
                        "unit_price": match.expected_cost / match.recommended_quantity if match.recommended_quantity else 0,
                    }
                ],
            )
        self._write(
            "audit_logs",
            [
                {
                    "organization_id": self._organization_id(user_id),
                    "user_id": user_id,
                    "action": "purchase_order.created",
                    "entity_type": "purchase_order",
                    "entity_id": order_id,
                    "metadata": {"recommendation_id": recommendation_id, "quantity": match.recommended_quantity},
                }
            ],
        )
        return PurchaseOrderRow(
            id=str(order_id),
            status="pending_approval",
            supplier_name=match.supplier_name or "Unknown supplier",
            warehouse_name=match.warehouse_name,
            total_amount=match.expected_cost,
            created_at=datetime.now(timezone.utc).isoformat(),
            expected_delivery_date=None,
        )

    def audit_log(self, limit: int = 50) -> list[AuditEntry]:
        rows = self._get(
            "audit_logs",
            {"select": "id,action,entity_type,entity_id,metadata,created_at,user_id", "order": "created_at.desc", "limit": str(limit)},
        )
        return [
            AuditEntry(
                id=str(row["id"]),
                action=str(row.get("action") or "unknown"),
                entity_type=row.get("entity_type"),
                entity_id=str(row["entity_id"]) if row.get("entity_id") else None,
                metadata=row.get("metadata") or {},
                created_at=row.get("created_at") or datetime.now(timezone.utc).isoformat(),
                actor=(row.get("metadata") or {}).get("actor"),
            )
            for row in rows
        ]

    # ---------------------------------------------------------------- external signals

    def vessels(self, limit: int = 40) -> list[Vessel]:
        vessels = self._get(
            "vessels",
            {"select": "mmsi,name,call_sign,imo,ship_type,ship_type_label,destination,draught,last_seen_at", "order": "last_seen_at.desc", "limit": str(limit)},
        )
        positions = self._get(
            "vessel_positions",
            {"select": "mmsi,observed_at,latitude,longitude,speed_knots,course_degrees,nav_status_label", "order": "observed_at.desc", "limit": "400"},
        )
        latest: dict[int, dict[str, Any]] = {}
        for position in positions:
            latest.setdefault(int(position["mmsi"]), position)
        result = []
        for vessel in vessels:
            position = latest.get(int(vessel["mmsi"]), {})
            result.append(
                Vessel(
                    mmsi=int(vessel["mmsi"]),
                    name=vessel.get("name"),
                    call_sign=vessel.get("call_sign"),
                    imo=int(vessel["imo"]) if vessel.get("imo") else None,
                    ship_type_label=vessel.get("ship_type_label"),
                    destination=vessel.get("destination"),
                    draught=float(vessel["draught"]) if vessel.get("draught") is not None else None,
                    latitude=position.get("latitude"),
                    longitude=position.get("longitude"),
                    speed_knots=position.get("speed_knots"),
                    course_degrees=position.get("course_degrees"),
                    nav_status_label=position.get("nav_status_label"),
                    observed_at=position.get("observed_at") or vessel.get("last_seen_at"),
                )
            )
        return result

    def crop_indices(self, limit: int = 30) -> list[CropIndex]:
        rows = self._get(
            "crop_index_observations",
            {
                "select": "scene_id,aoi_name,crop,observation_date,ndvi_mean,ndvi_p10,ndvi_p90,health_score,cloud_pixel_percentage,valid_pixel_percentage",
                "order": "observation_date.desc",
                "limit": str(limit),
            },
        )
        return [
            CropIndex(
                scene_id=str(row["scene_id"]),
                aoi_name=str(row["aoi_name"]),
                crop=row.get("crop"),
                observation_date=str(row["observation_date"]),
                ndvi_mean=float(row.get("ndvi_mean") or 0),
                ndvi_p10=float(row.get("ndvi_p10") or 0),
                ndvi_p90=float(row.get("ndvi_p90") or 0),
                health_score=float(row.get("health_score") or 0),
                cloud_pixel_percentage=float(row.get("cloud_pixel_percentage") or 0),
                valid_pixel_percentage=float(row.get("valid_pixel_percentage") or 0),
            )
            for row in rows
        ]

    def agricultural_observations(self, limit: int = 40) -> list[AgriculturalObservation]:
        rows = self._get(
            "agricultural_observations",
            {
                "select": "dataset_code,region_label,item_label,element_label,year,value,unit",
                "element_label": "in.(Production,Domestic supply quantity,Import quantity,Export quantity)",
                "order": "year.desc,value.desc",
                "limit": str(limit),
            },
        )
        return [
            AgriculturalObservation(
                dataset_code=str(row["dataset_code"]),
                region=row.get("region_label") or "Unknown region",
                item=row.get("item_label") or "Unknown item",
                element=row.get("element_label") or "Unknown element",
                year=int(row["year"]),
                value=float(row.get("value") or 0),
                unit=row.get("unit"),
            )
            for row in rows
        ]

    def food_catalog(self, limit: int = 30, source: str | None = None) -> list[FoodCatalogItem]:
        params = {
            "select": "source,source_id,name,brand,category,allergens,nutriscore_grade,nova_group,data_type",
            "order": "observed_at.desc",
            "limit": str(limit),
        }
        if source:
            params["source"] = f"eq.{source}"
        rows = self._get("food_products", params)
        return [
            FoodCatalogItem(
                source=str(row["source"]),
                source_id=str(row["source_id"]),
                name=str(row["name"]),
                brand=row.get("brand"),
                category=row.get("category"),
                allergens=row.get("allergens") or [],
                nutriscore_grade=row.get("nutriscore_grade"),
                nova_group=int(row["nova_group"]) if row.get("nova_group") is not None else None,
                data_type=row.get("data_type"),
            )
            for row in rows
        ]

    def ingestion_runs(self, limit: int = 20) -> list[IngestionRun]:
        rows = self._get(
            "ingestion_runs",
            {"select": "provider,dataset_code,status,rows_written,started_at,finished_at,error_message", "order": "started_at.desc", "limit": str(limit)},
        )
        return [
            IngestionRun(
                provider=str(row["provider"]),
                dataset_code=str(row["dataset_code"]),
                status=str(row.get("status") or "unknown"),
                rows_written=int(row.get("rows_written") or 0),
                started_at=row.get("started_at") or datetime.now(timezone.utc).isoformat(),
                finished_at=row.get("finished_at"),
                error_message=row.get("error_message"),
            )
            for row in rows
        ]

    def external_signals(self) -> ExternalSignals:
        by_source = {
            source: self._count("food_products", {"source": f"eq.{source}"})
            for source in ("open_food_facts", "usda_fooddata")
        }
        return ExternalSignals(
            food_catalog_by_source=by_source,
            agricultural_observations=self._count("agricultural_observations"),
            crop_indices=self._count("crop_index_observations"),
            vessels=self._count("vessels", column="mmsi"),
            latest_runs=self.ingestion_runs(limit=8),
        )

    def health(self) -> dict[str, Any]:
        try:
            warehouses = self._get("warehouses", {"select": "id", "limit": "1"})
            return {"repository": "supabase", "reachable": True, "warehouse_rows": len(warehouses)}
        except (RepositoryError, httpx.HTTPError) as exc:
            return {"repository": "supabase", "reachable": False, "error": str(exc)[:200]}

    def profile(self, user_id: str) -> dict[str, Any] | None:
        rows = self._get("profiles", {"select": "role,organization_id,full_name", "id": f"eq.{user_id}", "limit": "1"})
        return rows[0] if rows else None

    def _organization_id(self, user_id: str | None) -> str | None:
        if not user_id:
            return None
        profile = self.profile(user_id)
        return str(profile["organization_id"]) if profile and profile.get("organization_id") else None
