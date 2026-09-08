# ML Pipeline

## Forecasting

1. Ingest validated sales, inventory, price, promotion, calendar, sentiment, supply, and logistics features.
2. Build warehouse × SKU daily features with lag and rolling windows.
3. Train an XGBoost/LightGBM regressor per segment with a seasonal naive baseline.
4. Produce 1/7/14/30-day horizons with prediction intervals from residual quantiles or quantile regression.
5. Store forecast rows and feature snapshots in PostgreSQL; model artifacts live in an object store.
6. Evaluate MAE, RMSE, MAPE, WAPE, bias, coverage, and segment-level degradation.

The initial runnable demo uses a deterministic seasonal baseline behind the same `ForecastProvider` interface. It never lets a language model supply numeric forecasts.

## Sentiment

Signals are cleaned, language-detected, classified, mapped to product/category, then aggregated by region and time bucket. Individual text is not returned to recommendation outputs. Confidence is a function of sample size, classifier confidence, and source quality.

## Satellite

Sentinel-2 tiles are cloud-filtered and transformed into NDVI, crop health, and crop stress features. These are supply-side features only; they do not claim to predict exact inventory demand on their own.

## Monitoring

Every forecast stores model name/version and feature snapshot references. A monitoring job checks data drift, prediction drift, forecast error, bias, stockout rate, waste rate, turnover, and service level. Alerts are emitted as structured events.
