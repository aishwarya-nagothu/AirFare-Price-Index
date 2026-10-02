# 🇮🇳 India Airfare Price Index (APIx) — Prototype

> **Prototype / Experimental Airfare Price Index — NOT Official MoSPI CPI**

A functional prototype demonstrating how airfare prices can be automatically collected, cleaned, normalized, analyzed, and converted into a Real-time Airfare Price Index for India — designed as a potential augmentation to the Consumer Price Index (CPI).

**Hackathon Problem Statement 26056** — Ministry of Statistics and Programme Implementation (MoSPI)

Official Reference Portal: [eSankhyiki — MoSPI](https://esankhyiki.mospi.gov.in/)

---

## Quick Start (5-Minute Demo)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Generate demo data & compute index
python scripts/generate_demo_data.py

# 3. Launch dashboard
streamlit run frontend/app.py

# 4. (Optional) Start API backend
uvicorn backend.main:app --reload --port 8000
```

Open http://localhost:8501 for the dashboard, http://localhost:8000/docs for API docs.

---

## Architecture

```
Airfare Sources (Demo / Live Scrapers)
        ↓
Data Collection (Playwright / Synthetic Generator)
        ↓
Cleaning & Normalization Pipeline
        ↓
SQLite Database
        ↓
Airfare Price Index (APIx) Calculation
        ↓
Analytics (Anomaly Detection, Forecasting, Back-Testing)
        ↓
Streamlit Dashboard + FastAPI
```

## Data Modes

| Mode | Description | Default |
|------|-------------|---------|
| **DEMO** | Realistic synthetic data (35 days, 10 routes, 5 airlines) | ✅ Yes |
| **LIVE** | Modular scraper architecture (placeholder adapters) | No |

Set via environment: `DATA_MODE=demo` or `DATA_MODE=live`

## Project Structure

```
backend/
    main.py                 # FastAPI application
    config.py               # Configuration & constants
    database/db.py          # SQLite schema & connection
    models/models.py        # Domain models
    schemas/schemas.py      # Pydantic API schemas
    services/
        demo_generator.py   # Synthetic data generator
        cleaning.py         # Data cleaning pipeline
    scrapers/
        base.py             # Abstract scraper interface
        demo_scraper.py     # Demo mode adapter
        makemytrip.py       # Live OTA adapter (placeholder)
    index/calculator.py     # APIx index computation
    analytics/
        anomaly.py          # Anomaly detection
        forecast.py         # Simple forecasting
        backtesting.py      # Index vs reference comparison
frontend/
    app.py                  # Streamlit dashboard
data/
    demo/                   # Generated demo data
    reference/              # DGCA sample reference CSV
scripts/
    generate_demo_data.py   # Full data pipeline script
    import_data.py          # Import reference CSV/Excel
tests/
    test_pipeline.py        # Comprehensive test suite
```

## Index Methodology (APIx v1)

```
APIx(t) = 100 × Σ(w_r × P_r(t) / P_r(base)) / Σ(w_r)
```

- `w_r` = prototype route weight (configurable, NOT official MoSPI weights)
- `P_r(t)` = median total fare for route r on date t
- `P_r(base)` = median fare during base period (2025-07-01 to 2025-07-07)
- Base period index = **100**

**Frequencies:** Daily, Weekly (7-day rolling), Monthly

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `GET /airfares` | Query airfare observations |
| `GET /routes` | List tracked routes |
| `GET /airlines` | List airlines |
| `GET /index` | Latest index value |
| `GET /index/trend` | Index time series |
| `GET /index/changes` | Daily/weekly/monthly changes |
| `GET /route/{route}` | Route detail |
| `GET /anomalies` | Anomaly alerts |
| `GET /forecast` | Experimental forecast |
| `GET /backtest` | Back-testing results |
| `GET /stats` | System statistics |
| `GET /leadtime/{route}` | Lead-time analysis |
| `GET /heatmap` | Route heatmap data |

## Dashboard Features

- **KPI Cards:** Current APIx, daily/weekly/monthly changes
- **Index Trend Chart:** Daily/weekly/monthly with base period line
- **Route Analysis:** 30-day price trends, airline comparison
- **Route Heatmap:** Origin→Destination fare change matrix
- **Lead-Time Analysis:** T+1 through T+45 booking window curves
- **Anomaly Alerts:** Rolling z-score detection with severity levels
- **Forecasting:** Linear regression short-term predictions
- **Back-Testing:** APIx vs DGCA reference comparison
- **Methodology Page:** Full documentation
- **Data Quality Report:** Cleaning statistics

## Running Tests

```bash
pytest tests/ -v
```

## Docker

```bash
docker-compose up --build
```

Dashboard: http://localhost:8501 | API: http://localhost:8000

## Importing Reference Data

```bash
python scripts/import_data.py data/reference/dgca_sample_reference.csv DGCA_SAMPLE DEMO_REFERENCE
```

For official government data, set `data_type=OFFICIAL_REFERENCE`.

## Demo Scenario Walkthrough

1. Open dashboard → see current Airfare Index (~112-127)
2. Select DEL → BOM → view 30-day price trend
3. Lead-Time Analysis → compare T+1 vs T+45 fares
4. Route heatmap → identify expensive corridors
5. Anomalies → see BLR-HYD spike alert (+85%)
6. Forecast → experimental 7-day prediction
7. Back-Testing → APIx vs reference correlation
8. Methodology → explain architecture for live data collection

## Limitations

- Prototype weights, not official MoSPI/DGCA weights
- Synthetic demo data for reliable demonstration
- 10 domestic routes only (no international)
- Live scraping not enabled (OTA bot protection)
- Simple linear regression forecasting
- SQLite (not production-grade for high volume)

## Moving to Production

1. **Official data partnerships** — DGCA/MoSPI API access
2. **Permitted scraping** — airline APIs, authorized OTA feeds
3. **Production database** — PostgreSQL/TimescaleDB
4. **Official route weights** — from MoSPI CPI basket
5. **Scheduler** — APScheduler/Celery for automated collection
6. **Monitoring** — data quality alerts, pipeline health
7. **Security** — authentication, audit logging
8. **Validation** — statistical review against official CPI methodology

## License

Prototype for hackathon demonstration purposes.
