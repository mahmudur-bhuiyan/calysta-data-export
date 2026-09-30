"""Audit portal service history for all patients: skip when empty, download when present."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime

from auth import authenticate_and_select_facility
from export_index import write_export_index
from export_status import CATEGORY_SERVICES, mark_category, remove_empty_category_folders
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
from patient_naming import patient_display_name, patient_file_slug
from progress_report import generate_progress_report
from service_history_downloader import download_service_history


def _patient_name(patient: dict) -> str:
    return patient_display_name(patient["first_name"], patient["last_name"])


def _patient_slug(patient: dict) -> str:
    return patient_file_slug(patient["id"], patient["first_name"], patient["last_name"])


def _has_service_csv(patient_folder: str) -> bool:
    svc_dir = os.path.join(patient_folder, FOLDER_SERVICES)
    if not os.path.isdir(svc_dir):
        return False
    return any(name.lower().endswith(".csv") for name in os.listdir(svc_dir))


def _select_patient_ids(
    all_patients: list[dict],
    folders_by_id: dict[str, str],
    *,
    missing_only: bool,
    all_patients_flag: bool,
    explicit_ids: list[str],
    start_from: str | None,
) -> list[str]:
    if explicit_ids:
        ids = list(explicit_ids)
    elif all_patients_flag:
        ids = [p["id"] for p in all_patients if p["id"] in folders_by_id]
    elif missing_only:
        ids = [
            p["id"]
            for p in all_patients
            if p["id"] in folders_by_id and not _has_service_csv(folders_by_id[p["id"]])
        ]
    else:
        return []

    if start_from:
        try:
            idx = ids.index(start_from)
            ids = ids[idx:]
        except ValueError:
            print(f"Warning: start-from id {start_from} not in target list — processing all")

    return ids


async def audit_service_history(
    patient_ids: list[str],
    *,
    update_index_every: int = 50,
) -> int:
    credentials = load_yaml(os.path.join(CONFIG_PATH, "credentials.yaml"))
    settings = load_yaml(os.path.join(CONFIG_PATH, "settings.yaml"))
    facility_name = credentials.get("facility", "Facility")
    facility_folder = sanitize_facility_folder_name(facility_name)

    csv_path, _ = select_patient_csv(facility_name)
    if not csv_path:
        print("Error: no patient list CSV found.", file=sys.stderr)
        return 1

    all_patients = load_patient_data(csv_path)
    patient_data = {p["id"]: p for p in all_patients}
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

    print(f"Auditing service history for {len(targets)} patient(s)...")

    playwright = browser = None
    with_data = 0
    empty = 0
    failed = 0
    try:
        playwright, browser, _context, page = await authenticate_and_select_facility(
            credentials, settings
        )
        for i, (patient, folder) in enumerate(targets, start=1):
            pid = patient["id"]
            full_name = _patient_name(patient)
            svc_dir = os.path.join(folder, FOLDER_SERVICES)
            print(f"\n[{i}/{len(targets)}] {pid} ({full_name})", flush=True)
            try:
                count = await download_service_history(
                    page, svc_dir, patient_id=pid, patient_name=_patient_slug(patient)
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
                    print("  skip — no portal service rows", flush=True)
                else:
                    with_data += 1
                    print(f"  downloaded — {count} row(s)", flush=True)
            except Exception as exc:
                failed += 1
                print(f"  error — {exc}", flush=True)

            if update_index_every and i % update_index_every == 0:
                index_path = write_export_index(
                    all_patients,
                    base_downloads_path,
                    to_pascalcase,
                    path=resolve_export_index_path(facility_folder),
                )
                print(f"  (checkpoint index: {index_path})")
    finally:
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()

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
        f"Done: {with_data} downloaded, {empty} empty (skipped), "
        f"{failed} errors, {len(targets)} total"
    )
    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check portal service history for patients. "
            "Skip when empty; download CSV and update export index when data exists."
        )
    )
    parser.add_argument("patient_ids", nargs="*", help="Optional explicit patient IDs")
    parser.add_argument("--file", help="Text file with one patient ID per line")
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="Only patients without a service history CSV on disk (default when no IDs)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Audit every patient folder (re-download when portal has rows)",
    )
    parser.add_argument(
        "--start-from",
        metavar="ID",
        help="Resume from this patient id within the selected list",
    )
    parser.add_argument(
        "--update-index-every",
        type=int,
        default=50,
        help="Rewrite export_index.csv every N patients (0 = only at end)",
    )
    args = parser.parse_args()

    credentials = load_yaml(os.path.join(CONFIG_PATH, "credentials.yaml"))
    facility_name = credentials.get("facility", "Facility")
    csv_path, _ = select_patient_csv(facility_name)
    if not csv_path:
        print("Error: no patient list CSV found.", file=sys.stderr)
        return 1

    all_patients = load_patient_data(csv_path)
    base_downloads_path = resolve_patients_base(
        sanitize_facility_folder_name(facility_name)
    )
    folders_by_id = index_patient_folders_by_id(base_downloads_path)

    explicit_ids = list(args.patient_ids)
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            explicit_ids.extend(line.strip() for line in f if line.strip())

    missing_only = args.missing_only
    all_flag = args.all
    if not explicit_ids and not missing_only and not all_flag:
        missing_only = True

    if missing_only and all_flag:
        print("Use only one of --missing-only or --all", file=sys.stderr)
        return 1

    patient_ids = _select_patient_ids(
        all_patients,
        folders_by_id,
        missing_only=missing_only,
        all_patients_flag=all_flag,
        explicit_ids=explicit_ids,
        start_from=args.start_from,
    )
    if not patient_ids:
        print("No matching patients.", file=sys.stderr)
        return 1

    return asyncio.run(
        audit_service_history(
            patient_ids,
            update_index_every=args.update_index_every,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
