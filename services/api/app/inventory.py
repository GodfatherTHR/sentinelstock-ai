from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InventoryPolicy:
    review_period_days: float = 7
    safety_stock_days: float = 4
    excess_threshold_days: float = 45
    critical_probability: float = 0.7


def inventory_metrics(
    quantity: float,
    reserved: float,
    incoming: float,
    average_daily_demand: float,
    lead_time_days: float,
    unit_value: float,
    policy: InventoryPolicy = InventoryPolicy(),
) -> dict[str, float | str]:
    available = max(quantity - reserved + incoming, 0)
    demand = max(average_daily_demand, 0.1)
    days = available / demand
    safety_stock = demand * policy.safety_stock_days
    reorder_point = demand * lead_time_days + safety_stock
    coverage_gap = max(lead_time_days - days, 0)
    stockout_probability = min(max(0.08 + coverage_gap * 0.19, 0.02), 0.98)
    excess = max(available - demand * policy.excess_threshold_days, 0)
    if available <= 0 or stockout_probability >= 0.75:
        level = "CRITICAL"
    elif available <= reorder_point or stockout_probability >= 0.5:
        level = "HIGH"
    elif available <= reorder_point * 1.25 or days < 18:
        level = "MEDIUM"
    else:
        level = "LOW"
    return {
        "available_inventory": round(available, 1),
        "days_of_inventory": round(days, 1),
        "safety_stock": round(safety_stock, 1),
        "reorder_point": round(reorder_point, 1),
        "stockout_probability": round(stockout_probability, 3),
        "excess_inventory": round(excess, 1),
        "inventory_risk": level,
        "inventory_value": round(available * unit_value, 2),
    }


def optimized_quantity(
    available_inventory: float,
    forecast_demand: float,
    safety_stock: float,
    incoming: float,
    minimum_order_quantity: float,
    case_pack: int = 1,
) -> float:
    target = max(forecast_demand + safety_stock, 0)
    raw = max(target - available_inventory - incoming, 0)
    quantity = max(raw, minimum_order_quantity if raw > 0 else 0)
    return float(round((quantity + case_pack - 1) / case_pack) * case_pack)
