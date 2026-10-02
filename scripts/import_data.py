"""Import reference CSV/Excel files into the database."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database.db import get_db, init_db


def import_reference_csv(filepath: str, source: str = "DGCA_IMPORT", data_type: str = "OFFICIAL_REFERENCE"):
    """
    Import a CSV with columns: route, month, passenger_traffic, average_fare

    Set data_type='OFFICIAL_REFERENCE' only for verified government data.
    """
    init_db()
    df = pd.read_csv(filepath)

    required = {"route", "month", "average_fare"}
    if not required.issubset(df.columns):
        raise ValueError(f"CSV must contain columns: {required}")

    with get_db() as conn:
        for _, row in df.iterrows():
            conn.execute(
                """INSERT INTO reference_data
                   (route, month, passenger_traffic, average_fare, source, data_type)
                   VALUES (?,?,?,?,?,?)""",
                (row["route"], row["month"],
                 row.get("passenger_traffic"), row["average_fare"],
                 source, data_type),
            )
    print(f"Imported {len(df)} reference records from {filepath}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/import_data.py <csv_file> [source] [data_type]")
        sys.exit(1)
    source = sys.argv[2] if len(sys.argv) > 2 else "DGCA_IMPORT"
    data_type = sys.argv[3] if len(sys.argv) > 3 else "OFFICIAL_REFERENCE"
    import_reference_csv(sys.argv[1], source, data_type)
