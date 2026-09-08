from datetime import datetime

import pandas as pd
from fastapi import FastAPI
from pydantic import BaseModel, Field

from .forecaster import ForecastService

app = FastAPI(title="SentinelStock Forecasting Service", version="0.2.0")
service = ForecastService()


class SalesRecord(BaseModel):
    date: datetime
    warehouse_id: str
    product_id: str
    quantity: float = Field(ge=0)
    price: float = 0
    promotion: float = 0
    regional_sentiment: float = 0
    sentiment_change: float = 0
    shipping_delay: float = 0
    agricultural_supply: float = 1
    crop_health: float = 1
    holiday: float = 0


class ForecastRequest(BaseModel):
    sales: list[SalesRecord]
    horizon: int = Field(default=7, ge=1, le=30)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "forecasting", "model_policy": "xgboost-with-baseline-fallback"}


@app.post("/forecast")
def forecast(request: ForecastRequest):
    frame = pd.DataFrame([record.model_dump() for record in request.sales])
    model_name = service.fit(frame)
    points = service.forecast(frame, request.horizon)
    return {"model_name": model_name, "horizon": request.horizon, "forecasts": [point.__dict__ for point in points]}
