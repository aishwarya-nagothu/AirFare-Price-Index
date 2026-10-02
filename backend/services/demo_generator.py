"""Generate realistic synthetic airfare data for DEMO mode."""
import random
import sqlite3
from datetime import datetime, timedelta

import numpy as np

from backend.config import (
    ADVANCE_WINDOWS,
    BASE_DIR,
    DATA_MODE,
    DEMO_AIRLINES,
    DEMO_ROUTES,
    ROUTE_BASE_FARES,
)
from backend.database.db import get_db, init_db


# Airline price multipliers (IndiGo typically cheapest, Air India premium)
AIRLINE_MULTIPLIERS = {
    "IndiGo": 0.92,
    "SpiceJet": 0.95,
    "Akasa Air": 0.98,
    "Air India Express": 1.05,
    "Air India": 1.12,
}

DEPARTURE_TIMES = [
    ("06:00", "08:30"), ("08:15", "10:45"), ("11:00", "13:30"),
    ("14:30", "17:00"), ("18:00", "20:30"), ("20:45", "23:15"),
]


def _route_key(origin: str, destination: str) -> str:
    return f"{origin}-{destination}"


def _seasonal_factor(date: datetime) -> float:
    """Simulate seasonal demand — higher in Dec-Jan, Oct (festivals)."""
    month = date.month
    if month in (12, 1):
        return 1.15
    if month in (10, 11):
        return 1.10
    if month in (6, 7, 8):
        return 0.95
    return 1.0


def _weekend_factor(date: datetime) -> float:
    return 1.08 if date.weekday() >= 5 else 1.0


def _advance_purchase_factor(days: int) -> float:
    """Prices increase as departure approaches."""
    factors = {45: 0.75, 30: 0.85, 15: 1.0, 7: 1.25, 1: 1.55}
    return factors.get(days, 1.0)


def _generate_fare(
    route: str,
    airline: str,
    collection_date: datetime,
    travel_date: datetime,
    advance_days: int,
    inject_anomaly: bool = False,
) -> dict | None:
    base = ROUTE_BASE_FARES.get(route, 4000)
    airline_mult = AIRLINE_MULTIPLIERS.get(airline, 1.0)
    seasonal = _seasonal_factor(travel_date)
    weekend = _weekend_factor(travel_date)
    advance = _advance_purchase_factor(advance_days)

    # Trend: prices drift upward over the 30-day collection period
    days_from_start = (collection_date - datetime(2025, 7, 1)).days
    trend = 1.0 + (days_from_start / 30) * 0.12

    noise = random.uniform(0.92, 1.08)
    base_fare = base * airline_mult * seasonal * weekend * advance * trend * noise

    # Inject anomaly for BLR-HYD around day 20-22
    if inject_anomaly and route == "BLR-HYD":
        base_fare *= random.uniform(1.7, 1.9)

    base_fare = round(base_fare, 0)
    taxes = round(base_fare * random.uniform(0.12, 0.18), 0)
    fees = round(random.uniform(200, 600), 0)
    total = base_fare + taxes + fees

    # Simulate sold-out (~3%)
    if random.random() < 0.03:
        return {
            "base_fare": None, "taxes": None, "fees": None,
            "total_fare": None, "availability_status": "Sold Out",
        }

    dep, arr = random.choice(DEPARTURE_TIMES)
    return {
        "base_fare": base_fare,
        "taxes": taxes,
        "fees": fees,
        "total_fare": total,
        "availability_status": "Available",
        "departure_time": dep,
        "arrival_time": arr,
    }


