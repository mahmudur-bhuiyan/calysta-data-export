"""Re-scrape patient service history for specific patient IDs."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime

from auth import authenticate_and_select_facility
from export_index import write_export_index
from export_status import CATEGORY_SERVICES, mark_category, remove_empty_category_folders, reset_category
from facility_paths import delivery_report_dir, resolve_export_index_path, resolve_patients_base
from main import (
    CONFIG_PATH,
    FOLDER_SERVICES,
    index_patient_folders_by_id,
    load_patient_data,
    load_yaml,
    sanitize_facility_folder_name,
    select_patient_csv,
    to_pascalcase,
)
from progress_report import generate_progress_report
from service_history_downloader import download_service_history


def _patient_name(patient: dict) -> str:
    first = to_pascalcase(patient["first_name"])
    last = to_pascalcase(patient["last_name"])
    return f"{first} {last}"


async def reexport_services(patient_ids: list[str]) -> int:
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

    playwright = browser = context = page = None
    with_data = 0
    empty = 0
    try:
        playwright, browser, context, page = await authenticate_and_select_facility(
            credentials, settings
        )
        for patient, folder in targets:
            pid = patient["id"]
            full_name = _patient_name(patient)
            svc_dir = os.path.join(folder, FOLDER_SERVICES)
            reset_category(folder, CATEGORY_SERVICES)
            os.makedirs(svc_dir, exist_ok=True)
            print(f"\nDownloading service history for {pid} ({full_name})...")
            count = await download_service_history(
                page, svc_dir, patient_id=pid, patient_name=full_name
            )
            mark_category(
                folder,
                CATEGORY_SERVICES,
                file_count=count,
                empty_ok=(count == 0),
            )
            if count == 0:
                remove_empty_category_folders(folder)
                empty += 1
                print(f"  No service history rows for {pid}")
            else:
                with_data += 1
                print(f"  OK — wrote {count} service row(s)")
    finally:
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()

    all_patients = load_patient_data(csv_path)
    index_path = write_export_index(
        all_patients,
        base_downloads_path,
        to_pascalcase,
        path=resolve_export_index_path(facility_folder),
    )
    output_dir = delivery_report_dir(facility_folder)
    os.makedirs(output_dir, exist_ok=True)
    safe = facility_folder.replace(" ", "_").replace("(", "").replace(")", "")
    report_path = generate_progress_report(
        facility_name=facility_name,
        patient_data=all_patients,
        base_downloads_path=base_downloads_path,
        output_dir=output_dir,
        to_pascalcase=to_pascalcase,
        custom_filename=f"{safe}_Export_Progress_{datetime.now().strftime('%m-%d-%Y')}.html",
    )
    print(f"\nExport index: {index_path}")
    print(f"Progress report: {report_path}")
    print(
        f"Done: {with_data} with service data, {empty} empty, "
        f"{len(targets)} total processed"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Re-scrape service history for specific patient IDs."
    )
    parser.add_argument(
        "patient_ids",
        nargs="*",
        help="Patient IDs to re-export",
    )
    parser.add_argument(
        "--file",
        help="Text file with one patient ID per line",
    )
    args = parser.parse_args()

    patient_ids = list(args.patient_ids)
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            patient_ids.extend(line.strip() for line in f if line.strip())

    if not patient_ids:
        print("Provide patient IDs or --file", file=sys.stderr)
        return 1

    return asyncio.run(reexport_services(patient_ids))


if __name__ == "__main__":
    raise SystemExit(main())
