"""Remove legacy 'no data found for this patient' service history CSVs."""

from __future__ import annotations

import argparse
import os
import sys

from export_index import write_export_index
from export_status import remove_empty_category_folders
from facility_paths import resolve_export_index_path, resolve_patients_base
from main import (
    CONFIG_PATH,
    load_patient_data,
    load_yaml,
    sanitize_facility_folder_name,
    select_patient_csv,
    to_pascalcase,
)
from service_history_downloader import is_placeholder_service_csv


def cleanup(base_downloads_path: str) -> tuple[int, list[str]]:
    removed = 0
    patient_ids: list[str] = []
    if not os.path.isdir(base_downloads_path):
        return removed, patient_ids

    for name in os.listdir(base_downloads_path):
        if not name.split("_", 1)[0].isdigit():
            continue
        folder = os.path.join(base_downloads_path, name)
        if not os.path.isdir(folder):
            continue
        sub = os.path.join(folder, "04_Service_History")
        if not os.path.isdir(sub):
            continue
        had_placeholder = False
        for fn in os.listdir(sub):
            path = os.path.join(sub, fn)
            if not fn.endswith(".csv") or not os.path.isfile(path):
                continue
            if is_placeholder_service_csv(path):
                os.remove(path)
                removed += 1
                had_placeholder = True
        if had_placeholder:
            patient_ids.append(name.split("_", 1)[0])
            remove_empty_category_folders(folder)
    return removed, patient_ids


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Remove placeholder service history CSVs and refresh export_index.csv"
    )
    parser.add_argument(
        "--facility",
        help="Facility folder name under downloads/ (default: credentials.yaml)",
    )
    parser.add_argument(
        "--list-ids",
        action="store_true",
        help="Print affected patient IDs (for reexport_service_history.py)",
    )
    args = parser.parse_args()

    if args.facility:
        facility_folder = args.facility
    else:
        credentials = load_yaml(os.path.join(CONFIG_PATH, "credentials.yaml"))
        facility_folder = sanitize_facility_folder_name(
            credentials.get("facility", "Facility")
        )

    csv_path, _ = select_patient_csv(
        load_yaml(os.path.join(CONFIG_PATH, "credentials.yaml")).get("facility", "Facility")
    )
    if not csv_path:
        print("No patient CSV found.", file=sys.stderr)
        return 1

    patient_data = load_patient_data(csv_path)
    base = resolve_patients_base(facility_folder)
    removed, patient_ids = cleanup(base)

    index_path = write_export_index(
        patient_data,
        base,
        to_pascalcase,
        path=resolve_export_index_path(facility_folder),
    )

    if args.list_ids:
        for pid in patient_ids:
            print(pid)
    else:
        print(f"Removed {removed} placeholder service history file(s)")
        print(f"Patients affected: {len(patient_ids)}")
        print(f"Export index refreshed: {index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
