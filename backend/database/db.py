"""SQLite database connection and initialization."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from backend.config import DB_PATH, DEMO_AIRLINES, DEMO_ROUTES, AIRPORT_NAMES


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS airlines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    code TEXT,
    is_active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS airports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    city TEXT,
    country TEXT DEFAULT 'India'
);

CREATE TABLE IF NOT EXISTS routes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    route_code TEXT NOT NULL UNIQUE,
    weight REAL DEFAULT 0.1,
    is_active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS airfare_observations_raw (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    airline TEXT NOT NULL,
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    route TEXT NOT NULL,
    travel_date TEXT NOT NULL,
    collection_timestamp TEXT NOT NULL,
    advance_purchase_days INTEGER,
    departure_time TEXT,
    arrival_time TEXT,
    fare_class TEXT DEFAULT 'Economy',
    base_fare REAL,
    taxes REAL,
    fees REAL,
    total_fare REAL,
    baggage TEXT,
    direct_or_connecting TEXT DEFAULT 'Direct',
    availability_status TEXT DEFAULT 'Available',
    data_mode TEXT DEFAULT 'demo',
    scraping_run_id INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS airfare_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_id INTEGER,
    source TEXT NOT NULL,
    airline TEXT NOT NULL,
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    route TEXT NOT NULL,
    travel_date TEXT NOT NULL,
    collection_timestamp TEXT NOT NULL,
    advance_purchase_days INTEGER,
    departure_time TEXT,
    arrival_time TEXT,
    fare_class TEXT DEFAULT 'Economy',
    base_fare REAL,
    taxes REAL,
    fees REAL,
    total_fare REAL,
    baggage TEXT,
    direct_or_connecting TEXT DEFAULT 'Direct',
    availability_status TEXT DEFAULT 'Available',
    data_mode TEXT DEFAULT 'demo',
    is_outlier INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (raw_id) REFERENCES airfare_observations_raw(id)
);

CREATE TABLE IF NOT EXISTS scraping_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    mode TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT DEFAULT 'running',
    records_collected INTEGER DEFAULT 0,
    error_message TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS index_values (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    index_date TEXT NOT NULL,
    frequency TEXT NOT NULL,
    index_value REAL NOT NULL,
    base_period_start TEXT,
    base_period_end TEXT,
    routes_count INTEGER,
    observations_count INTEGER,
    methodology TEXT DEFAULT 'APIx',
    data_mode TEXT DEFAULT 'demo',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(index_date, frequency, data_mode)
);

CREATE TABLE IF NOT EXISTS cleaning_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_timestamp TEXT NOT NULL,
    raw_records INTEGER,
    duplicates_removed INTEGER,
    invalid_records INTEGER,
    outliers_handled INTEGER,
    sold_out_removed INTEGER,
    final_observations INTEGER,
    data_mode TEXT DEFAULT 'demo'
);

CREATE TABLE IF NOT EXISTS reference_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    route TEXT NOT NULL,
    month TEXT NOT NULL,
    passenger_traffic REAL,
    average_fare REAL,
    source TEXT DEFAULT 'DGCA_SAMPLE',
    data_type TEXT DEFAULT 'DEMO_REFERENCE',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS anomalies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    route TEXT NOT NULL,
    airline TEXT,
    detection_date TEXT NOT NULL,
    normal_average REAL,
    current_average REAL,
    change_pct REAL,
    severity TEXT DEFAULT 'medium',
    method TEXT DEFAULT 'rolling_zscore',
    data_mode TEXT DEFAULT 'demo',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_obs_route ON airfare_observations(route);
CREATE INDEX IF NOT EXISTS idx_obs_travel_date ON airfare_observations(travel_date);
CREATE INDEX IF NOT EXISTS idx_obs_collection ON airfare_observations(collection_timestamp);
CREATE INDEX IF NOT EXISTS idx_obs_airline ON airfare_observations(airline);
CREATE INDEX IF NOT EXISTS idx_index_date ON index_values(index_date);
CREATE INDEX IF NOT EXISTS idx_raw_route ON airfare_observations_raw(route);
"""


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_db(db_path: Path | None = None):
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path | None = None):
    """Initialize database schema and seed reference data."""
    with get_db(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        _seed_airports(conn)
        _seed_airlines(conn)
        _seed_routes(conn)


def _seed_airports(conn: sqlite3.Connection):
    for code, name in AIRPORT_NAMES.items():
        city = name.split("(")[0].strip()
        conn.execute(
            "INSERT OR IGNORE INTO airports (code, name, city) VALUES (?, ?, ?)",
            (code, name, city),
        )


def _seed_airlines(conn: sqlite3.Connection):
    codes = {"IndiGo": "6E", "Air India": "AI", "Air India Express": "IX",
             "Akasa Air": "QP", "SpiceJet": "SG"}
    for name in DEMO_AIRLINES:
        conn.execute(
            "INSERT OR IGNORE INTO airlines (name, code) VALUES (?, ?)",
            (name, codes.get(name, "")),
        )


def _seed_routes(conn: sqlite3.Connection):
    for r in DEMO_ROUTES:
        route_code = f"{r['origin']}-{r['destination']}"
        conn.execute(
            "INSERT OR IGNORE INTO routes (origin, destination, route_code, weight) VALUES (?, ?, ?, ?)",
            (r["origin"], r["destination"], route_code, r["weight"]),
        )
