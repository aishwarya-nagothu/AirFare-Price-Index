"""Data cleaning and normalization pipeline."""
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from backend.config import DATA_MODE
from backend.database.db import get_db
from backend.models.models import CleaningStats

logger = logging.getLogger(__name__)

AIRLINE_ALIASES = {
    "indigo": "IndiGo",
    "6e": "IndiGo",
    "air india": "Air India",
    "ai": "Air India",
    "spicejet": "SpiceJet",
    "sg": "SpiceJet",
    "akasa": "Akasa Air",
    "akasa air": "Akasa Air",
    "qp": "Akasa Air",
    "air india express": "Air India Express",
    "ix": "Air India Express",
}

MIN_FARE = 500
MAX_FARE = 100000

# Numeric stat fields persisted to SQLite — must be native int, not numpy.int64
_STAT_INT_FIELDS = (
    "raw_records",
    "duplicates_removed",
    "invalid_records",
    "outliers_handled",
    "sold_out_removed",
    "final_observations",
)


def _coerce_stat_int(value) -> int:
    """Convert pandas/numpy counts and legacy BLOB reads to native Python int."""
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, bytes):
        # SQLite stores numpy.int64 as 8-byte little-endian BLOB on some platforms
        return int.from_bytes(value, byteorder="little", signed=False)
    if isinstance(value, float):
        return int(value)
    return int(value)


def normalize_airline(name: str) -> str:
    if not name:
        return name
    key = name.strip().lower()
    return AIRLINE_ALIASES.get(key, name.strip())


def normalize_airport(code: str) -> str:
    if not code:
        return code
    return code.strip().upper()[:3]


def run_cleaning_pipeline(db_path=None) -> CleaningStats:
    """Clean raw observations and populate cleaned table."""
    stats = CleaningStats(run_timestamp=datetime.utcnow().isoformat(), data_mode=DATA_MODE)

    with get_db(db_path) as conn:
        df = pd.read_sql("SELECT * FROM airfare_observations_raw", conn)
        stats.raw_records = len(df)

        if df.empty:
            conn.execute("DELETE FROM airfare_observations")
            _save_stats(conn, stats)
            return stats

        # Normalize airline and airport codes
        df["airline"] = df["airline"].apply(normalize_airline)
        df["origin"] = df["origin"].apply(normalize_airport)
        df["destination"] = df["destination"].apply(normalize_airport)
        df["route"] = df["origin"] + "-" + df["destination"]

        # Remove sold-out / cancelled
        sold_out_mask = df["availability_status"].isin(["Sold Out", "Cancelled", "Unavailable"])
        stats.sold_out_removed = int(sold_out_mask.sum())
        df = df[~sold_out_mask]

        # Remove invalid fares
        invalid_mask = (
            df["total_fare"].isna()
            | (df["total_fare"] < MIN_FARE)
            | (df["total_fare"] > MAX_FARE)
        )
        stats.invalid_records = int(invalid_mask.sum())
        df = df[~invalid_mask]

        # Remove duplicates (same route, airline, travel_date, collection day, advance window)
        df["collection_date"] = pd.to_datetime(df["collection_timestamp"]).dt.date.astype(str)
        dup_cols = ["route", "airline", "travel_date", "collection_date", "advance_purchase_days"]
        before = len(df)
        df = df.drop_duplicates(subset=dup_cols, keep="first")
        stats.duplicates_removed = int(before - len(df))

        # Outlier detection using IQR per route
        df["is_outlier"] = 0
        for route in df["route"].unique():
            mask = df["route"] == route
            fares = df.loc[mask, "total_fare"]
            if len(fares) < 10:
                continue
            q1, q3 = fares.quantile(0.25), fares.quantile(0.75)
            iqr = q3 - q1
            lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            outlier_mask = mask & ((df["total_fare"] < lower) | (df["total_fare"] > upper))
            stats.outliers_handled += int(outlier_mask.sum())
            df.loc[outlier_mask, "is_outlier"] = 1
            # Cap outliers rather than remove (keep for anomaly detection)
            df.loc[outlier_mask & (df["total_fare"] > upper), "total_fare"] = upper
            df.loc[outlier_mask & (df["total_fare"] < lower), "total_fare"] = lower

        # Ensure base_fare + taxes + fees ≈ total_fare
        df["base_fare"] = df["base_fare"].fillna(df["total_fare"] * 0.82)
        df["taxes"] = df["taxes"].fillna(df["total_fare"] * 0.13)
        df["fees"] = df["fees"].fillna(df["total_fare"] * 0.05)

        stats.final_observations = len(df)

        # Write cleaned data
        conn.execute("DELETE FROM airfare_observations")
        clean_cols = [
            "id", "source", "airline", "origin", "destination", "route",
            "travel_date", "collection_timestamp", "advance_purchase_days",
            "departure_time", "arrival_time", "fare_class", "base_fare",
            "taxes", "fees", "total_fare", "baggage", "direct_or_connecting",
            "availability_status", "data_mode", "is_outlier",
        ]
        df["raw_id"] = df["id"]
        out_cols = ["raw_id"] + [c for c in clean_cols if c != "id"]
        out_df = df[out_cols].rename(columns={"raw_id": "raw_id"})
        out_df.to_sql("airfare_observations", conn, if_exists="append", index=False)

        _save_stats(conn, stats)

    logger.info(
        "Cleaning complete: raw=%d, final=%d, dups=%d, invalid=%d, outliers=%d",
        stats.raw_records, stats.final_observations,
        stats.duplicates_removed, stats.invalid_records, stats.outliers_handled,
    )
    return stats


def _save_stats(conn, stats: CleaningStats):
    conn.execute(
        """INSERT INTO cleaning_stats
           (run_timestamp, raw_records, duplicates_removed, invalid_records,
            outliers_handled, sold_out_removed, final_observations, data_mode)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            stats.run_timestamp,
            _coerce_stat_int(stats.raw_records),
            _coerce_stat_int(stats.duplicates_removed),
            _coerce_stat_int(stats.invalid_records),
            _coerce_stat_int(stats.outliers_handled),
            _coerce_stat_int(stats.sold_out_removed),
            _coerce_stat_int(stats.final_observations),
            stats.data_mode,
        ),
    )


def get_cleaning_stats(db_path=None) -> dict | None:
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM cleaning_stats ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row:
            result = dict(row)
            for field in _STAT_INT_FIELDS:
                if field in result:
                    result[field] = _coerce_stat_int(result[field])
            return result
    return None
