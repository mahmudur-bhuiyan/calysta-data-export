"""Re-scrape per-patient SMS logs from the Calysta portal."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime

from auth import authenticate_and_select_facility
from export_status import CATEGORY_SMS, mark_category, remove_empty_category_folders, reset_category
from facility_paths import delivery_report_dir, resolve_patients_base
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
from patient_naming import patient_display_name, patient_file_slug
from progress_report import generate_progress_report
from sms_log_downloader import download_sms_log


def _patient_name(patient: dict) -> str:
    return patient_display_name(patient["first_name"], patient["last_name"])


def _patient_slug(patient: dict) -> str:
    return patient_file_slug(patient["id"], patient["first_name"], patient["last_name"])


async def _reexport_sms(patient_ids: list[str] | None, facility_folder: str) -> int:
    credentials = load_yaml(os.path.join(CONFIG_PATH, "credentials.yaml"))
    settings = load_yaml(os.path.join(CONFIG_PATH, "settings.yaml"))
    facility_name = credentials.get("facility", facility_folder)

    csv_path, _ = select_patient_csv(facility_name)
    if not csv_path:
        print("Error: no patient list CSV found.", file=sys.stderr)
        return 1

    patient_data = {p["id"]: p for p in load_patient_data(csv_path)}
    records_dir = resolve_patients_base(facility_folder)
    folders = index_patient_folders_by_id(records_dir)
    targets = patient_ids or sorted(folders.keys(), key=int)

    rows: list[tuple[dict, str]] = []
    for pid in targets:
        patient = patient_data.get(pid)
        folder = folders.get(pid)
        if patient and folder:
            rows.append((patient, folder))

    if not rows:
        print("No patients to process.")
        return 1

    playwright = browser = None
    updated = 0
    try:
        playwright, browser, context, page = await authenticate_and_select_facility(
            credentials, settings
        )
        for patient, folder in rows:
            pid = patient["id"]
            full_name = _patient_name(patient)
            sms_dir = os.path.join(folder, FOLDER_SMS)
            reset_category(folder, CATEGORY_SMS)
            print(f"\nDownloading SMS log for {pid} ({full_name})...")
            count = await download_sms_log(
                page, sms_dir, patient_id=pid, patient_name=_patient_slug(patient)
            )
            remove_empty_category_folders(folder)
            if count > 0:
                mark_category(folder, CATEGORY_SMS, file_count=count)
                print(f"  OK — wrote SMS log ({count} file)")
            else:
                mark_category(folder, CATEGORY_SMS, empty_ok=True)
                print(f"  No SMS rows for {pid}")
            updated += 1
    finally:
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()

    if csv_path:
        output_dir = delivery_report_dir(facility_folder)
        os.makedirs(output_dir, exist_ok=True)
        safe = facility_folder.replace(" ", "_").replace("(", "").replace(")", "")
        report_path = generate_progress_report(
            facility_name=facility_name,
            patient_data=load_patient_data(csv_path),
            base_downloads_path=records_dir,
            output_dir=output_dir,
            to_pascalcase=to_pascalcase,
            custom_filename=f"{safe}_Export_Progress_{datetime.now().strftime('%m-%d-%Y')}.html",
        )
        print(f"Updated progress report: {report_path}")

    print(f"Re-exported SMS logs for {updated}/{len(targets)} patient(s)")
    return 0


def backfill(facility_folder: str, patient_ids: list[str] | None = None) -> int:
    return asyncio.run(_reexport_sms(patient_ids, facility_folder))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Re-scrape per-patient SMS logs from the Calysta portal."
    )
    parser.add_argument(
        "patient_ids",
        nargs="*",
        help="Patient IDs to re-export (default: all exported patients)",
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

    return backfill(facility_folder, args.patient_ids or None)


if __name__ == "__main__":
    raise SystemExit(main())
