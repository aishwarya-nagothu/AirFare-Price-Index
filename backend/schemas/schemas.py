"""Pydantic schemas for API validation."""
from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    data_mode: str
    database: str


class AirfareObservationResponse(BaseModel):
    id: int
    source: str
    airline: str
    origin: str
    destination: str
    route: str
    travel_date: str
    collection_timestamp: str
    advance_purchase_days: Optional[int]
    base_fare: Optional[float]
    taxes: Optional[float]
    fees: Optional[float]
    total_fare: Optional[float]
    availability_status: str
    data_mode: str


class RouteResponse(BaseModel):
    route_code: str
    origin: str
    destination: str
    weight: float


class AirlineResponse(BaseModel):
    name: str
    code: Optional[str]


class IndexResponse(BaseModel):
    index_date: str
    frequency: str
    index_value: float
    base_period_start: str
    base_period_end: str
    methodology: str
    data_mode: str
    label: str = "Prototype Airfare Price Index (APIx) — NOT official CPI"


class IndexTrendResponse(BaseModel):
    dates: list[str]
    values: list[float]
    frequency: str
    methodology: str


class AnomalyResponse(BaseModel):
    route: str
    airline: Optional[str]
    detection_date: str
    normal_average: float
    current_average: float
    change_pct: float
    severity: str


class ForecastResponse(BaseModel):
    route: str
    historical_dates: list[str]
    historical_values: list[float]
    forecast_dates: list[str]
    forecast_values: list[float]
    method: str
    label: str = "Experimental forecast — not official prediction"


class StatsResponse(BaseModel):
    total_observations: int
    total_routes: int
    total_airlines: int
    data_mode: str
    latest_index: Optional[float]
    cleaning_stats: Optional[dict]


class BacktestResponse(BaseModel):
    dates: list[str]
    apix_values: list[float]
    reference_values: list[float]
    correlation: Optional[float]
    mae: Optional[float]
    rmse: Optional[float]
    label: str = "Prototype validation — not official comparison"
