from __future__ import annotations

import pandas as pd


FEATURE_COLUMNS = [
    "rolling_sales_7d",
    "rolling_sales_30d",
    "rolling_sales_90d",
    "day_of_week",
    "month",
    "holiday",
    "price",
    "promotion",
    "regional_sentiment",
    "sentiment_change",
    "shipping_delay",
    "agricultural_supply",
    "crop_health",
]


def build_feature_frame(sales: pd.DataFrame) -> pd.DataFrame:
    """Create leakage-safe warehouse × SKU daily features.

    Input must contain date, warehouse_id, product_id, quantity. Optional signal
    columns are defaulted and retained so a provider outage cannot break training.
    """
    required = {"date", "warehouse_id", "product_id", "quantity"}
    missing = required.difference(sales.columns)
    if missing:
        raise ValueError(f"missing required sales columns: {sorted(missing)}")
    frame = sales.copy()
    frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["date", "warehouse_id", "product_id"])
    frame["quantity"] = pd.to_numeric(frame["quantity"], errors="coerce").fillna(0).clip(lower=0)
    defaults = {"price": 0.0, "promotion": 0.0, "regional_sentiment": 0.0, "sentiment_change": 0.0, "shipping_delay": 0.0, "agricultural_supply": 1.0, "crop_health": 1.0, "holiday": 0.0}
    for column, default in defaults.items():
        if column not in frame:
            frame[column] = default
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(default)
    frame = frame.sort_values(["warehouse_id", "product_id", "date"])
    keys = ["warehouse_id", "product_id"]
    grouped = frame.groupby(keys, sort=False)["quantity"]
    frame["rolling_sales_7d"] = grouped.transform(lambda values: values.shift(1).rolling(7, min_periods=1).mean())
    frame["rolling_sales_30d"] = grouped.transform(lambda values: values.shift(1).rolling(30, min_periods=1).mean())
    frame["rolling_sales_90d"] = grouped.transform(lambda values: values.shift(1).rolling(90, min_periods=1).mean())
    frame["day_of_week"] = frame["date"].dt.dayofweek
    frame["month"] = frame["date"].dt.month
    return frame.fillna(0).reset_index(drop=True)
