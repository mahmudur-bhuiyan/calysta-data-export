"""Add patient_id as the first column in existing per-patient appointment CSVs."""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys

from appointment_selectors import APPOINTMENT_CSV_COLUMNS, APPOINTMENT_PORTAL_HEADERS
from facility_paths import resolve_patients_base
from main import CONFIG_PATH, load_yaml, sanitize_facility_folder_name


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
        appt_dir = os.path.join(records_dir, name, "03_Appointment_History")
        if not os.path.isdir(appt_dir):
            skipped += 1
            continue

        csv_files = [
            f for f in os.listdir(appt_dir)
            if f.endswith(".csv") and f.startswith("Appointment_History_")
        ]
        if not csv_files:
            skipped += 1
            continue

        path = os.path.join(appt_dir, csv_files[0])
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            old_fields = reader.fieldnames or []

        if not rows:
            skipped += 1
            continue

        if old_fields and old_fields[0] == "patient_id":
            if all((r.get("patient_id") or "").strip() == patient_id for r in rows):
                skipped += 1
                continue

        out_rows = []
        for row in rows:
            out = {col: row.get(col, "") for col in APPOINTMENT_PORTAL_HEADERS}
            # Map legacy columns if header names shifted
            for key, value in row.items():
                if key and key != "patient_id" and key in APPOINTMENT_PORTAL_HEADERS:
                    out[key] = value
            out["patient_id"] = patient_id
            out_rows.append({col: out.get(col, "") for col in APPOINTMENT_CSV_COLUMNS})

        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=APPOINTMENT_CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(out_rows)

        updated += 1

    print(f"Updated {updated} appointment file(s); skipped {skipped}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Add patient_id column to existing appointment history CSVs."
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
