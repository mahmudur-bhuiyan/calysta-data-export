"""Add patient_id as the first column in existing per-patient details CSVs."""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys

from facility_paths import resolve_patients_base
from main import CONFIG_PATH, load_yaml, sanitize_facility_folder_name
from patient_details_selectors import PATIENT_DETAIL_CSV_COLUMNS, PATIENT_DETAIL_FIELDS


def backfill(facility_folder: str) -> int:
    records_dir = resolve_patients_base(facility_folder)
    if not os.path.isdir(records_dir):
        print(f"Error: patients records folder not found: {records_dir}", file=sys.stderr)
        return 1

    updated = 0
    skipped = 0

    for name in sorted(os.listdir(records_dir)):
        if not re.match(r"^(\d+)_", name):
            continue
        patient_id = name.split("_", 1)[0]
        details_dir = os.path.join(records_dir, name, "01_Patient_Details")
        if not os.path.isdir(details_dir):
            skipped += 1
            continue

        csv_files = [f for f in os.listdir(details_dir) if f.endswith("_details.csv")]
        if not csv_files:
            skipped += 1
            continue

        path = os.path.join(details_dir, csv_files[0])
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            old_fields = reader.fieldnames or []

        if not rows:
            skipped += 1
            continue

        row = rows[0]
        if "patient_id" in old_fields and row.get("patient_id", "").strip() == patient_id:
            skipped += 1
            continue

        row["patient_id"] = patient_id
        out_row = {col: row.get(col, "N/A") for col in PATIENT_DETAIL_CSV_COLUMNS}

        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=PATIENT_DETAIL_CSV_COLUMNS)
            writer.writeheader()
            writer.writerow(out_row)

        updated += 1

    print(f"Updated {updated} patient details file(s); skipped {skipped}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Add patient_id column to existing patient details CSVs."
    )
    parser.add_argument(
        "--facility",
        help="Facility folder name under downloads/ (default: from credentials.yaml)",
    )
    args = parser.parse_args()

    if args.facility:
        facility_folder = args.facility
    else:
        credentials = load_yaml(os.path.join(CONFIG_PATH, "credentials.yaml"))
        facility_folder = sanitize_facility_folder_name(
            credentials.get("facility", "Facility")
        )

    return backfill(facility_folder)


if __name__ == "__main__":
    raise SystemExit(main())
