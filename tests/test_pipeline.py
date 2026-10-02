"""Tests for the Airfare Price Index prototype."""
import os
import sys
import tempfile
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database.db import init_db, get_db
from backend.services.demo_generator import generate_demo_data, generate_reference_data
from backend.services.cleaning import (
    run_cleaning_pipeline,
    normalize_airline,
    normalize_airport,
    get_cleaning_stats,
    _coerce_stat_int,
    _STAT_INT_FIELDS,
)
from backend.index.calculator import compute_and_store_index, compute_daily_index, get_index_change
from backend.analytics.anomaly import detect_anomalies_rolling_zscore
from backend.config import DEMO_ROUTES


@pytest.fixture
def test_db():
    """Create a temporary test database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    init_db(db_path)
    generate_demo_data(days=10, db_path=db_path)
    generate_reference_data(db_path=db_path)
    run_cleaning_pipeline(db_path=db_path)
    compute_and_store_index(db_path=db_path)
    yield db_path
    db_path.unlink(missing_ok=True)


class TestDatabase:
    def test_init_db(self, test_db):
        with get_db(test_db) as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = {t["name"] for t in tables}
            assert "airfare_observations" in table_names
            assert "index_values" in table_names
            assert "airlines" in table_names
            assert "routes" in table_names

    def test_seed_data(self, test_db):
        with get_db(test_db) as conn:
            airlines = conn.execute("SELECT COUNT(*) FROM airlines").fetchone()[0]
            routes = conn.execute("SELECT COUNT(*) FROM routes").fetchone()[0]
            assert airlines == 5
            assert routes == 10


class TestDemoGenerator:
    def test_generates_records(self, test_db):
        with get_db(test_db) as conn:
            raw = conn.execute("SELECT COUNT(*) FROM airfare_observations_raw").fetchone()[0]
            assert raw > 0

    def test_has_multiple_routes(self, test_db):
        with get_db(test_db) as conn:
            routes = conn.execute(
                "SELECT DISTINCT route FROM airfare_observations_raw"
            ).fetchall()
            assert len(routes) >= 10


class TestCleaning:
    def test_normalizes_airline(self):
        assert normalize_airline("indigo") == "IndiGo"
        assert normalize_airline("6E") == "IndiGo"
        assert normalize_airline("Air India") == "Air India"

    def test_normalizes_airport(self):
        assert normalize_airport("del") == "DEL"
        assert normalize_airport(" BOM ") == "BOM"

    def test_removes_duplicates(self, test_db):
        with get_db(test_db) as conn:
            raw = conn.execute("SELECT COUNT(*) FROM airfare_observations_raw").fetchone()[0]
            clean = conn.execute("SELECT COUNT(*) FROM airfare_observations").fetchone()[0]
            assert clean <= raw

    def test_cleaning_stats(self, test_db):
        with get_db(test_db) as conn:
            stats = conn.execute("SELECT * FROM cleaning_stats ORDER BY id DESC LIMIT 1").fetchone()
            assert stats is not None
            assert stats["final_observations"] > 0


class TestIndexCalculation:
    def test_index_computed(self, test_db):
        with get_db(test_db) as conn:
            count = conn.execute("SELECT COUNT(*) FROM index_values WHERE frequency='daily'").fetchone()[0]
            assert count > 0

    def test_base_period_near_100(self, test_db):
        with get_db(test_db) as conn:
            rows = conn.execute(
                """SELECT index_value FROM index_values
                   WHERE frequency='daily' ORDER BY index_date LIMIT 3"""
            ).fetchall()
            for r in rows:
                assert 85 <= r["index_value"] <= 115

    def test_index_change(self, test_db):
        changes = get_index_change(test_db)
        assert "current" in changes
        assert "daily_change" in changes

    def test_daily_index_formula(self):
        df = pd.DataFrame({
            "collection_timestamp": ["2025-07-01"] * 4 + ["2025-07-02"] * 4,
            "route": ["DEL-BOM", "DEL-BLR", "DEL-BOM", "DEL-BLR"] * 2,
            "total_fare": [4500, 4200, 4600, 4300, 4700, 4400, 4800, 4500],
        })
        weights = {"DEL-BOM": 0.6, "DEL-BLR": 0.4}
        result = compute_daily_index(df, weights)
        assert not result.empty
        assert result.iloc[0]["index_value"] == pytest.approx(100.0, abs=5)


class TestAnomalyDetection:
    def test_detects_spike(self):
        dates = [f"2025-07-{d:02d}" for d in range(1, 15)]
        fares = [4000] * 12 + [7500, 7800]
        df = pd.DataFrame({
            "route": ["BLR-HYD"] * 14,
            "collection_timestamp": [f"{d}T08:00:00" for d in dates],
            "total_fare": fares,
        })
        alerts = detect_anomalies_rolling_zscore(df, window=5, threshold=1.5)
        assert len(alerts) > 0
        assert alerts[0].route == "BLR-HYD"


class TestAPI:
    def test_health_endpoint(self, test_db):
        from fastapi.testclient import TestClient
        import backend.config as cfg
        original = cfg.DB_PATH
        cfg.DB_PATH = test_db
        try:
            from backend.main import app
            client = TestClient(app)
            resp = client.get("/health")
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"
        finally:
            cfg.DB_PATH = original

    def test_routes_endpoint(self, test_db):
        from fastapi.testclient import TestClient
        import backend.config as cfg
        original = cfg.DB_PATH
        cfg.DB_PATH = test_db
        try:
            from backend.main import app
            client = TestClient(app)
            resp = client.get("/routes")
            assert resp.status_code == 200
            assert len(resp.json()) == 10
        finally:
            cfg.DB_PATH = original

    def test_index_endpoint(self, test_db):
        from fastapi.testclient import TestClient
        import backend.config as cfg
        original = cfg.DB_PATH
        cfg.DB_PATH = test_db
        try:
            from backend.main import app
            client = TestClient(app)
            resp = client.get("/index")
            assert resp.status_code == 200
            data = resp.json()
            assert "index_value" in data
            assert "APIx" in data["methodology"]
        finally:
            cfg.DB_PATH = original

    def test_stats_endpoint(self, test_db):
        from fastapi.testclient import TestClient
        import backend.config as cfg
        original = cfg.DB_PATH
        cfg.DB_PATH = test_db
        try:
            from backend.main import app
            client = TestClient(app)
            resp = client.get("/stats")
            assert resp.status_code == 200
            assert resp.json()["total_observations"] > 0
        finally:
            cfg.DB_PATH = original


class TestCleaningStatsTypes:
    """Regression tests for numpy.int64 → SQLite BLOB bytes issue."""

    def test_coerce_stat_int_from_bytes(self):
        assert _coerce_stat_int(b"\x00\x00\x00\x00\x00\x00\x00\x00") == 0
        assert _coerce_stat_int(b"\x0b\x00\x00\x00\x00\x00\x00\x00") == 11
        assert _coerce_stat_int(b"\r\x01\x00\x00\x00\x00\x00\x00") == 269

    def test_coerce_stat_int_from_numpy(self):
        import numpy as np
        assert _coerce_stat_int(np.int64(42)) == 42
        assert isinstance(_coerce_stat_int(np.int64(42)), int)

    def test_get_cleaning_stats_returns_native_ints(self, test_db):
        stats = get_cleaning_stats(test_db)
        assert stats is not None
        for field in _STAT_INT_FIELDS:
            value = stats[field]
            assert isinstance(value, int), f"{field} should be int, got {type(value)}"
            assert f"{value:,}"  # must not raise TypeError

    def test_legacy_blob_rows_decoded_on_read(self, test_db):
        """Simulate legacy rows stored when numpy.int64 was written as BLOB."""
        with get_db(test_db) as conn:
            conn.execute(
                """INSERT INTO cleaning_stats
                   (run_timestamp, raw_records, duplicates_removed, invalid_records,
                    outliers_handled, sold_out_removed, final_observations, data_mode)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "2025-01-01T00:00:00",
                    1000,
                    10,
                    b"\x05\x00\x00\x00\x00\x00\x00\x00",  # 5
                    b"\x0b\x00\x00\x00\x00\x00\x00\x00",  # 11
                    b"\r\x01\x00\x00\x00\x00\x00\x00",    # 269
                    900,
                    "demo",
                ),
            )

        stats = get_cleaning_stats(test_db)
        assert stats["invalid_records"] == 5
        assert stats["outliers_handled"] == 11
        assert stats["sold_out_removed"] == 269
        assert all(isinstance(stats[f], int) for f in _STAT_INT_FIELDS)


class TestDataQualityFormatting:
    def test_format_metric_value_handles_bytes(self):
        from frontend.app import format_metric_value

        assert format_metric_value(b"\x0b\x00\x00\x00\x00\x00\x00\x00") == "11"
        assert format_metric_value(8460) == "8,460"
        assert format_metric_value(None) == "—"

    def test_data_quality_metrics_format_without_error(self, test_db):
        """Reproduce Data Quality page metric formatting."""
        from frontend.app import format_metric_value

        stats = get_cleaning_stats(test_db)
        assert stats is not None
        metric_keys = [
            "raw_records",
            "duplicates_removed",
            "invalid_records",
            "outliers_handled",
            "sold_out_removed",
            "final_observations",
        ]
        for key in metric_keys:
            formatted = format_metric_value(stats[key])
            assert isinstance(formatted, str)
            assert formatted  # non-empty display string
