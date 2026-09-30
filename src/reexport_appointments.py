"""Re-download appointment history for specific patient IDs."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime

from auth import authenticate_and_select_facility
from appointment_downloader import download_appointment_history
from export_status import CATEGORY_APPOINTMENTS, mark_category, reset_category
from facility_paths import delivery_report_dir, resolve_patients_base
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
from patient_naming import patient_display_name, patient_file_slug
from progress_report import generate_progress_report


def _patient_name(patient: dict) -> str:
    return patient_display_name(patient["first_name"], patient["last_name"])


def _patient_slug(patient: dict) -> str:
    return patient_file_slug(patient["id"], patient["first_name"], patient["last_name"])


async def reexport_appointments(patient_ids: list[str]) -> int:
    credentials = load_yaml(os.path.join(CONFIG_PATH, "credentials.yaml"))
    settings = load_yaml(os.path.join(CONFIG_PATH, "settings.yaml"))
    facility_name = credentials.get("facility", "Facility")
    facility_folder = sanitize_facility_folder_name(facility_name)

    csv_path, _ = select_patient_csv(facility_name)
    if not csv_path:
        print("Error: no patient list CSV found.", file=sys.stderr)
        return 1

    patient_data = {p["id"]: p for p in load_patient_data(csv_path)}
    base_downloads_path = resolve_patients_base(facility_folder)
    folders_by_id = index_patient_folders_by_id(base_downloads_path)

    targets: list[tuple[dict, str]] = []
    for pid in patient_ids:
        patient = patient_data.get(pid)
        if not patient:
            print(f"Warning: patient id {pid} not found in patient list — skipping")
            continue
        folder = folders_by_id.get(pid)
        if not folder:
            print(f"Warning: no export folder for patient id {pid} — skipping")
            continue
        targets.append((patient, folder))

    if not targets:
        print("No patients to process.")
        return 1

    for patient, folder in targets:
        reset_category(folder, CATEGORY_APPOINTMENTS)
        print(f"Reset appointments for {patient['id']} ({_patient_name(patient)})")

    playwright = browser = context = page = None
    failed = 0
    try:
        playwright, browser, context, page = await authenticate_and_select_facility(
            credentials, settings
        )
        for patient, folder in targets:
            pid = patient["id"]
            full_name = _patient_name(patient)
            appt_dir = os.path.join(folder, FOLDER_APPOINTMENTS)
            os.makedirs(appt_dir, exist_ok=True)
            print(f"\nDownloading appointments for {pid} ({full_name})...")
            count = await download_appointment_history(
                page, appt_dir, patient_id=pid, patient_name=_patient_slug(patient)
            )
            mark_category(
                folder,
                CATEGORY_APPOINTMENTS,
                file_count=count,
                empty_ok=(count == 0),
            )
            if count > 0:
                print(f"  OK — wrote {count} appointment file(s)")
            else:
                print(f"  No appointments exported for {pid}")
                failed += 1
    finally:
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()

    output_dir = delivery_report_dir(facility_folder)
    os.makedirs(output_dir, exist_ok=True)
    safe = facility_folder.replace(" ", "_").replace("(", "").replace(")", "")
    report_path = generate_progress_report(
        facility_name=facility_name,
        patient_data=load_patient_data(csv_path),
        base_downloads_path=base_downloads_path,
        output_dir=output_dir,
        to_pascalcase=to_pascalcase,
        custom_filename=f"{safe}_Export_Progress_{datetime.now().strftime('%m-%d-%Y')}.html",
    )
    print(f"\nUpdated progress report: {report_path}")
    print(f"Done: {len(targets) - failed}/{len(targets)} patients received appointment files")
    return 0 if failed == 0 else 2


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Re-download appointment history for specific patient IDs."
    )
    parser.add_argument(
        "patient_ids",
        nargs="+",
        help="Patient IDs to re-export (e.g. 166258 171503)",
    )
    args = parser.parse_args()
    return asyncio.run(reexport_appointments(args.patient_ids))


if __name__ == "__main__":
    raise SystemExit(main())
