"""Back-testing: compare APIx against reference/DGCA data."""
import logging

import numpy as np
import pandas as pd

from backend.config import DATA_MODE
from backend.database.db import get_db

logger = logging.getLogger(__name__)


def run_backtest(db_path=None) -> dict:
    """
    Compare prototype APIx index against reference average fare trends.

    Results are clearly labeled as prototype validation, NOT official comparison.
    """
    with get_db(db_path) as conn:
        index_df = pd.read_sql(
            """SELECT index_date, index_value FROM index_values
               WHERE frequency='daily' AND data_mode=? ORDER BY index_date""",
            conn, params=(DATA_MODE,),
        )
        ref_df = pd.read_sql(
            "SELECT route, month, average_fare, data_type FROM reference_data ORDER BY month",
            conn,
        )
        obs_df = pd.read_sql(
            """SELECT route, collection_timestamp, total_fare FROM airfare_observations
               WHERE is_outlier = 0""",
            conn,
        )

    if index_df.empty or ref_df.empty:
        return {
            "dates": [], "apix_values": [], "reference_values": [],
            "correlation": None, "mae": None, "rmse": None,
            "label": "Prototype validation — insufficient data",
        }

    # Build monthly reference index (normalized to 100 at first month)
    ref_monthly = ref_df.groupby("month")["average_fare"].mean().reset_index()
    ref_monthly.columns = ["month", "ref_fare"]
    base_fare = ref_monthly.iloc[0]["ref_fare"]
    ref_monthly["ref_index"] = (ref_monthly["ref_fare"] / base_fare) * 100

    # Build monthly APIx from daily index
    index_df["month"] = pd.to_datetime(index_df["index_date"]).dt.to_period("M").astype(str)
    apix_monthly = index_df.groupby("month")["index_value"].mean().reset_index()
    apix_monthly.columns = ["month", "apix_value"]

    merged = pd.merge(apix_monthly, ref_monthly, on="month", how="inner")

    if merged.empty:
        # Fall back to route-level comparison
        obs_df["month"] = pd.to_datetime(obs_df["collection_timestamp"]).dt.to_period("M").astype(str)
        obs_monthly = obs_df.groupby("month")["total_fare"].median().reset_index()
        obs_monthly.columns = ["month", "obs_fare"]
        base = obs_monthly.iloc[0]["obs_fare"] if not obs_monthly.empty else 1
        obs_monthly["obs_index"] = (obs_monthly["obs_fare"] / base) * 100

        merged = pd.merge(apix_monthly, obs_monthly, on="month", how="inner")
        if merged.empty:
            return {
                "dates": index_df["index_date"].tolist(),
                "apix_values": index_df["index_value"].tolist(),
                "reference_values": [],
                "correlation": None, "mae": None, "rmse": None,
                "label": "Prototype validation — DEMO_REFERENCE data",
            }
        ref_col = "obs_index"
    else:
        ref_col = "ref_index"

    dates = merged["month"].tolist()
    apix_vals = merged["apix_value"].round(2).tolist()
    ref_vals = merged[ref_col].round(2).tolist()

    correlation = float(np.corrcoef(apix_vals, ref_vals)[0, 1]) if len(apix_vals) > 1 else None
    errors = np.array(apix_vals) - np.array(ref_vals)
    mae = float(np.mean(np.abs(errors))) if len(errors) > 0 else None
    rmse = float(np.sqrt(np.mean(errors ** 2))) if len(errors) > 0 else None

    return {
        "dates": dates,
        "apix_values": apix_vals,
        "reference_values": ref_vals,
        "correlation": round(correlation, 3) if correlation is not None else None,
        "mae": round(mae, 2) if mae is not None else None,
        "rmse": round(rmse, 2) if rmse is not None else None,
        "label": "Prototype validation — NOT official MoSPI/DGCA comparison",
        "reference_type": ref_df["data_type"].iloc[0] if not ref_df.empty else "DEMO_REFERENCE",
    }
