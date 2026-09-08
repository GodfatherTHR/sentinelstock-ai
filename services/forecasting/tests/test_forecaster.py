import pandas as pd

from app.forecaster import ForecastService, SeasonalBaselineForecaster


def sample_sales(days: int = 14) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=days, freq="D", tz="UTC")
    return pd.DataFrame({"date": dates, "warehouse_id": "wh-1", "product_id": "sku-1", "quantity": [10 + (i % 3) for i in range(days)]})


def test_baseline_forecast_is_numeric_and_bounded():
    sales = sample_sales()
    model = SeasonalBaselineForecaster().fit(sales)
    points = model.predict(sales, horizon=7)
    assert points and points[0].predicted_demand >= 0
    assert 0 <= points[0].lower_bound <= points[0].predicted_demand <= points[0].upper_bound


def test_service_uses_safe_baseline_for_small_training_sets():
    sales = sample_sales()
    service = ForecastService()
    assert service.fit(sales) == "seasonal_baseline"
    assert service.forecast(sales)[0].model_name == "seasonal_baseline"
