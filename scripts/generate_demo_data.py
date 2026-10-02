"""Initialize and populate the prototype database."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database.db import init_db
from backend.services.demo_generator import generate_demo_data, generate_reference_data
from backend.services.cleaning import run_cleaning_pipeline
from backend.index.calculator import compute_and_store_index
from backend.analytics.anomaly import run_anomaly_detection


def main():
    print("=" * 60)
    print("  India Airfare Price Index — Demo Data Pipeline")
    print("  DATA MODE: DEMO / SYNTHETIC")
    print("=" * 60)

    print("\n[1/5] Initializing database...")
    init_db()

    print("[2/5] Generating 35-day synthetic airfare data...")
    gen_result = generate_demo_data(days=35)
    print(f"       Raw records generated: {gen_result['raw_records']}")
    print(f"       Duplicates injected: {gen_result['duplicates_injected']}")

    print("[3/5] Generating reference data (DEMO)...")
    generate_reference_data()

    print("[4/5] Running cleaning pipeline...")
    stats = run_cleaning_pipeline()
    print(f"       Raw records:      {stats.raw_records:,}")
    print(f"       Duplicates removed: {stats.duplicates_removed:,}")
    print(f"       Invalid records:  {stats.invalid_records:,}")
    print(f"       Outliers handled: {stats.outliers_handled:,}")
    print(f"       Sold-out removed: {stats.sold_out_removed:,}")
    print(f"       Final observations: {stats.final_observations:,}")

    print("[5/5] Computing Airfare Price Index (APIx)...")
    idx_result = compute_and_store_index()
    print(f"       Daily index values: {idx_result['daily_count']}")
    print(f"       Latest APIx: {idx_result['latest_index']}")

    print("\n[+] Running anomaly detection...")
    anomalies = run_anomaly_detection()
    print(f"       Anomalies detected: {len(anomalies)}")

    print("\n" + "=" * 60)
    print("  Pipeline complete! Start the dashboard with:")
    print("  streamlit run frontend/app.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
