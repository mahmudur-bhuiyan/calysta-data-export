"""Backfill per-patient SMS/email log CSVs from facility Master Data."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

from export_status import CATEGORY_SMS, mark_category
from facility_paths import delivery_report_dir, master_data_dir, resolve_patients_base
from main import (
    CONFIG_PATH,
    FOLDER_SMS,
    index_patient_folders_by_id,
    load_patient_data,
    load_yaml,
    sanitize_facility_folder_name,
    select_patient_csv,
    to_pascalcase,
)
from progress_report import generate_progress_report
from sms_log_master import find_master_sms_csv, load_sms_logs_by_patient, write_patient_sms_log


def _patient_name(patient: dict) -> str:
    return f"{to_pascalcase(patient['first_name'])} {to_pascalcase(patient['last_name'])}"


def backfill(facility_folder: str, patient_ids: list[str] | None = None) -> int:
    master_dir = master_data_dir(facility_folder)
    records_dir = resolve_patients_base(facility_folder)
    master_sms_path = find_master_sms_csv(master_dir)
    if not master_sms_path:
        print(f"Error: no SMS/email logs CSV in {master_dir}", file=sys.stderr)
        return 1

    sms_by_patient = load_sms_logs_by_patient(master_sms_path)
    folders = index_patient_folders_by_id(records_dir)

    csv_path, _ = select_patient_csv(
        load_yaml(os.path.join(CONFIG_PATH, "credentials.yaml")).get("facility", "Facility")
    )
    patient_data = {p["id"]: p for p in load_patient_data(csv_path)} if csv_path else {}

    targets = patient_ids or sorted(folders.keys(), key=int)
    updated = 0

    for pid in targets:
        folder = folders.get(pid)
        patient = patient_data.get(pid)
        if not folder or not patient:
            continue

        full_name = _patient_name(patient)
        rows = sms_by_patient.get(pid, [])
        sms_dir = os.path.join(folder, FOLDER_SMS)
        os.makedirs(sms_dir, exist_ok=True)
        write_patient_sms_log(sms_dir, full_name, rows)
        mark_category(
            folder,
            CATEGORY_SMS,
            file_count=1,
            empty_ok=(len(rows) == 0),
        )
        updated += 1
        if rows:
            print(f"Updated {pid} ({full_name}): {len(rows)} row(s)")
        else:
            print(f"Updated {pid} ({full_name}): header only (no master rows)")

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

    print(f"Backfilled SMS logs for {updated}/{len(targets)} patient(s)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill per-patient SMS/email logs from Master Data."
    )
    parser.add_argument(
        "patient_ids",
        nargs="*",
        help="Patient IDs to backfill (default: all exported patients)",
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
