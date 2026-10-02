"""Domain models for airfare observations."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class AirfareObservation:
    source: str
    airline: str
    origin: str
    destination: str
    route: str
    travel_date: str
    collection_timestamp: str
    advance_purchase_days: int
    base_fare: float
    taxes: float
    fees: float
    total_fare: float
    departure_time: str = "06:00"
    arrival_time: str = "08:30"
    fare_class: str = "Economy"
    baggage: str = "15 kg"
    direct_or_connecting: str = "Direct"
    availability_status: str = "Available"
    data_mode: str = "demo"
    raw_id: Optional[int] = None
    id: Optional[int] = None
    is_outlier: int = 0

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


@dataclass
class IndexValue:
    index_date: str
    frequency: str
    index_value: float
    base_period_start: str
    base_period_end: str
    routes_count: int = 0
    observations_count: int = 0
    methodology: str = "APIx"
    data_mode: str = "demo"


@dataclass
class CleaningStats:
    run_timestamp: str
    raw_records: int = 0
    duplicates_removed: int = 0
    invalid_records: int = 0
    outliers_handled: int = 0
    sold_out_removed: int = 0
    final_observations: int = 0
    data_mode: str = "demo"


@dataclass
class AnomalyAlert:
    route: str
    detection_date: str
    normal_average: float
    current_average: float
    change_pct: float
    airline: Optional[str] = None
    severity: str = "medium"
    method: str = "rolling_zscore"
    data_mode: str = "demo"
