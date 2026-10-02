"""Application configuration."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DEMO_DIR = DATA_DIR / "demo"
REFERENCE_DIR = DATA_DIR / "reference"
DB_PATH = DATA_DIR / "airfare_index.db"

# Data mode: "demo" (default) or "live"
DATA_MODE = os.getenv("DATA_MODE", "demo")

# Index configuration
BASE_PERIOD_START = "2025-07-01"
BASE_PERIOD_END = "2025-07-07"
BASE_INDEX_VALUE = 100.0

# Demo routes with prototype weights (NOT official MoSPI weights)
DEMO_ROUTES = [
    {"origin": "DEL", "destination": "BOM", "weight": 0.18},
    {"origin": "DEL", "destination": "BLR", "weight": 0.14},
    {"origin": "BOM", "destination": "BLR", "weight": 0.12},
    {"origin": "DEL", "destination": "CCU", "weight": 0.08},
    {"origin": "BLR", "destination": "HYD", "weight": 0.10},
    {"origin": "MAA", "destination": "DEL", "weight": 0.08},
    {"origin": "HYD", "destination": "DEL", "weight": 0.08},
    {"origin": "BOM", "destination": "HYD", "weight": 0.07},
    {"origin": "DEL", "destination": "HYD", "weight": 0.08},
    {"origin": "BLR", "destination": "MAA", "weight": 0.07},
]

DEMO_AIRLINES = [
    "IndiGo",
    "Air India",
    "Air India Express",
    "Akasa Air",
    "SpiceJet",
]

ADVANCE_WINDOWS = [1, 7, 15, 30, 45]

AIRPORT_NAMES = {
    "DEL": "Delhi (Indira Gandhi Intl)",
    "BOM": "Mumbai (Chhatrapati Shivaji)",
    "BLR": "Bengaluru (Kempegowda)",
    "CCU": "Kolkata (Netaji Subhash Chandra Bose)",
    "HYD": "Hyderabad (Rajiv Gandhi)",
    "MAA": "Chennai (Chennai Intl)",
}

# Base fare ranges by route (INR) for synthetic data
ROUTE_BASE_FARES = {
    "DEL-BOM": 4500,
    "DEL-BLR": 4200,
    "BOM-BLR": 3800,
    "DEL-CCU": 4800,
    "BLR-HYD": 3200,
    "MAA-DEL": 4600,
    "HYD-DEL": 4400,
    "BOM-HYD": 3500,
    "DEL-HYD": 4300,
    "BLR-MAA": 2800,
}

API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
