"""
Prototype Airfare Price Index (APIx) Calculator.

IMPORTANT: This is an EXPERIMENTAL prototype index.
It is NOT the official MoSPI Consumer Price Index (CPI).

Methodology:
-----------
APIx(t) = 100 × Σ(w_r × P_r(t) / P_r(base)) / Σ(w_r)

Where:
  - w_r = prototype route weight (configurable, NOT official MoSPI weights)
  - P_r(t) = median total fare for route r on date t
             (averaged across airlines and advance-purchase windows)
  - P_r(base) = median total fare for route r during base period
  - Base period index = 100

Frequencies:
  - daily: computed per collection date
  - weekly: 7-day rolling average of daily index
  - monthly: calendar month average of daily index
"""
import logging
from datetime import datetime, timedelta

import pandas as pd

from backend.config import (
    BASE_INDEX_VALUE,
    BASE_PERIOD_END,
    BASE_PERIOD_START,
    DATA_MODE,
    DEMO_ROUTES,
)
from backend.database.db import get_db

logger = logging.getLogger(__name__)

METHODOLOGY = "APIx_v1_weighted_median"


def _get_route_weights() -> dict[str, float]:
    return {f"{r['origin']}-{r['destination']}": r["weight"] for r in DEMO_ROUTES}


def compute_route_medians(df: pd.DataFrame, date_col: str = "collection_date") -> pd.DataFrame:
    """Compute median fare per route per date."""
    return (
        df.groupby([date_col, "route"])["total_fare"]
        .median()
        .reset_index()
        .rename(columns={"total_fare": "median_fare"})
    )


def compute_daily_index(df: pd.DataFrame, weights: dict) -> pd.DataFrame:
    """Compute daily APIx values."""
    df = df.copy()
    df["collection_date"] = pd.to_datetime(df["collection_timestamp"]).dt.date.astype(str)

    medians = compute_route_medians(df)
    base_start = BASE_PERIOD_START
    base_end = BASE_PERIOD_END

    base_medians = (
        medians[(medians["collection_date"] >= base_start) & (medians["collection_date"] <= base_end)]
        .groupby("route")["median_fare"]
        .median()
        .to_dict()
    )

    if not base_medians:
        logger.warning("No base period data; using first 7 days as base.")
        first_dates = sorted(medians["collection_date"].unique())[:7]
        base_medians = (
            medians[medians["collection_date"].isin(first_dates)]
            .groupby("route")["median_fare"]
            .median()
            .to_dict()
        )

    results = []
    for date, group in medians.groupby("collection_date"):
        weighted_sum = 0.0
        weight_sum = 0.0
        obs_count = 0
        routes_used = 0

        for _, row in group.iterrows():
            route = row["route"]
            w = weights.get(route, 0.1)
            base_price = base_medians.get(route)
            if base_price and base_price > 0:
                ratio = row["median_fare"] / base_price
                weighted_sum += w * ratio
                weight_sum += w
                routes_used += 1

        route_obs = df[df["collection_date"] == date]
        obs_count = len(route_obs)

        if weight_sum > 0:
            index_val = BASE_INDEX_VALUE * (weighted_sum / weight_sum)
            results.append({
                "index_date": date,
                "frequency": "daily",
                "index_value": round(index_val, 2),
                "routes_count": routes_used,
                "observations_count": obs_count,
            })

    return pd.DataFrame(results)


def compute_weekly_index(daily_df: pd.DataFrame) -> pd.DataFrame:
    """7-day rolling average of daily index."""
    if daily_df.empty:
        return pd.DataFrame()
    daily_df = daily_df.sort_values("index_date")
    daily_df["index_value_smooth"] = daily_df["index_value"].rolling(7, min_periods=1).mean()
    return daily_df.assign(
        frequency="weekly",
        index_value=lambda d: d["index_value_smooth"].round(2),
    )[["index_date", "frequency", "index_value", "routes_count", "observations_count"]]


def compute_monthly_index(daily_df: pd.DataFrame) -> pd.DataFrame:
    """Calendar month average."""
    if daily_df.empty:
        return pd.DataFrame()
    daily_df = daily_df.copy()
    daily_df["month"] = pd.to_datetime(daily_df["index_date"]).dt.to_period("M").astype(str)
    monthly = (
        daily_df.groupby("month")
        .agg(index_value=("index_value", "mean"), routes_count=("routes_count", "max"),
             observations_count=("observations_count", "sum"))
        .reset_index()
        .rename(columns={"month": "index_date"})
    )
    monthly["frequency"] = "monthly"
    monthly["index_value"] = monthly["index_value"].round(2)
    return monthly


def compute_and_store_index(db_path=None) -> dict:
    """Compute all index frequencies and store in database."""
    weights = _get_route_weights()

    with get_db(db_path) as conn:
        df = pd.read_sql("SELECT * FROM airfare_observations WHERE is_outlier = 0", conn)
        if df.empty:
            logger.warning("No cleaned observations for index calculation.")
            return {"daily": 0, "weekly": 0, "monthly": 0}

        daily = compute_daily_index(df, weights)
        weekly = compute_weekly_index(daily)
        monthly = compute_monthly_index(daily)

        conn.execute("DELETE FROM index_values WHERE data_mode = ?", (DATA_MODE,))

        for idx_df in [daily, weekly, monthly]:
            for _, row in idx_df.iterrows():
                conn.execute(
                    """INSERT OR REPLACE INTO index_values
                       (index_date, frequency, index_value, base_period_start,
                        base_period_end, routes_count, observations_count,
                        methodology, data_mode)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (row["index_date"], row["frequency"], row["index_value"],
                     BASE_PERIOD_START, BASE_PERIOD_END,
                     int(row.get("routes_count", 0)), int(row.get("observations_count", 0)),
                     METHODOLOGY, DATA_MODE),
                )

    latest = daily.iloc[-1]["index_value"] if not daily.empty else None
    return {
        "daily_count": len(daily),
        "weekly_count": len(weekly),
        "monthly_count": len(monthly),
        "latest_index": latest,
    }


def get_index_change(db_path=None) -> dict:
    """Compute daily, weekly, monthly percentage changes."""
    with get_db(db_path) as conn:
        daily = pd.read_sql(
            "SELECT index_date, index_value FROM index_values WHERE frequency='daily' AND data_mode=? ORDER BY index_date",
            conn, params=(DATA_MODE,),
        )
    if daily.empty:
        return {"daily_change": 0, "weekly_change": 0, "monthly_change": 0, "current": None}

    current = daily.iloc[-1]["index_value"]
    daily_change = _pct_change(daily, 1, current)
    weekly_change = _pct_change(daily, 7, current)
    monthly_change = _pct_change(daily, 30, current)

    return {
        "current": round(current, 1),
        "daily_change": round(daily_change, 1),
        "weekly_change": round(weekly_change, 1),
        "monthly_change": round(monthly_change, 1),
    }


def _pct_change(df: pd.DataFrame, periods: int, current: float) -> float:
    if len(df) <= periods:
        return 0.0
    prev = df.iloc[-(periods + 1)]["index_value"]
    if prev == 0:
        return 0.0
    return ((current - prev) / prev) * 100
