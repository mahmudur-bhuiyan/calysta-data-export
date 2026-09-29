"""Backfill per-patient appointment CSVs from facility Master Data when portal export is empty."""

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import defaultdict
from datetime import datetime, date, time

from appointment_downloader import write_appointment_csv
from export_status import CATEGORY_APPOINTMENTS, mark_category
from facility_paths import delivery_report_dir, master_data_dir, resolve_patients_base
from main import (
    CONFIG_PATH,
    FOLDER_APPOINTMENTS,
    index_patient_folders_by_id,
    load_patient_data,
    load_yaml,
    sanitize_facility_folder_name,
    select_patient_csv,
    to_pascalcase,
)
from progress_report import generate_progress_report
from validate_export import _count_by_patient, _csv_rows, _find_master_csv, _load_patients


PORTAL_HEADERS = [
    "Patient",
    "Patient Email Address",
    "Provider",
    "Resource",
    "Booked By",
    "Services",
    "Appointment note",
    "Appointment date",
    "Appointment time",
    "Booking Date",
    "Booking Time",
    "Appointment status",
]


def _format_date(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").strftime("%m/%d/%Y")
    except ValueError:
        return value


def _format_time(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    for fmt in ("%H:%M:%S", "%H:%M", "%I:%M %p", "%I:%M:%S %p"):
        try:
            return datetime.strptime(value, fmt).strftime("%I:%M %p").lstrip("0")
        except ValueError:
            continue
    return value


def _clean(value: str) -> str:
    value = (value or "").strip()
    return "" if value.upper() == "NULL" else value


def _master_rows_for_patient(master_dir: str, patient_id: str) -> list[dict]:
    path = _find_master_csv(master_dir, "appointments_list")
    if not path:
        return []
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if (row.get("patient_id") or "").strip() == patient_id:
                rows.append(row)
    return rows


def _to_portal_rows(master_rows: list[dict], email: str) -> list[list[str]]:
    portal_rows = []
    for row in master_rows:
        full_name = f"{row.get('first_name', '').strip()} {row.get('last_name', '').strip()}".strip()
        portal_rows.append([
            full_name,
            email,
            _clean(row.get("provider_name", "")),
            _clean(row.get("resource_name", "")),
            _clean(row.get("booked_by_name", "")),
            "",
            _clean(row.get("appointment_notes", "")),
            _format_date(row.get("appointment_date", "")),
            _format_time(row.get("start_time", "")),
            "",
            "",
            _clean(row.get("status", "")),
        ])
    return portal_rows


def _patient_name(patient: dict) -> str:
    return f"{to_pascalcase(patient['first_name'])} {to_pascalcase(patient['last_name'])}"


def find_gap_patient_ids(facility_folder: str) -> list[str]:
    master_dir = master_data_dir(facility_folder)
    records_dir = resolve_patients_base(facility_folder)
    patients = _load_patients(master_dir)
    master_appts = _count_by_patient(master_dir, "appointments_list")
    exports = index_patient_folders_by_id(records_dir)

    gaps = []
    for pid, count in master_appts.items():
        if count <= 0:
            continue
        folder = exports.get(pid)
        if not folder:
            continue
        if _csv_rows(folder, FOLDER_APPOINTMENTS) == 0:
            gaps.append(pid)
    return sorted(gaps, key=int)


def backfill(facility_folder: str, patient_ids: list[str] | None = None) -> int:
    master_dir = master_data_dir(facility_folder)
    records_dir = resolve_patients_base(facility_folder)
    patients = _load_patients(master_dir)
    folders = index_patient_folders_by_id(records_dir)

    csv_path, _ = select_patient_csv(
        load_yaml(os.path.join(CONFIG_PATH, "credentials.yaml")).get("facility", "Facility")
    )
    patient_data = {p["id"]: p for p in load_patient_data(csv_path)} if csv_path else {}

    targets = patient_ids or find_gap_patient_ids(facility_folder)
    if not targets:
        print("No appointment gaps to backfill.")
        return 0

    filled = 0
    for pid in targets:
        folder = folders.get(pid)
        patient = patient_data.get(pid) or {
            "id": pid,
            "first_name": patients.get(pid, {}).get("first_name", ""),
            "last_name": patients.get(pid, {}).get("last_name", ""),
        }
        if not folder:
            print(f"Skipping {pid}: no export folder")
            continue

        master_rows = _master_rows_for_patient(master_dir, pid)
        if not master_rows:
            print(f"Skipping {pid}: no master appointments")
            continue

        full_name = _patient_name(patient)
        email = (patients.get(pid, {}).get("email") or "").strip()
        appt_dir = os.path.join(folder, FOLDER_APPOINTMENTS)
        os.makedirs(appt_dir, exist_ok=True)
        save_path = os.path.join(appt_dir, f"Appointment_History_{full_name}.csv")
        portal_rows = _to_portal_rows(master_rows, email)
        write_appointment_csv(save_path, PORTAL_HEADERS, portal_rows)
        mark_category(folder, CATEGORY_APPOINTMENTS, file_count=1)
        filled += 1
        print(f"Backfilled {pid} ({full_name}): {len(portal_rows)} appointment row(s)")

    if csv_path:
        output_dir = delivery_report_dir(facility_folder)
        os.makedirs(output_dir, exist_ok=True)
        safe = facility_folder.replace(" ", "_").replace("(", "").replace(")", "")
        report_path = generate_progress_report(
            facility_name=load_yaml(os.path.join(CONFIG_PATH, "credentials.yaml")).get(
                "facility", facility_folder
            ),
            patient_data=load_patient_data(csv_path),
            base_downloads_path=records_dir,
            output_dir=output_dir,
            to_pascalcase=to_pascalcase,
            custom_filename=f"{safe}_Export_Progress_{datetime.now().strftime('%m-%d-%Y')}.html",
        )
        print(f"Updated progress report: {report_path}")

    print(f"Backfilled {filled}/{len(targets)} patient(s)")
    return 0 if filled == len(targets) else 2


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill appointment CSVs from Master Data for patients with portal gaps."
    )
    parser.add_argument(
        "patient_ids",
        nargs="*",
        help="Patient IDs to backfill (default: auto-detect gaps)",
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

    patient_ids = args.patient_ids or None
    return backfill(facility_folder, patient_ids)


if __name__ == "__main__":
    raise SystemExit(main())
