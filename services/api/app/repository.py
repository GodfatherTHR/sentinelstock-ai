from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from .inventory import InventoryPolicy, inventory_metrics
from .schemas import (
    Forecast,
    InventoryStatus,
    Product,
    Recommendation,
    Sentiment,
    Shipment,
    Supplier,
    Warehouse,
)


def now() -> datetime:
    return datetime.now(timezone.utc)


class DataRepository(Protocol):
    def warehouses(self) -> list[Warehouse]: ...
    def products(self) -> list[Product]: ...
    def inventory(self) -> list[InventoryStatus]: ...
    def forecasts(self) -> list[Forecast]: ...
    def sentiment(self) -> list[Sentiment]: ...
    def suppliers(self) -> list[Supplier]: ...
    def shipments(self) -> list[Shipment]: ...
    def recommendations(self) -> list[Recommendation]: ...


class DemoRepository:
    """Deterministic read model used until the Supabase adapter is configured."""

    def __init__(self) -> None:
        self._warehouses = [
            Warehouse(id="wh-dhaka", name="Dhaka Central", region="Dhaka", latitude=23.8103, longitude=90.4125, capacity=98000, utilization=0.78, inventory_value=1824000, risk_score=0.68, risk_level="HIGH", status="watch"),
            Warehouse(id="wh-ctg", name="Chattogram Port", region="Chattogram", latitude=22.3569, longitude=91.7832, capacity=72000, utilization=0.61, inventory_value=1298000, risk_score=0.44, risk_level="MEDIUM", status="stable"),
            Warehouse(id="wh-raj", name="Rajshahi North", region="Rajshahi", latitude=24.3745, longitude=88.6042, capacity=54000, utilization=0.49, inventory_value=864500, risk_score=0.29, risk_level="LOW", status="stable"),
            Warehouse(id="wh-syl", name="Sylhet East", region="Sylhet", latitude=24.8949, longitude=91.8687, capacity=42000, utilization=0.83, inventory_value=642700, risk_score=0.76, risk_level="CRITICAL", status="critical"),
        ]
        self._products = [
            Product(id="sku-oil-1", sku="OIL-1L-SUN", name="Sunflower Oil 1L", category="Cooking Oil", unit="case", shelf_life_days=365, is_perishable=False),
            Product(id="sku-rice-5", sku="RICE-5KG-BAS", name="Basmati Rice 5kg", category="Staples", unit="bag", shelf_life_days=540, is_perishable=False),
            Product(id="sku-milk-1", sku="MILK-1L-UHT", name="UHT Milk 1L", category="Dairy", unit="case", shelf_life_days=180, is_perishable=True),
            Product(id="sku-lentil-1", sku="DAL-1KG-RED", name="Red Lentils 1kg", category="Staples", unit="bag", shelf_life_days=360, is_perishable=False),
        ]
        product_by_id = {p.id: p for p in self._products}
        warehouse_by_id = {w.id: w for w in self._warehouses}
        raw_inventory = [
            ("inv-1", "wh-dhaka", "sku-oil-1", 4200, 540, 1800, 720, 6.2, 0.73),
            ("inv-2", "wh-dhaka", "sku-rice-5", 18800, 1200, 6200, 610, 29.7, 0.18),
            ("inv-3", "wh-dhaka", "sku-milk-1", 2600, 380, 900, 450, 4.8, 0.82),
            ("inv-4", "wh-ctg", "sku-oil-1", 6400, 460, 3200, 680, 13.4, 0.38),
            ("inv-5", "wh-ctg", "sku-rice-5", 14400, 900, 3500, 540, 25.0, 0.14),
            ("inv-6", "wh-raj", "sku-lentil-1", 9600, 430, 1300, 310, 33.2, 0.09),
            ("inv-7", "wh-syl", "sku-oil-1", 1600, 250, 400, 420, 3.8, 0.91),
            ("inv-8", "wh-syl", "sku-milk-1", 980, 180, 250, 210, 3.3, 0.94),
        ]
        self._inventory: list[InventoryStatus] = []
        for ident, warehouse_id, product_id, quantity, reserved, incoming, demand, days, probability in raw_inventory:
            product = product_by_id[product_id]
            warehouse = warehouse_by_id[warehouse_id]
            metrics = inventory_metrics(quantity, reserved, incoming, demand, 8 if product_id == "sku-oil-1" else 6, 38 if product_id == "sku-oil-1" else 22)
            self._inventory.append(InventoryStatus(id=ident, warehouse_id=warehouse_id, warehouse_name=warehouse.name, product_id=product_id, sku=product.sku, product_name=product.name, category=product.category, quantity=quantity, reserved=reserved, incoming=incoming, available_inventory=float(metrics["available_inventory"]), average_daily_demand=demand, days_of_inventory=days, safety_stock=float(metrics["safety_stock"]), reorder_point=float(metrics["reorder_point"]), stockout_probability=probability, excess_inventory=float(metrics["excess_inventory"]), inventory_risk="CRITICAL" if probability >= 0.85 else "HIGH" if probability >= 0.5 else "MEDIUM" if probability >= 0.25 else "LOW", unit_value=38 if product_id == "sku-oil-1" else 22, updated_at=now()))
        self._forecasts = [
            Forecast(warehouse_id="wh-dhaka", product_id="sku-oil-1", product_name="Sunflower Oil 1L", horizon="7d", predicted_demand=9850, lower_bound=9210, upper_bound=10540, confidence=0.91, model_name="seasonal_baseline", model_version="phase1.0", generated_at=now()),
            Forecast(warehouse_id="wh-dhaka", product_id="sku-oil-1", product_name="Sunflower Oil 1L", horizon="30d", predicted_demand=41400, lower_bound=36500, upper_bound=46800, confidence=0.84, model_name="seasonal_baseline", model_version="phase1.0", generated_at=now()),
            Forecast(warehouse_id="wh-syl", product_id="sku-oil-1", product_name="Sunflower Oil 1L", horizon="7d", predicted_demand=2940, lower_bound=2530, upper_bound=3440, confidence=0.87, model_name="seasonal_baseline", model_version="phase1.0", generated_at=now()),
            Forecast(warehouse_id="wh-dhaka", product_id="sku-milk-1", product_name="UHT Milk 1L", horizon="7d", predicted_demand=3680, lower_bound=3340, upper_bound=4050, confidence=0.88, model_name="seasonal_baseline", model_version="phase1.0", generated_at=now()),
        ]
        self._sentiment = [
            Sentiment(region="Dhaka", product_category="Cooking Oil", sentiment_score=0.72, sentiment_change=0.18, demand_signal=0.84, confidence=0.91, sample_count=1840, trend="rising"),
            Sentiment(region="Chattogram", product_category="Cooking Oil", sentiment_score=0.61, sentiment_change=0.06, demand_signal=0.68, confidence=0.88, sample_count=920, trend="rising"),
            Sentiment(region="Sylhet", product_category="Dairy", sentiment_score=0.48, sentiment_change=-0.12, demand_signal=0.54, confidence=0.82, sample_count=610, trend="falling"),
            Sentiment(region="Rajshahi", product_category="Staples", sentiment_score=0.66, sentiment_change=0.02, demand_signal=0.62, confidence=0.86, sample_count=740, trend="stable"),
        ]
        self._suppliers = [
            Supplier(id="sup-aci", name="ACI Consumer Brands", region="Dhaka", on_time_rate=0.93, lead_time_days=8, lead_time_variance_days=1.4, active_products=28, capacity_status="available"),
            Supplier(id="sup-meghna", name="Meghna Group Foods", region="Chattogram", on_time_rate=0.88, lead_time_days=10, lead_time_variance_days=2.3, active_products=19, capacity_status="constrained"),
            Supplier(id="sup-pran", name="PRAN-RFL Group", region="Rajshahi", on_time_rate=0.91, lead_time_days=7, lead_time_variance_days=1.8, active_products=23, capacity_status="available"),
        ]
        self._shipments = [
            Shipment(id="shp-4491", supplier_name="Meghna Group Foods", destination="Chattogram Port", vessel_id="MV Bengal Star", eta="12 Sep 2026", status="At sea · 67% complete", delay_days=2.0, risk_score=0.64, latitude=20.12, longitude=89.32),
            Shipment(id="shp-4484", supplier_name="ACI Consumer Brands", destination="Dhaka Central", vessel_id="Road convoy BD-22", eta="09 Sep 2026", status="In transit", delay_days=0.0, risk_score=0.18, latitude=23.45, longitude=90.11),
        ]
        self._recommendations: list[Recommendation] = [
            self._make_recommendation("rec-1001", "wh-dhaka", "sku-oil-1", 2400, "sup-aci", "HIGH", 0.73, 0.91, 9850, 4200, 6.2, 0.084, ["regional_demand_increase", "positive_consumer_sentiment", "supplier_lead_time_increase"], "pending"),
            self._make_recommendation("rec-1002", "wh-syl", "sku-milk-1", 1800, "sup-pran", "CRITICAL", 0.88, 0.86, 3680, 980, 3.3, 0.94, ["low_days_of_inventory", "perishable_shelf_life", "regional_supply_risk"], "pending"),
            self._make_recommendation("rec-0998", "wh-ctg", "sku-oil-1", 1600, "sup-meghna", "MEDIUM", 0.46, 0.89, 7200, 6400, 13.4, 0.38, ["demand_recovery", "capacity_available"], "approved"),
        ]

    def _make_recommendation(self, ident: str, warehouse_id: str, product_id: str, quantity: float, supplier_id: str, urgency: str, risk: float, confidence: float, forecast: float, current: float, days: float, stockout: float, drivers: list[str], status: str) -> Recommendation:
        warehouse = next(w for w in self._warehouses if w.id == warehouse_id)
        product = next(p for p in self._products if p.id == product_id)
        supplier = next(s for s in self._suppliers if s.id == supplier_id)
        return Recommendation(id=ident, decision_type="RESTOCK", warehouse_id=warehouse_id, warehouse_name=warehouse.name, product_id=product_id, product_name=product.name, sku=product.sku, recommended_quantity=quantity, supplier_id=supplier_id, supplier_name=supplier.name, urgency=urgency, risk_score=risk, confidence=confidence, forecast_demand=forecast, current_inventory=current, days_of_inventory=days, expected_stockout_probability=stockout, drivers=drivers, requires_human_approval=True, approval_status=status, expected_cost=quantity * (38 if product_id == "sku-oil-1" else 22), created_at=now(), explanation={"what": f"Order {quantity:,.0f} {product.unit}s of {product.name} for {warehouse.name}.", "how_much": f"The target covers the next forecast window plus safety stock while respecting the supplier case pack.", "when": f"Place the order now: {days:.1f} days of inventory is below the {supplier.lead_time_days}-day lead time envelope.", "from_where": f"{supplier.name} has {supplier.on_time_rate:.0%} on-time performance and the best available lead-time/capacity mix.", "why": "The recommendation is grounded in forecast demand, inventory coverage, aggregated regional sentiment, and supply risk signals.", "risk": "Demand may normalize faster than expected or the shipment may arrive late; approval and the next inventory event remain required.", "confidence": f"{confidence:.0%}; the demo uses a deterministic seasonal baseline until the trained forecasting adapter is enabled."})

    def warehouses(self) -> list[Warehouse]: return self._warehouses
    def products(self) -> list[Product]: return self._products
    def inventory(self) -> list[InventoryStatus]: return self._inventory
    def forecasts(self) -> list[Forecast]: return self._forecasts
    def sentiment(self) -> list[Sentiment]: return self._sentiment
    def suppliers(self) -> list[Supplier]: return self._suppliers
    def shipments(self) -> list[Shipment]: return self._shipments
    def recommendations(self) -> list[Recommendation]: return self._recommendations

    def add_recommendation(self, recommendation: Recommendation) -> None:
        self._recommendations.insert(0, recommendation)

    def update_recommendation(self, ident: str, status: str) -> Recommendation | None:
        for index, recommendation in enumerate(self._recommendations):
            if recommendation.id == ident:
                updated = recommendation.model_copy(update={"approval_status": status})
                self._recommendations[index] = updated
                return updated
        return None


repository = DemoRepository()
