"""Simple anomaly detection for airfare price spikes."""
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from backend.config import DATA_MODE
from backend.database.db import get_db
from backend.models.models import AnomalyAlert

logger = logging.getLogger(__name__)


def detect_anomalies_rolling_zscore(
    df: pd.DataFrame,
    window: int = 7,
    threshold: float = 2.0,
) -> list[AnomalyAlert]:
    """
    Detect sudden fare increases using rolling mean + z-score.

    An alert fires when current route average exceeds rolling mean
    by more than `threshold` standard deviations.
    """
    alerts = []
    df = df.copy()
    df["collection_date"] = pd.to_datetime(df["collection_timestamp"]).dt.date.astype(str)

    for route in df["route"].unique():
        route_df = df[df["route"] == route].sort_values("collection_date")
        daily_avg = (
            route_df.groupby("collection_date")["total_fare"]
            .mean()
            .reset_index()
            .rename(columns={"total_fare": "avg_fare"})
        )

        if len(daily_avg) < window + 1:
            continue

        daily_avg["rolling_mean"] = daily_avg["avg_fare"].rolling(window, min_periods=3).mean()
        daily_avg["rolling_std"] = daily_avg["avg_fare"].rolling(window, min_periods=3).std()
        daily_avg["zscore"] = (
            (daily_avg["avg_fare"] - daily_avg["rolling_mean"]) / daily_avg["rolling_std"]
        )

        for _, row in daily_avg.iterrows():
            if pd.isna(row["zscore"]) or row["zscore"] < threshold:
                continue
            normal = row["rolling_mean"]
            current = row["avg_fare"]
            if normal <= 0:
                continue
            change_pct = ((current - normal) / normal) * 100
            severity = "high" if change_pct > 50 else "medium" if change_pct > 25 else "low"
            alerts.append(AnomalyAlert(
                route=route,
                detection_date=row["collection_date"],
                normal_average=round(normal, 0),
                current_average=round(current, 0),
                change_pct=round(change_pct, 1),
                severity=severity,
                method="rolling_zscore",
                data_mode=DATA_MODE,
            ))

    return alerts


def detect_anomalies_isolation_forest(df: pd.DataFrame) -> list[AnomalyAlert]:
    """Alternative: Isolation Forest on route-day aggregates."""
    from sklearn.ensemble import IsolationForest

    alerts = []
    df = df.copy()
    df["collection_date"] = pd.to_datetime(df["collection_timestamp"]).dt.date.astype(str)

    daily = (
        df.groupby(["route", "collection_date"])["total_fare"]
        .agg(["mean", "std", "count"])
        .reset_index()
    )
    daily.columns = ["route", "collection_date", "avg_fare", "std_fare", "count"]
    daily = daily.dropna()

    if len(daily) < 20:
        return alerts

    X = daily[["avg_fare", "std_fare", "count"]].values
    clf = IsolationForest(contamination=0.05, random_state=42)
    daily["anomaly"] = clf.fit_predict(X)

    route_means = daily.groupby("route")["avg_fare"].mean().to_dict()

    for _, row in daily[daily["anomaly"] == -1].iterrows():
        normal = route_means.get(row["route"], row["avg_fare"])
        current = row["avg_fare"]
        change_pct = ((current - normal) / normal) * 100 if normal > 0 else 0
        if change_pct > 15:
            alerts.append(AnomalyAlert(
                route=row["route"],
                detection_date=row["collection_date"],
                normal_average=round(normal, 0),
                current_average=round(current, 0),
                change_pct=round(change_pct, 1),
                severity="high" if change_pct > 50 else "medium",
                method="isolation_forest",
                data_mode=DATA_MODE,
            ))

    return alerts


def run_anomaly_detection(db_path=None, method: str = "rolling_zscore") -> list[dict]:
    """Run anomaly detection and store results."""
    with get_db(db_path) as conn:
        df = pd.read_sql("SELECT * FROM airfare_observations", conn)

    if df.empty:
        return []

    if method == "isolation_forest":
        alerts = detect_anomalies_isolation_forest(df)
    else:
        alerts = detect_anomalies_rolling_zscore(df)

    with get_db(db_path) as conn:
        conn.execute("DELETE FROM anomalies WHERE data_mode = ?", (DATA_MODE,))
        for a in alerts:
            conn.execute(
                """INSERT INTO anomalies
                   (route, airline, detection_date, normal_average, current_average,
                    change_pct, severity, method, data_mode)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (a.route, a.airline, a.detection_date, a.normal_average,
                 a.current_average, a.change_pct, a.severity, a.method, a.data_mode),
            )

    return [a.__dict__ for a in alerts]
