"""Simple forecasting for airfare trends."""
import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from backend.config import DATA_MODE
from backend.database.db import get_db

logger = logging.getLogger(__name__)


def forecast_route(
    route: str,
    forecast_days: int = 7,
    db_path=None,
) -> dict:
    """
    Forecast short-term fare trend using linear regression on daily medians.

    Returns historical + forecast values. Clearly labeled as experimental.
    """
    with get_db(db_path) as conn:
        df = pd.read_sql(
            """SELECT collection_timestamp, total_fare FROM airfare_observations
               WHERE route = ? AND is_outlier = 0 ORDER BY collection_timestamp""",
            conn, params=(route,),
        )

    if df.empty or len(df) < 5:
        return {
            "route": route,
            "historical_dates": [],
            "historical_values": [],
            "forecast_dates": [],
            "forecast_values": [],
            "method": "linear_regression",
            "error": "Insufficient data for forecasting",
        }

    df["collection_date"] = pd.to_datetime(df["collection_timestamp"]).dt.date.astype(str)
    daily = df.groupby("collection_date")["total_fare"].median().reset_index()
    daily = daily.sort_values("collection_date")

    dates = daily["collection_date"].tolist()
    values = daily["total_fare"].tolist()

    X = np.arange(len(values)).reshape(-1, 1)
    y = np.array(values)

    model = LinearRegression()
    model.fit(X, y)

    last_date = datetime.strptime(dates[-1], "%Y-%m-%d")
    forecast_dates = []
    forecast_values = []

    for i in range(1, forecast_days + 1):
        future_x = len(values) + i - 1
        pred = model.predict([[future_x]])[0]
        pred = max(pred, 500)
        fd = (last_date + timedelta(days=i)).strftime("%Y-%m-%d")
        forecast_dates.append(fd)
        forecast_values.append(round(pred, 0))

    return {
        "route": route,
        "historical_dates": dates,
        "historical_values": [round(v, 0) for v in values],
        "forecast_dates": forecast_dates,
        "forecast_values": forecast_values,
        "method": "linear_regression",
        "label": "Experimental forecast — not official prediction",
    }


def forecast_index(forecast_days: int = 7, db_path=None) -> dict:
    """Forecast the overall APIx index."""
    with get_db(db_path) as conn:
        df = pd.read_sql(
            """SELECT index_date, index_value FROM index_values
               WHERE frequency='daily' AND data_mode=? ORDER BY index_date""",
            conn, params=(DATA_MODE,),
        )

    if df.empty or len(df) < 5:
        return {"error": "Insufficient index data"}

    dates = df["index_date"].tolist()
    values = df["index_value"].tolist()

    X = np.arange(len(values)).reshape(-1, 1)
    model = LinearRegression()
    model.fit(X, np.array(values))

    last_date = datetime.strptime(dates[-1], "%Y-%m-%d")
    forecast_dates, forecast_values = [], []

    for i in range(1, forecast_days + 1):
        pred = model.predict([[len(values) + i - 1]])[0]
        fd = (last_date + timedelta(days=i)).strftime("%Y-%m-%d")
        forecast_dates.append(fd)
        forecast_values.append(round(pred, 2))

    return {
        "historical_dates": dates,
        "historical_values": values,
        "forecast_dates": forecast_dates,
        "forecast_values": forecast_values,
        "method": "linear_regression",
    }
