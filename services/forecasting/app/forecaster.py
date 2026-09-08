from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .features import FEATURE_COLUMNS, build_feature_frame


@dataclass(frozen=True)
class ForecastPoint:
    warehouse_id: str
    product_id: str
    horizon: int
    predicted_demand: float
    lower_bound: float
    upper_bound: float
    confidence: float
    model_name: str
    model_version: str


class SeasonalBaselineForecaster:
    """Robust baseline used when the trained model is unavailable or unsafe."""

    def __init__(self) -> None:
        self._means: dict[tuple[str, str, int], float] = {}
        self._residual_scale = 0.0

    def fit(self, sales: pd.DataFrame) -> "SeasonalBaselineForecaster":
        frame = build_feature_frame(sales)
        frame["day_of_week"] = pd.to_datetime(frame["date"]).dt.dayofweek
        self._means = frame.groupby(["warehouse_id", "product_id", "day_of_week"])["quantity"].mean().to_dict()
        residuals = frame.apply(lambda row: row["quantity"] - self._means.get((row["warehouse_id"], row["product_id"], row["day_of_week"]), row["quantity"]), axis=1)
        self._residual_scale = float(residuals.abs().median() * 1.65) if len(residuals) else 0.0
        return self

    def predict(self, scope: pd.DataFrame, horizon: int = 7) -> list[ForecastPoint]:
        if not self._means:
            raise RuntimeError("forecaster must be fit before predict")
        latest = scope.sort_values("date").groupby(["warehouse_id", "product_id"], as_index=False).tail(1)
        points: list[ForecastPoint] = []
        for _, row in latest.iterrows():
            value = self._means.get((row["warehouse_id"], row["product_id"], pd.Timestamp(row["date"]).dayofweek), float(row.get("rolling_sales_7d", 0)))
            total = max(float(value) * horizon, 0)
            interval = max(self._residual_scale * horizon, total * 0.08)
            points.append(ForecastPoint(str(row["warehouse_id"]), str(row["product_id"]), horizon, round(total, 3), round(max(total - interval, 0), 3), round(total + interval, 3), .72, "seasonal_baseline", "phase2.0"))
        return points


class XGBoostForecaster:
    """Optional trained adapter. It is only selected when xgboost is installed."""

    def __init__(self) -> None:
        self.model = None

    def fit(self, sales: pd.DataFrame) -> "XGBoostForecaster":
        from xgboost import XGBRegressor

        frame = build_feature_frame(sales)
        self.model = XGBRegressor(n_estimators=220, max_depth=5, learning_rate=.05, subsample=.8, colsample_bytree=.8, objective="reg:squarederror", random_state=42, n_jobs=2)
        self.model.fit(frame[FEATURE_COLUMNS], frame["quantity"])
        return self

    def predict(self, scope: pd.DataFrame, horizon: int = 7) -> list[ForecastPoint]:
        if self.model is None:
            raise RuntimeError("forecaster must be fit before predict")
        frame = build_feature_frame(scope)
        latest = frame.sort_values("date").groupby(["warehouse_id", "product_id"], as_index=False).tail(1)
        values = self.model.predict(latest[FEATURE_COLUMNS]) * horizon
        return [ForecastPoint(str(row.warehouse_id), str(row.product_id), horizon, round(max(float(value), 0), 3), round(max(float(value) * .82, 0), 3), round(max(float(value) * 1.18, 0), 3), .84, "xgboost", "phase2.0") for row, value in zip(latest.itertuples(), values)]


class ForecastService:
    """Stable orchestration seam: trained adapter when safe, baseline otherwise."""

    def __init__(self) -> None:
        self.model = SeasonalBaselineForecaster()

    def fit(self, sales: pd.DataFrame) -> str:
        if len(sales) >= 60:
            try:
                model = XGBoostForecaster().fit(sales)
                self.model = model
                return "xgboost"
            except (ImportError, ModuleNotFoundError):
                pass
        self.model = SeasonalBaselineForecaster().fit(sales)
        return "seasonal_baseline"

    def forecast(self, sales: pd.DataFrame, horizon: int = 7) -> list[ForecastPoint]:
        return self.model.predict(build_feature_frame(sales), horizon=horizon)
