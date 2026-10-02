"""
India Airfare Price Index (APIx) — Streamlit Dashboard

Prototype / Experimental — NOT official MoSPI CPI
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from backend.config import (
    ADVANCE_WINDOWS,
    AIRPORT_NAMES,
    BASE_PERIOD_END,
    BASE_PERIOD_START,
    DATA_MODE,
    DEMO_AIRLINES,
    DEMO_ROUTES,
)
from backend.database.db import get_db
from backend.index.calculator import get_index_change
from backend.analytics.forecast import forecast_route
from backend.analytics.backtesting import run_backtest
from backend.services.cleaning import get_cleaning_stats

# ── Page config ──────────────────────────────────────────────
st.set_page_config(
    page_title="India Airfare Price Index",
    page_icon="🇮🇳",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ─────────────────────────────────────────────────
st.markdown("""
<style>
    .main-banner {
        background: linear-gradient(135deg, #1a237e 0%, #283593 50%, #1565c0 100%);
        color: white; padding: 1.2rem 2rem; border-radius: 8px;
        margin-bottom: 1rem; text-align: center;
    }
    .main-banner h1 { margin: 0; font-size: 1.8rem; }
    .main-banner p { margin: 0.3rem 0 0; opacity: 0.9; font-size: 0.95rem; }
    .demo-badge {
        background: #ff6f00; color: white; padding: 0.3rem 1rem;
        border-radius: 20px; font-weight: bold; font-size: 0.85rem;
        display: inline-block; margin-top: 0.5rem;
    }
    .kpi-card {
        background: white; border: 1px solid #e0e0e0; border-radius: 8px;
        padding: 1.2rem; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.06);
    }
    .kpi-value { font-size: 2rem; font-weight: 700; color: #1a237e; }
    .kpi-label { font-size: 0.85rem; color: #666; margin-top: 0.3rem; }
    .kpi-change-up { color: #d32f2f; font-weight: 600; }
    .kpi-change-down { color: #388e3c; font-weight: 600; }
    .anomaly-alert {
        background: #fff3e0; border-left: 4px solid #ff6f00;
        padding: 0.8rem 1rem; margin: 0.5rem 0; border-radius: 4px;
    }
    div[data-testid="stSidebar"] { background: #f5f5f5; }
</style>
""", unsafe_allow_html=True)


# ── Data helpers ───────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_observations(filters=None):
    query = "SELECT * FROM airfare_observations WHERE 1=1"
    params = []
    if filters:
        if filters.get("route"):
            query += " AND route = ?"; params.append(filters["route"])
        if filters.get("airline"):
            query += " AND airline = ?"; params.append(filters["airline"])
        if filters.get("advance_days"):
            query += " AND advance_purchase_days = ?"; params.append(filters["advance_days"])
        if filters.get("origin"):
            query += " AND origin = ?"; params.append(filters["origin"])
        if filters.get("destination"):
            query += " AND destination = ?"; params.append(filters["destination"])
    with get_db() as conn:
        return pd.read_sql(query, conn, params=params or None)


@st.cache_data(ttl=300)
def load_index(frequency="daily"):
    with get_db() as conn:
        return pd.read_sql(
            "SELECT * FROM index_values WHERE frequency=? AND data_mode=? ORDER BY index_date",
            conn, params=(frequency, DATA_MODE),
        )


@st.cache_data(ttl=300)
def load_anomalies():
    with get_db() as conn:
        return pd.read_sql(
            "SELECT * FROM anomalies WHERE data_mode=? ORDER BY change_pct DESC",
            conn, params=(DATA_MODE,),
        )


@st.cache_data(ttl=300)
def load_routes():
    with get_db() as conn:
        return pd.read_sql("SELECT * FROM routes", conn)


def format_metric_value(value) -> str:
    """Format a dashboard metric safely (int/float/str/bytes/numpy scalars)."""
    if value is None:
        return "—"
    if isinstance(value, bytes):
        value = int.from_bytes(value, byteorder="little", signed=False)
    elif hasattr(value, "item") and callable(value.item):
        try:
            value = value.item()
        except (ValueError, TypeError):
            pass
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        if isinstance(value, float) and value.is_integer():
            return f"{int(value):,}"
        if isinstance(value, int):
            return f"{value:,}"
        return f"{value:,.1f}"
    return str(value)


# ── Banner ─────────────────────────────────────────────────────
st.markdown("""
<div class="main-banner">
    <h1>🇮🇳 INDIA AIRFARE PRICE INDEX</h1>
    <p>Prototype Airfare Price Index (APIx) — Ministry of Statistics & Programme Implementation</p>
    <span class="demo-badge">⚠ Prototype / Experimental — NOT Official CPI &nbsp;|&nbsp; Data Mode: DEMO / SYNTHETIC</span>
</div>
""", unsafe_allow_html=True)

# ── Sidebar filters ────────────────────────────────────────────
st.sidebar.title("Filters")
page = st.sidebar.radio("Navigation", [
    "Dashboard", "Route Analysis", "Lead-Time Analysis",
    "Anomalies & Forecast", "Back-Testing", "Methodology", "Data Quality",
])

routes_list = [f"{r['origin']}-{r['destination']}" for r in DEMO_ROUTES]
selected_route = st.sidebar.selectbox("Route", ["All"] + routes_list)
selected_airline = st.sidebar.selectbox("Airline", ["All"] + DEMO_AIRLINES)
advance_options = ["All"] + [f"T+{d}" for d in ADVANCE_WINDOWS]
selected_advance = st.sidebar.selectbox("Advance Purchase", advance_options)

filters = {}
if selected_route != "All":
    filters["route"] = selected_route
if selected_airline != "All":
    filters["airline"] = selected_airline
if selected_advance != "All":
    filters["advance_days"] = int(selected_advance.replace("T+", ""))

# ── KPI Row ────────────────────────────────────────────────────
changes = get_index_change()
with get_db() as conn:
    obs_count = conn.execute("SELECT COUNT(*) FROM airfare_observations").fetchone()[0]
    route_count = conn.execute("SELECT COUNT(*) FROM routes").fetchone()[0]

kpi_cols = st.columns(6)
kpis = [
    ("Current APIx", f"{changes.get('current', '—')}", ""),
    ("Daily Change", f"{changes.get('daily_change', 0):+.1f}%", "up" if changes.get('daily_change', 0) > 0 else "down"),
    ("Weekly Change", f"{changes.get('weekly_change', 0):+.1f}%", "up" if changes.get('weekly_change', 0) > 0 else "down"),
    ("Monthly Change", f"{changes.get('monthly_change', 0):+.1f}%", "up" if changes.get('monthly_change', 0) > 0 else "down"),
    ("Routes Tracked", str(route_count), ""),
    ("Observations", f"{obs_count:,}", ""),
]
for col, (label, value, direction) in zip(kpi_cols, kpis):
    change_class = f"kpi-change-{direction}" if direction else ""
    col.markdown(f"""<div class="kpi-card">
        <div class="kpi-value {change_class}">{value}</div>
        <div class="kpi-label">{label}</div>
    </div>""", unsafe_allow_html=True)

st.markdown("---")

# ══════════════════════════════════════════════════════════════
# PAGE: DASHBOARD
# ══════════════════════════════════════════════════════════════
if page == "Dashboard":
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("Airfare Price Index (APIx) Over Time")
        freq = st.radio("Frequency", ["daily", "weekly", "monthly"], horizontal=True, key="idx_freq")
        idx_df = load_index(freq)
        if not idx_df.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=idx_df["index_date"], y=idx_df["index_value"],
                mode="lines+markers", name="APIx",
                line=dict(color="#1565c0", width=2),
                fill="tozeroy", fillcolor="rgba(21,101,192,0.08)",
            ))
            fig.add_hline(y=100, line_dash="dash", line_color="gray",
                          annotation_text="Base Period (100)")
            fig.update_layout(
                xaxis_title="Date", yaxis_title="Index Value",
                height=400, margin=dict(l=40, r=20, t=30, b=40),
                plot_bgcolor="white", paper_bgcolor="white",
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("No index data. Run `python scripts/generate_demo_data.py` first.")

    with col2:
        st.subheader("Index Summary")
        if not idx_df.empty:
            latest = idx_df.iloc[-1]
            st.metric("Latest APIx", f"{latest['index_value']:.1f}")
            st.metric("Base Period", f"{BASE_PERIOD_START} to {BASE_PERIOD_END}")
            st.metric("Methodology", "APIx v1 — Weighted Median")
            st.info("Base period index = 100. Values above 100 indicate fares above the base period average.")

    # Route-wise trends
    st.subheader("Route-wise Average Fare Trends")
    obs_df = load_observations(filters if filters else None)
    if not obs_df.empty:
        obs_df["collection_date"] = pd.to_datetime(obs_df["collection_timestamp"]).dt.date.astype(str)
        route_trend = obs_df.groupby(["collection_date", "route"])["total_fare"].median().reset_index()
        fig2 = px.line(
            route_trend, x="collection_date", y="total_fare", color="route",
            labels={"total_fare": "Median Fare (₹)", "collection_date": "Date"},
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        fig2.update_layout(height=380, plot_bgcolor="white", paper_bgcolor="white")
        st.plotly_chart(fig2, use_container_width=True)

    # Airline comparison + Heatmap
    col3, col4 = st.columns(2)
    with col3:
        st.subheader("Average Fare by Airline")
        if not obs_df.empty:
            airline_avg = obs_df.groupby("airline")["total_fare"].mean().reset_index().sort_values("total_fare")
            fig3 = px.bar(
                airline_avg, x="total_fare", y="airline", orientation="h",
                labels={"total_fare": "Avg Fare (₹)", "airline": "Airline"},
                color="total_fare", color_continuous_scale="Blues",
            )
            fig3.update_layout(height=320, showlegend=False, plot_bgcolor="white")
            st.plotly_chart(fig3, use_container_width=True)

    with col4:
        st.subheader("Route Heatmap — Fare Change %")
        if not obs_df.empty:
            route_stats = []
            for route in obs_df["route"].unique():
                rdf = obs_df[obs_df["route"] == route].sort_values("collection_timestamp")
                if len(rdf) < 2:
                    continue
                first_half = rdf.iloc[:len(rdf)//2]["total_fare"].mean()
                second_half = rdf.iloc[len(rdf)//2:]["total_fare"].mean()
                pct = ((second_half - first_half) / first_half * 100) if first_half else 0
                parts = route.split("-")
                route_stats.append({
                    "origin": parts[0], "destination": parts[1],
                    "avg_fare": rdf["total_fare"].mean(),
                    "pct_change": pct,
                })
            if route_stats:
                hm_df = pd.DataFrame(route_stats)
                origins = sorted(hm_df["origin"].unique())
                dests = sorted(hm_df["destination"].unique())
                matrix = pd.DataFrame(0.0, index=origins, columns=dests)
                for _, row in hm_df.iterrows():
                    matrix.loc[row["origin"], row["destination"]] = row["pct_change"]
                fig4 = px.imshow(
                    matrix, text_auto=".1f", aspect="auto",
                    color_continuous_scale="RdYlGn_r",
                    labels=dict(color="Change %"),
                    title="Fare Change % (recent vs earlier period)",
                )
                fig4.update_layout(height=320)
                st.plotly_chart(fig4, use_container_width=True)

# ══════════════════════════════════════════════════════════════
# PAGE: ROUTE ANALYSIS
# ══════════════════════════════════════════════════════════════
elif page == "Route Analysis":
    route = selected_route if selected_route != "All" else "DEL-BOM"
    st.subheader(f"Route Analysis: {route}")
    origin, dest = route.split("-")
    st.caption(f"{AIRPORT_NAMES.get(origin, origin)} → {AIRPORT_NAMES.get(dest, dest)}")

    obs_df = load_observations({"route": route})
    if obs_df.empty:
        st.warning("No data for this route.")
    else:
        obs_df["collection_date"] = pd.to_datetime(obs_df["collection_timestamp"]).dt.date.astype(str)

        col1, col2 = st.columns(2)
        with col1:
            daily = obs_df.groupby("collection_date")["total_fare"].agg(["mean", "min", "max"]).reset_index()
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=daily["collection_date"], y=daily["mean"],
                                     mode="lines+markers", name="Average", line=dict(color="#1565c0")))
            fig.add_trace(go.Scatter(x=daily["collection_date"], y=daily["max"],
                                     mode="lines", name="Max", line=dict(color="#ef5350", dash="dot")))
            fig.add_trace(go.Scatter(x=daily["collection_date"], y=daily["min"],
                                     mode="lines", name="Min", line=dict(color="#66bb6a", dash="dot")))
            fig.update_layout(title="30-Day Price Trend", yaxis_title="Fare (₹)", height=380,
                              plot_bgcolor="white")
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            airline_route = obs_df.groupby("airline")["total_fare"].mean().reset_index().sort_values("total_fare")
            fig2 = px.bar(airline_route, x="airline", y="total_fare",
                          title="Average Fare by Airline", color="total_fare",
                          color_continuous_scale="Viridis")
            fig2.update_layout(height=380, showlegend=False, plot_bgcolor="white")
            st.plotly_chart(fig2, use_container_width=True)

        st.subheader("Recent Observations")
        display_cols = ["collection_timestamp", "airline", "travel_date",
                        "advance_purchase_days", "base_fare", "taxes", "fees",
                        "total_fare", "availability_status"]
        st.dataframe(obs_df[display_cols].tail(20), use_container_width=True)

# ══════════════════════════════════════════════════════════════
# PAGE: LEAD-TIME ANALYSIS
# ══════════════════════════════════════════════════════════════
elif page == "Lead-Time Analysis":
    st.subheader("Lead-Time / Advance-Purchase Analysis")
    st.caption("How airfare changes depending on booking window — key for dynamic pricing analysis")

    route = selected_route if selected_route != "All" else "DEL-BOM"
    obs_df = load_observations({"route": route})

    if obs_df.empty:
        st.warning("No data available.")
    else:
        leadtime = (
            obs_df.groupby("advance_purchase_days")["total_fare"]
            .agg(["mean", "std", "count"])
            .reset_index()
            .sort_values("advance_purchase_days", ascending=False)
        )
        leadtime.columns = ["advance_days", "avg_fare", "std_fare", "count"]

        col1, col2 = st.columns([2, 1])
        with col1:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=[f"T+{d}" for d in leadtime["advance_days"]],
                y=leadtime["avg_fare"],
                mode="lines+markers+text",
                text=[f"₹{v:,.0f}" for v in leadtime["avg_fare"]],
                textposition="top center",
                line=dict(color="#1565c0", width=3),
                marker=dict(size=10),
                error_y=dict(type="data", array=leadtime["std_fare"], visible=True),
            ))
            fig.update_layout(
                title=f"Lead-Time Elasticity — {route}",
                xaxis_title="Advance Purchase Window",
                yaxis_title="Average Fare (₹)",
                height=420, plot_bgcolor="white",
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown("**Fare by Booking Window**")
            for _, row in leadtime.iterrows():
                st.markdown(f"**T+{int(row['advance_days'])}** → ₹{row['avg_fare']:,.0f}")
            st.info("Prices typically increase as departure date approaches, reflecting airline revenue management strategies.")

        # Multi-route comparison
        st.subheader("Lead-Time Comparison Across Routes")
        all_obs = load_observations()
        if not all_obs.empty:
            multi = (
                all_obs.groupby(["route", "advance_purchase_days"])["total_fare"]
                .mean().reset_index()
            )
            multi["window"] = multi["advance_purchase_days"].apply(lambda d: f"T+{d}")
            fig2 = px.line(
                multi, x="window", y="total_fare", color="route",
                markers=True, labels={"total_fare": "Avg Fare (₹)"},
            )
            fig2.update_layout(height=400, plot_bgcolor="white")
            st.plotly_chart(fig2, use_container_width=True)

# ══════════════════════════════════════════════════════════════
# PAGE: ANOMALIES & FORECAST
# ══════════════════════════════════════════════════════════════
elif page == "Anomalies & Forecast":
    st.subheader("Anomaly Detection & Forecasting")

    anomalies_df = load_anomalies()
    if not anomalies_df.empty:
        st.markdown("#### ⚠ Anomaly Alerts")
        for _, a in anomalies_df.head(10).iterrows():
            sev_color = {"high": "🔴", "medium": "🟠", "low": "🟡"}.get(a["severity"], "⚪")
            st.markdown(f"""<div class="anomaly-alert">
                {sev_color} <strong>Unusual fare increase</strong> — Route: <strong>{a['route']}</strong><br>
                Normal average: ₹{a['normal_average']:,.0f} → Current: ₹{a['current_average']:,.0f}
                (<strong>+{a['change_pct']:.1f}%</strong>) on {a['detection_date']}
                <br><small>Method: {a['method']}</small>
            </div>""", unsafe_allow_html=True)
    else:
        st.info("No anomalies detected in current data.")

    st.markdown("---")
    st.subheader("Experimental Forecast")
    st.caption("⚠ Forecasts are experimental and NOT official predictions")

    fc_route = selected_route if selected_route != "All" else "DEL-BOM"
    fc = forecast_route(fc_route, forecast_days=7)

    if fc.get("historical_dates"):
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=fc["historical_dates"], y=fc["historical_values"],
            mode="lines+markers", name="Historical", line=dict(color="#1565c0"),
        ))
        fig.add_trace(go.Scatter(
            x=fc["forecast_dates"], y=fc["forecast_values"],
            mode="lines+markers", name="Forecast",
            line=dict(color="#ef5350", dash="dash"),
        ))
        fig.update_layout(
            title=f"Fare Forecast — {fc_route} (Linear Regression)",
            yaxis_title="Median Fare (₹)", height=400, plot_bgcolor="white",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning(fc.get("error", "Insufficient data for forecast."))

# ══════════════════════════════════════════════════════════════
# PAGE: BACK-TESTING
# ══════════════════════════════════════════════════════════════
elif page == "Back-Testing":
    st.subheader("Back-Testing: APIx vs Reference Data")
    st.caption("Prototype validation — NOT official MoSPI/DGCA comparison")

    bt = run_backtest()
    if bt["dates"]:
        col1, col2, col3 = st.columns(3)
        col1.metric("Correlation", bt.get("correlation", "N/A"))
        col2.metric("MAE", bt.get("mae", "N/A"))
        col3.metric("RMSE", bt.get("rmse", "N/A"))

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=bt["dates"], y=bt["apix_values"],
            mode="lines+markers", name="Prototype APIx",
            line=dict(color="#1565c0", width=2),
        ))
        fig.add_trace(go.Scatter(
            x=bt["dates"], y=bt["reference_values"],
            mode="lines+markers", name="Reference (DGCA Sample)",
            line=dict(color="#ff6f00", width=2, dash="dot"),
        ))
        fig.update_layout(
            title="APIx vs Reference Average Fare Index",
            xaxis_title="Month", yaxis_title="Index (Base = 100)",
            height=420, plot_bgcolor="white",
        )
        st.plotly_chart(fig, use_container_width=True)

        if bt.get("reference_type") == "DEMO_REFERENCE":
            st.warning("Reference data is DEMO/SYNTHETIC sample data — not official DGCA statistics.")
    else:
        st.info("Insufficient data for back-testing. Run the data pipeline first.")

# ══════════════════════════════════════════════════════════════
# PAGE: METHODOLOGY
# ══════════════════════════════════════════════════════════════
elif page == "Methodology":
    st.subheader("Methodology & Documentation")

    st.markdown("""
    ### 1. What This Project Does
    This prototype demonstrates how airfare prices can be automatically collected,
    cleaned, normalized, and converted into a **Real-time Airfare Price Index (APIx)**
    for India — designed as a potential augmentation to the Consumer Price Index (CPI).

    ### 2. Why High-Frequency Airfare Collection
    Airfares are highly dynamic, changing multiple times daily based on demand,
    competition, and revenue management algorithms. Traditional monthly CPI surveys
    cannot capture this volatility. Automated collection enables daily/weekly index
    computation reflecting real market conditions.

    ### 3. Data Sources
    | Source | Type | Status |
    |--------|------|--------|
    | Demo/Synthetic Generator | DEMO | Active (default) |
    | MakeMyTrip Scraper | LIVE | Architecture only |
    | DGCA Reference CSV | DEMO REFERENCE | Sample data |
    | MoSPI eSankhyiki | OFFICIAL | Reference portal |

    Official portal: [eSankhyiki — MoSPI](https://esankhyiki.mospi.gov.in/)

    ### 4. Data Pipeline
    ```
    Sources → Collection → Raw DB → Cleaning → Clean DB → Index Calculation → Dashboard
    ```

    ### 5. Cleaning Methodology
    - Duplicate removal (same route/airline/date/window)
    - Invalid fare filtering (< ₹500 or > ₹1,00,000)
    - Sold-out/cancelled flight removal
    - Airline name normalization (aliases → canonical)
    - Airport code standardization (IATA 3-letter)
    - Outlier capping (IQR method, 1.5× threshold)
    - Base fare / taxes / fees validation

    ### 6. Index Methodology (APIx v1)
    **Formula:**
    ```
    APIx(t) = 100 × Σ(w_r × P_r(t) / P_r(base)) / Σ(w_r)
    ```
    - `w_r` = prototype route weight (configurable, NOT official MoSPI weights)
    - `P_r(t)` = median total fare for route r on date t
    - `P_r(base)` = median fare during base period ({base_start} to {base_end})
    - Base period index = **100**

    **Frequencies:** Daily, Weekly (7-day rolling), Monthly

    ### 7. Route Selection
    10 representative domestic routes covering major metro corridors:
    DEL-BOM, DEL-BLR, BOM-BLR, DEL-CCU, BLR-HYD, MAA-DEL, HYD-DEL, BOM-HYD, DEL-HYD, BLR-MAA

    ### 8. Advance-Purchase Windows
    T+1, T+7, T+15, T+30, T+45 days — capturing dynamic pricing across booking horizons.

    ### 9. Limitations
    - Prototype weights, not official MoSPI/DGCA weights
    - Synthetic demo data for demonstration
    - Limited route coverage (10 domestic routes)
    - No international routes
    - Simple forecasting (linear regression)
    - Live scraping not enabled (bot protection on OTAs)

    ### 10. Difference from Official CPI
    This **Prototype Airfare Price Index (APIx)** is an experimental demonstration.
    It is **NOT** the official Consumer Price Index published by MoSPI.
    Official CPI uses established survey methodology, representative baskets,
    and verified weights approved by the Government of India.
    """.format(base_start=BASE_PERIOD_START, base_end=BASE_PERIOD_END))

# ══════════════════════════════════════════════════════════════
# PAGE: DATA QUALITY
# ══════════════════════════════════════════════════════════════
elif page == "Data Quality":
    st.subheader("Data Quality Report")

    stats = get_cleaning_stats()
    if stats:
        cols = st.columns(3)
        metrics = [
            ("Raw Records", stats["raw_records"]),
            ("Duplicates Removed", stats["duplicates_removed"]),
            ("Invalid Records", stats["invalid_records"]),
            ("Outliers Handled", stats["outliers_handled"]),
            ("Sold-Out Removed", stats["sold_out_removed"]),
            ("Final Observations", stats["final_observations"]),
        ]
        for i, (label, val) in enumerate(metrics):
            cols[i % 3].metric(label, format_metric_value(val))

        retention = (
            stats["final_observations"] / stats["raw_records"] * 100
        ) if stats["raw_records"] else 0
        st.progress(retention / 100, text=f"Data Retention Rate: {retention:.1f}%")
    else:
        st.info("No cleaning stats available. Run the data pipeline.")

    st.subheader("Data Source Indicator")
    st.markdown(f"""
    | Property | Value |
    |----------|-------|
    | Data Mode | **{DATA_MODE.upper()}** |
    | Data Label | DEMO / SYNTHETIC DATA |
    | Official Reference | [eSankhyiki MoSPI Portal](https://esankhyiki.mospi.gov.in/) |
    | Index Label | Prototype APIx — NOT official CPI |
    """)

    with get_db() as conn:
        runs = pd.read_sql("SELECT * FROM scraping_runs ORDER BY id DESC LIMIT 5", conn)
    if not runs.empty:
        st.subheader("Recent Collection Runs")
        st.dataframe(runs, use_container_width=True)

# ── Footer ─────────────────────────────────────────────────────
st.markdown("---")
st.caption(
    "Prototype Airfare Price Index (APIx) · MoSPI Hackathon Demo · "
    "Data: DEMO/SYNTHETIC · NOT Official CPI · "
    "[eSankhyiki Portal](https://esankhyiki.mospi.gov.in/)"
)
