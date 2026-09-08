from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
ApprovalStatus = Literal["pending", "approved", "rejected", "executed"]


class Warehouse(BaseModel):
    id: str
    name: str
    region: str
    latitude: float
    longitude: float
    capacity: int
    utilization: float
    inventory_value: float
    risk_score: float
    risk_level: RiskLevel
    status: Literal["stable", "watch", "critical"]


class Product(BaseModel):
    id: str
    sku: str
    name: str
    category: str
    unit: str
    shelf_life_days: int | None = None
    is_perishable: bool


class InventoryStatus(BaseModel):
    id: str
    warehouse_id: str
    warehouse_name: str
    product_id: str
    sku: str
    product_name: str
    category: str
    quantity: float
    reserved: float
    incoming: float
    available_inventory: float
    average_daily_demand: float
    days_of_inventory: float
    safety_stock: float
    reorder_point: float
    stockout_probability: float
    excess_inventory: float
    inventory_risk: RiskLevel
    unit_value: float
    updated_at: datetime


class Forecast(BaseModel):
    warehouse_id: str
    product_id: str
    product_name: str
    horizon: Literal["7d", "14d", "30d"]
    predicted_demand: float
    lower_bound: float
    upper_bound: float
    confidence: float
    model_name: str
    model_version: str
    generated_at: datetime


class Sentiment(BaseModel):
    region: str
    product_category: str
    sentiment_score: float
    sentiment_change: float
    demand_signal: float
    confidence: float
    sample_count: int
    trend: Literal["rising", "stable", "falling"]


class Supplier(BaseModel):
    id: str
    name: str
    region: str
    on_time_rate: float
    lead_time_days: int
    lead_time_variance_days: float
    active_products: int
    capacity_status: Literal["available", "constrained"]


class Shipment(BaseModel):
    id: str
    supplier_name: str
    destination: str
    vessel_id: str
    eta: str
    status: str
    delay_days: float
    risk_score: float
    latitude: float
    longitude: float


class Explanation(BaseModel):
    what: str
    how_much: str
    when: str
    from_where: str
    why: str
    risk: str
    confidence: str


class Recommendation(BaseModel):
    id: str
    decision_type: Literal["RESTOCK", "TRANSFER", "NO_ACTION"]
    warehouse_id: str
    warehouse_name: str
    product_id: str
    product_name: str
    sku: str
    recommended_quantity: float
    supplier_id: str | None
    supplier_name: str | None
    urgency: RiskLevel
    risk_score: float
    confidence: float
    forecast_demand: float
    current_inventory: float
    days_of_inventory: float
    expected_stockout_probability: float
    drivers: list[str]
    requires_human_approval: bool
    approval_status: ApprovalStatus
    expected_cost: float
    created_at: datetime
    explanation: Explanation


class GenerateRecommendationRequest(BaseModel):
    warehouse_id: str | None = None
    product_id: str | None = None


class PurchaseOrderRequest(BaseModel):
    decision_id: str
    note: str | None = Field(default=None, max_length=500)


class SimulationRequest(BaseModel):
    demand_delta_percent: float = Field(default=20, ge=-90, le=500)
    lead_time_delta_days: float = Field(default=0, ge=-30, le=90)
    crop_delta_percent: float = Field(default=0, ge=-90, le=100)
    sentiment_delta_percent: float = Field(default=0, ge=-100, le=500)


class SimulationResult(BaseModel):
    baseline: dict[str, float]
    scenario: dict[str, float]
    deltas: dict[str, float]
    assumptions: list[str]
