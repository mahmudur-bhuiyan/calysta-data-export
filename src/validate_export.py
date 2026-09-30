"""Validate per-patient exports against the patient list and on-disk folders."""

from __future__ import annotations

import argparse
import os
import re
import sys

from export_index import write_export_index
from facility_paths import resolve_export_index_path, resolve_patients_base
from main import (
    CONFIG_PATH,
    FOLDER_APPOINTMENTS,
    FOLDER_DETAILS,
    load_patient_data,
    load_yaml,
    sanitize_facility_folder_name,
    select_patient_csv,
    to_pascalcase,
)


def _load_patients_from_list(facility_name: str) -> dict[str, dict]:
    csv_path, _ = select_patient_csv(facility_name)
    if not csv_path:
        return {}
    patients: dict[str, dict] = {}
    for row in load_patient_data(csv_path):
        patients[row["id"]] = row
    return patients


def _index_export_folders(records_dir: str) -> dict[str, str]:
    index: dict[str, str] = {}
    if not os.path.isdir(records_dir):
        return index
    for name in os.listdir(records_dir):
        path = os.path.join(records_dir, name)
        if not os.path.isdir(path):
            continue
        m = re.match(r"^(\d+)_", name)
        if m:
            index[m.group(1)] = path
    return index


def _has_details_csv(folder: str) -> bool:
    sub = os.path.join(folder, FOLDER_DETAILS)
    if not os.path.isdir(sub):
        return False
    return any(name.lower().endswith("_details.csv") for name in os.listdir(sub))


def _has_appointment_csv(folder: str) -> bool:
    sub = os.path.join(folder, FOLDER_APPOINTMENTS)
    if not os.path.isdir(sub):
        return False
    return any(name.lower().endswith(".csv") for name in os.listdir(sub))


def find_gaps(facility_folder: str, facility_name: str) -> dict[str, list[tuple]]:
    """Return gap lists keyed by category for patients in patient_lists/."""
    records_dir = resolve_patients_base(facility_folder)
    patients = _load_patients_from_list(facility_name)
    exports = _index_export_folders(records_dir)

    missing_folders = []
    details_gaps = []
    appointment_gaps = []

    for pid in sorted(patients.keys(), key=int):
        patient = patients[pid]
        folder = exports.get(pid)
        if not folder:
            missing_folders.append(
                (pid, patient.get("first_name", ""), patient.get("last_name", ""))
            )
            continue

        if not _has_details_csv(folder):
            details_gaps.append(
                (pid, patient.get("first_name", ""), patient.get("last_name", ""))
            )

        if not _has_appointment_csv(folder):
            appointment_gaps.append(
                (pid, patient.get("first_name", ""), patient.get("last_name", ""))
            )

    return {
        "missing_folders": missing_folders,
        "details_missing": details_gaps,
        "appointment_missing": appointment_gaps,
        "list_patients": len(patients),
        "export_folders": len(exports),
    }


def validate(facility_folder: str, facility_name: str) -> dict[str, list[tuple]]:
    records_dir = resolve_patients_base(facility_folder)
    if not os.path.isdir(records_dir):
        print(f"Error: patients records folder not found: {records_dir}", file=sys.stderr)
        raise SystemExit(1)

    gaps = find_gaps(facility_folder, facility_name)

    print(f"Facility: {facility_folder}")
    print(f"Patients in list: {gaps['list_patients']}")
    print(f"Exported folders: {gaps['export_folders']}")
    print(f"Missing export folders: {len(gaps['missing_folders'])}")
    for row in gaps["missing_folders"][:20]:
        print(f"  {row[0]}: {row[1]} {row[2]}")

    print(f"\nPatient details CSV missing: {len(gaps['details_missing'])}")
    for row in gaps["details_missing"][:20]:
        print(f"  {row[0]}: {row[1]} {row[2]}")

    print(f"\nAppointment CSV missing: {len(gaps['appointment_missing'])}")
    for row in gaps["appointment_missing"][:20]:
        print(f"  {row[0]}: {row[1]} {row[2]}")

    print(
        "\nNote: All export categories are scraped from the Calysta portal. "
        "Master Data is manual-only — the exporter does not read from or write to it."
    )

    return gaps


def fix_gaps(facility_folder: str, gaps: dict[str, list[tuple]]) -> int:
    """Re-scrape appointment CSVs from the portal for patients missing them."""
    import asyncio

    from reexport_appointments import reexport_appointments

    appt_ids = [row[0] for row in gaps["appointment_missing"]]
    appt_ids = sorted(set(appt_ids), key=int)

    if not appt_ids:
        print("\nNo appointment gaps to re-export from portal.")
        return 0

    print(f"\nRe-exporting appointments from portal for {len(appt_ids)} patient(s)...")
    return asyncio.run(reexport_appointments(appt_ids))


def update_export_index(facility_folder: str) -> str:
    credentials = load_yaml(os.path.join(CONFIG_PATH, "credentials.yaml"))
    facility_name = credentials.get("facility", facility_folder)
    csv_path, _ = select_patient_csv(facility_name)
    if not csv_path:
        raise SystemExit("No patient list CSV found.")
    base = resolve_patients_base(facility_folder)
    return write_export_index(
        load_patient_data(csv_path),
        base,
        to_pascalcase,
        path=resolve_export_index_path(facility_folder),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate per-patient exports against patient_lists/ and on-disk folders."
    )
    parser.add_argument(
        "--facility",
        help="Facility folder name under downloads/ (default: from credentials.yaml)",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Re-export missing appointment CSVs from the portal",
    )
    parser.add_argument(
        "--update-index",
        action="store_true",
        help="Regenerate export_index.csv after validation/fix",
    )
    args = parser.parse_args()

    credentials = load_yaml(os.path.join(CONFIG_PATH, "credentials.yaml"))
    if args.facility:
        facility_folder = args.facility
        facility_name = credentials.get("facility", facility_folder)
    else:
        facility_name = credentials.get("facility", "Facility")
        facility_folder = sanitize_facility_folder_name(facility_name)

    gaps = validate(facility_folder, facility_name)

    has_gaps = any(
        gaps[key]
        for key in (
            "missing_folders",
            "details_missing",
            "appointment_missing",
        )
    )

    exit_code = 2 if has_gaps else 0

    if args.fix and gaps["appointment_missing"]:
        fix_code = fix_gaps(facility_folder, gaps)
        exit_code = max(exit_code, fix_code)
        print("\nRe-validating after fix...")
        gaps = validate(facility_folder, facility_name)
        has_gaps = any(
            gaps[key]
            for key in (
                "missing_folders",
                "details_missing",
                "appointment_missing",
            )
        )
        exit_code = 2 if has_gaps else 0

    if args.update_index or args.fix:
        index_path = update_export_index(facility_folder)
        print(f"\nExport index: {index_path}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