def generate_demo_data(
    days: int = 35,
    start_date: str = "2025-07-01",
    db_path=None,
) -> dict:
    """Generate synthetic airfare observations and load into database."""
    init_db(db_path)
    start = datetime.strptime(start_date, "%Y-%m-%d")
    records = []

    with get_db(db_path) as conn:
        # Clear existing demo data
        conn.execute("DELETE FROM airfare_observations")
        conn.execute("DELETE FROM airfare_observations_raw")
        conn.execute("DELETE FROM index_values")
        conn.execute("DELETE FROM anomalies")
        conn.execute("DELETE FROM cleaning_stats")

        run_id = conn.execute(
            """INSERT INTO scraping_runs (source, mode, started_at, status)
               VALUES (?, ?, ?, ?)""",
            ("demo_generator", "demo", datetime.utcnow().isoformat(), "running"),
        ).lastrowid

        for day_offset in range(days):
            collection_date = start + timedelta(days=day_offset)
            collection_ts = collection_date.replace(hour=8, minute=0).isoformat()

            for route_info in DEMO_ROUTES:
                origin = route_info["origin"]
                dest = route_info["destination"]
                route = _route_key(origin, dest)

                for airline in DEMO_AIRLINES:
                    for advance in ADVANCE_WINDOWS:
                        travel_date = collection_date + timedelta(days=advance)
                        inject = (day_offset in (20, 21, 22) and route == "BLR-HYD"
                                  and advance in (7, 15))

                        fare_data = _generate_fare(
                            route, airline, collection_date, travel_date,
                            advance, inject_anomaly=inject,
                        )
                        if fare_data is None:
                            continue

                        record = {
                            "source": "DEMO_SYNTHETIC",
                            "airline": airline,
                            "origin": origin,
                            "destination": dest,
                            "route": route,
                            "travel_date": travel_date.strftime("%Y-%m-%d"),
                            "collection_timestamp": collection_ts,
                            "advance_purchase_days": advance,
                            "fare_class": "Economy",
                            "baggage": "15 kg",
                            "direct_or_connecting": "Direct",
                            "data_mode": "demo",
                            "scraping_run_id": run_id,
                            **fare_data,
                        }
                        records.append(record)

        # Insert raw records (include some duplicates intentionally)
        dup_count = 0
        for i, rec in enumerate(records):
            conn.execute(
                """INSERT INTO airfare_observations_raw
                   (source, airline, origin, destination, route, travel_date,
                    collection_timestamp, advance_purchase_days, departure_time,
                    arrival_time, fare_class, base_fare, taxes, fees, total_fare,
                    baggage, direct_or_connecting, availability_status, data_mode,
                    scraping_run_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (rec["source"], rec["airline"], rec["origin"], rec["destination"],
                 rec["route"], rec["travel_date"], rec["collection_timestamp"],
                 rec["advance_purchase_days"], rec.get("departure_time", "06:00"),
                 rec.get("arrival_time", "08:30"), rec["fare_class"],
                 rec.get("base_fare"), rec.get("taxes"), rec.get("fees"),
                 rec.get("total_fare"), rec["baggage"], rec["direct_or_connecting"],
                 rec.get("availability_status", "Available"), rec["data_mode"],
                 rec["scraping_run_id"]),
            )
            # Inject ~1% duplicates
            if random.random() < 0.01:
                dup_count += 1
                conn.execute(
                    """INSERT INTO airfare_observations_raw
                       (source, airline, origin, destination, route, travel_date,
                        collection_timestamp, advance_purchase_days, departure_time,
                        arrival_time, fare_class, base_fare, taxes, fees, total_fare,
                        baggage, direct_or_connecting, availability_status, data_mode,
                        scraping_run_id)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (rec["source"], rec["airline"], rec["origin"], rec["destination"],
                     rec["route"], rec["travel_date"], rec["collection_timestamp"],
                     rec["advance_purchase_days"], rec.get("departure_time", "06:00"),
                     rec.get("arrival_time", "08:30"), rec["fare_class"],
                     rec.get("base_fare"), rec.get("taxes"), rec.get("fees"),
                     rec.get("total_fare"), rec["baggage"], rec["direct_or_connecting"],
                     rec.get("availability_status", "Available"), rec["data_mode"],
                     rec["scraping_run_id"]),
                )

        conn.execute(
            "UPDATE scraping_runs SET completed_at=?, status=?, records_collected=? WHERE id=?",
            (datetime.utcnow().isoformat(), "completed", len(records) + dup_count, run_id),
        )

    return {
        "raw_records": len(records) + dup_count,
        "duplicates_injected": dup_count,
        "collection_days": days,
        "routes": len(DEMO_ROUTES),
        "airlines": len(DEMO_AIRLINES),
    }


def generate_reference_data(db_path=None):
    """Generate sample DGCA-style reference data (clearly marked as DEMO)."""
    init_db(db_path)
    months = ["2025-05", "2025-06", "2025-07", "2025-08"]
    traffic_base = {
        "DEL-BOM": 850000, "DEL-BLR": 620000, "BOM-BLR": 480000,
        "DEL-CCU": 320000, "BLR-HYD": 280000, "MAA-DEL": 350000,
        "HYD-DEL": 310000, "BOM-HYD": 240000, "DEL-HYD": 290000,
        "BLR-MAA": 220000,
    }

    with get_db(db_path) as conn:
        conn.execute("DELETE FROM reference_data")
        for route_info in DEMO_ROUTES:
            route = _route_key(route_info["origin"], route_info["destination"])
            base_fare = ROUTE_BASE_FARES.get(route, 4000)
            base_traffic = traffic_base.get(route, 200000)
            for i, month in enumerate(months):
                fare = base_fare * (1 + i * 0.04 + random.uniform(-0.02, 0.02))
                traffic = base_traffic * (1 + i * 0.02)
                conn.execute(
                    """INSERT INTO reference_data
                       (route, month, passenger_traffic, average_fare, source, data_type)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (route, month, round(traffic), round(fare, 0),
                     "DGCA_SAMPLE", "DEMO_REFERENCE"),
                )
