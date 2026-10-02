"""FastAPI backend for India Airfare Price Index prototype."""
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from backend.config import DATA_MODE, DB_PATH
from backend.database.db import get_db, init_db
from backend.schemas.schemas import (
    AirfareObservationResponse,
    AirlineResponse,
    AnomalyResponse,
    BacktestResponse,
    ForecastResponse,
    HealthResponse,
    IndexResponse,
    IndexTrendResponse,
    RouteResponse,
    StatsResponse,
)
from backend.analytics.anomaly import run_anomaly_detection
from backend.analytics.backtesting import run_backtest
from backend.analytics.forecast import forecast_route, forecast_index
from backend.index.calculator import get_index_change
from backend.services.cleaning import get_cleaning_stats

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Database initialized. Data mode: %s", DATA_MODE)
    yield


app = FastAPI(
    title="India Airfare Price Index (APIx) — Prototype",
    description=(
        "Prototype Real-time Airfare Price Index for India. "
        "NOT an official MoSPI CPI measure."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok",
        data_mode=DATA_MODE,
        database="connected" if DB_PATH.exists() else "not_initialized",
    )


@app.get("/airfares", response_model=list[AirfareObservationResponse])
def get_airfares(
    route: Optional[str] = None,
    airline: Optional[str] = None,
    origin: Optional[str] = None,
    destination: Optional[str] = None,
    advance_days: Optional[int] = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
):
    query = "SELECT * FROM airfare_observations WHERE 1=1"
    params = []
    if route:
        query += " AND route = ?"; params.append(route)
    if airline:
        query += " AND airline = ?"; params.append(airline)
    if origin:
        query += " AND origin = ?"; params.append(origin)
    if destination:
        query += " AND destination = ?"; params.append(destination)
    if advance_days:
        query += " AND advance_purchase_days = ?"; params.append(advance_days)
    query += " ORDER BY collection_timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


@app.get("/routes", response_model=list[RouteResponse])
def get_routes():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM routes WHERE is_active=1").fetchall()
    return [dict(r) for r in rows]


@app.get("/airlines", response_model=list[AirlineResponse])
def get_airlines():
    with get_db() as conn:
        rows = conn.execute("SELECT name, code FROM airlines WHERE is_active=1").fetchall()
    return [dict(r) for r in rows]


@app.get("/index", response_model=IndexResponse)
def get_index(frequency: str = "daily"):
    with get_db() as conn:
        row = conn.execute(
            """SELECT * FROM index_values WHERE frequency=? AND data_mode=?
               ORDER BY index_date DESC LIMIT 1""",
            (frequency, DATA_MODE),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Index not computed. Run data pipeline first.")
    return dict(row)


@app.get("/index/trend", response_model=IndexTrendResponse)
def get_index_trend(frequency: str = "daily", days: int = 30):
    with get_db() as conn:
        rows = conn.execute(
            """SELECT index_date, index_value FROM index_values
               WHERE frequency=? AND data_mode=? ORDER BY index_date DESC LIMIT ?""",
            (frequency, DATA_MODE, days),
        ).fetchall()
    if not rows:
        raise HTTPException(404, "No index trend data.")
    rows = list(reversed(rows))
    return IndexTrendResponse(
        dates=[r["index_date"] for r in rows],
        values=[r["index_value"] for r in rows],
        frequency=frequency,
        methodology="APIx_v1_weighted_median",
    )


@app.get("/index/changes")
def get_index_changes():
    return get_index_change()


@app.get("/route/{route}")
def get_route_detail(route: str):
    with get_db() as conn:
        obs = conn.execute(
            """SELECT collection_timestamp, total_fare, advance_purchase_days, airline
               FROM airfare_observations WHERE route=? AND is_outlier=0
               ORDER BY collection_timestamp""",
            (route,),
        ).fetchall()
        route_info = conn.execute(
            "SELECT * FROM routes WHERE route_code=?", (route,)
        ).fetchone()
    if not obs:
        raise HTTPException(404, f"No data for route {route}")
    return {
        "route": route,
        "weight": route_info["weight"] if route_info else None,
        "observations": len(obs),
        "data": [dict(o) for o in obs],
    }


@app.get("/anomalies", response_model=list[AnomalyResponse])
def get_anomalies(severity: Optional[str] = None, limit: int = 20):
    query = "SELECT * FROM anomalies WHERE data_mode=? ORDER BY change_pct DESC LIMIT ?"
    params = [DATA_MODE, limit]
    if severity:
        query = "SELECT * FROM anomalies WHERE data_mode=? AND severity=? ORDER BY change_pct DESC LIMIT ?"
        params = [DATA_MODE, severity, limit]
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


@app.get("/forecast")
def get_forecast(route: Optional[str] = None, days: int = 7):
    if route:
        return forecast_route(route, days)
    return forecast_index(days)


@app.get("/backtest", response_model=BacktestResponse)
def get_backtest():
    result = run_backtest()
    return BacktestResponse(**{k: v for k, v in result.items() if k in BacktestResponse.model_fields})


@app.get("/stats", response_model=StatsResponse)
def get_stats():
    with get_db() as conn:
        obs_count = conn.execute("SELECT COUNT(*) FROM airfare_observations").fetchone()[0]
        route_count = conn.execute("SELECT COUNT(*) FROM routes").fetchone()[0]
        airline_count = conn.execute("SELECT COUNT(*) FROM airlines").fetchone()[0]
        latest = conn.execute(
            "SELECT index_value FROM index_values WHERE frequency='daily' AND data_mode=? ORDER BY index_date DESC LIMIT 1",
            (DATA_MODE,),
        ).fetchone()
    changes = get_index_change()
    return StatsResponse(
        total_observations=obs_count,
        total_routes=route_count,
        total_airlines=airline_count,
        data_mode=DATA_MODE,
        latest_index=changes.get("current"),
        cleaning_stats=get_cleaning_stats(),
    )


@app.get("/leadtime/{route}")
def get_leadtime_analysis(route: str):
    with get_db() as conn:
        rows = conn.execute(
            """SELECT advance_purchase_days, AVG(total_fare) as avg_fare
               FROM airfare_observations WHERE route=? AND is_outlier=0
               GROUP BY advance_purchase_days ORDER BY advance_purchase_days DESC""",
            (route,),
        ).fetchall()
    if not rows:
        raise HTTPException(404, f"No lead-time data for {route}")
    return {
        "route": route,
        "windows": [{"advance_days": r["advance_purchase_days"], "avg_fare": round(r["avg_fare"], 0)} for r in rows],
    }


@app.get("/heatmap")
def get_heatmap():
    with get_db() as conn:
        rows = conn.execute(
            """SELECT route, origin, destination,
                      AVG(total_fare) as avg_fare,
                      COUNT(*) as obs_count
               FROM airfare_observations WHERE is_outlier=0
               GROUP BY route, origin, destination""",
        ).fetchall()

        # Get recent vs earlier for % change
        recent = conn.execute(
            """SELECT route, AVG(total_fare) as avg_fare
               FROM airfare_observations
               WHERE is_outlier=0 AND collection_timestamp >= (
                   SELECT MAX(collection_timestamp) FROM airfare_observations
               ) GROUP BY route""",
        ).fetchall()
        earlier = conn.execute(
            """SELECT route, AVG(total_fare) as avg_fare
               FROM airfare_observations
               WHERE is_outlier=0 AND collection_timestamp <= (
                   SELECT MIN(collection_timestamp) FROM airfare_observations
               ) GROUP BY route""",
        ).fetchall()

    recent_map = {r["route"]: r["avg_fare"] for r in recent}
    earlier_map = {r["route"]: r["avg_fare"] for r in earlier}

    result = []
    for r in rows:
        route = r["route"]
        earlier_fare = earlier_map.get(route, r["avg_fare"])
        recent_fare = recent_map.get(route, r["avg_fare"])
        pct_change = ((recent_fare - earlier_fare) / earlier_fare * 100) if earlier_fare else 0
        result.append({
            "route": route,
            "origin": r["origin"],
            "destination": r["destination"],
            "avg_fare": round(r["avg_fare"], 0),
            "pct_change": round(pct_change, 1),
            "obs_count": r["obs_count"],
        })
    return result
