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
    lead_time_days: int
    minimum_order_quantity: float
    active_products: int
    active: bool = True


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
    source: str | None = None


class SalesPoint(BaseModel):
    day: str
    quantity: float


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


class Vessel(BaseModel):
    mmsi: int
    name: str | None = None
    call_sign: str | None = None
    imo: int | None = None
    ship_type_label: str | None = None
    destination: str | None = None
    draught: float | None = None
    latitude: float | None = None
    longitude: float | None = None
    speed_knots: float | None = None
    course_degrees: float | None = None
    nav_status_label: str | None = None
    observed_at: str | None = None


class CropIndex(BaseModel):
    scene_id: str
    aoi_name: str
    crop: str | None = None
    observation_date: str
    ndvi_mean: float
    ndvi_p10: float
    ndvi_p90: float
    health_score: float
    cloud_pixel_percentage: float
    valid_pixel_percentage: float


class AgriculturalObservation(BaseModel):
    dataset_code: str
    region: str
    item: str
    element: str
    year: int
    value: float
    unit: str | None = None


class FoodCatalogItem(BaseModel):
    source: str
    source_id: str
    name: str
    brand: str | None = None
    category: str | None = None
    allergens: list[str] = []
    nutriscore_grade: str | None = None
    nova_group: int | None = None
    data_type: str | None = None


class IngestionRun(BaseModel):
    provider: str
    dataset_code: str
    status: str
    rows_written: int
    started_at: str
    finished_at: str | None = None
    error_message: str | None = None


class ExternalSignals(BaseModel):
    food_catalog_by_source: dict[str, int]
    agricultural_observations: int
    crop_indices: int
    vessels: int
    latest_runs: list[IngestionRun]


class AuditEntry(BaseModel):
    id: str
    action: str
    entity_type: str | None = None
    entity_id: str | None = None
    metadata: dict = {}
    created_at: str
    actor: str | None = None


class PurchaseOrderRow(BaseModel):
    id: str
    status: str
    supplier_name: str
    warehouse_name: str
    total_amount: float
    created_at: str
    expected_delivery_date: str | None = None


class AgentAskRequest(BaseModel):
    query: str = Field(min_length=3, max_length=300)


class AgentAskResponse(BaseModel):
    query: str
    tool: str | None = None
    arguments: dict = {}
    summary: str
    rows: list[dict] = []
    confidence: float | None = None
    reasoning: str | None = None
    model: str
