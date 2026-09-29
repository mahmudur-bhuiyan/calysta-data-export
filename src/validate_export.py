"""Compare facility Master Data CSVs against per-patient export folders."""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from collections import defaultdict

from export_index import write_export_index
from facility_paths import master_data_dir, resolve_export_index_path, resolve_patients_base
from main import (
    CONFIG_PATH,
    FOLDER_APPOINTMENTS,
    FOLDER_DETAILS,
    FOLDER_SERVICES,
    FOLDER_SMS,
    load_patient_data,
    load_yaml,
    sanitize_facility_folder_name,
    select_patient_csv,
    to_pascalcase,
)


def _find_master_csv(master_dir: str, suffix: str) -> str | None:
    for name in os.listdir(master_dir):
        if name.lower().endswith(".csv") and suffix.lower() in name.lower():
            return os.path.join(master_dir, name)
    return None


def _load_patients(master_dir: str) -> dict[str, dict]:
    path = _find_master_csv(master_dir, "patients_list")
    if not path:
        return {}
    patients = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            pid = (row.get("id") or "").strip()
            if pid:
                patients[pid] = row
    return patients


def _count_by_patient(master_dir: str, suffix: str, key: str = "patient_id") -> dict[str, int]:
    path = _find_master_csv(master_dir, suffix)
    if not path:
        return {}
    counts: dict[str, int] = defaultdict(int)
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            pid = (row.get(key) or "").strip()
            if pid:
                counts[pid] += 1
    return counts


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


def _csv_rows(folder: str, subfolder: str) -> int:
    sub = os.path.join(folder, subfolder)
    if not os.path.isdir(sub):
        return 0
    total = 0
    for fn in os.listdir(sub):
        if fn.endswith(".csv"):
            with open(os.path.join(sub, fn), newline="", encoding="utf-8-sig") as f:
                total += max(0, sum(1 for _ in csv.DictReader(f)))
    return total


def _has_details_csv(folder: str) -> bool:
    sub = os.path.join(folder, FOLDER_DETAILS)
    if not os.path.isdir(sub):
        return False
    return any(name.endswith("_details.csv") for name in os.listdir(sub))


def find_gaps(facility_folder: str) -> dict[str, list[tuple]]:
    """Return gap lists keyed by category. Only patients in Master Patients_List."""
    master_dir = master_data_dir(facility_folder)
    records_dir = resolve_patients_base(facility_folder)
    patients = _load_patients(master_dir)
    exports = _index_export_folders(records_dir)

    master_appts = _count_by_patient(master_dir, "appointments_list")
    master_sms = _count_by_patient(master_dir, "sms_email_logs")

    appt_gaps = []
    appt_count_mismatches = []
    sms_gaps = []
    sms_count_mismatches = []
    details_gaps = []
    missing_folders = []

    for pid in sorted(patients.keys(), key=int):
        folder = exports.get(pid)
        if not folder:
            missing_folders.append((pid, patients[pid].get("first_name", ""), patients[pid].get("last_name", "")))
            continue

        master_appt_count = master_appts.get(pid, 0)
        exported_appts = _csv_rows(folder, FOLDER_APPOINTMENTS)
        if master_appt_count > 0 and exported_appts == 0:
            appt_gaps.append(
                (pid, patients[pid].get("first_name", ""), patients[pid].get("last_name", ""), master_appt_count)
            )
        elif master_appt_count != exported_appts:
            appt_count_mismatches.append(
                (pid, patients[pid].get("first_name", ""), patients[pid].get("last_name", ""), master_appt_count, exported_appts)
            )

        master_sms_count = master_sms.get(pid, 0)
        exported_sms = _csv_rows(folder, FOLDER_SMS)
        if master_sms_count > 0 and exported_sms == 0:
            sms_gaps.append(
                (pid, patients[pid].get("first_name", ""), patients[pid].get("last_name", ""), master_sms_count)
            )
        elif master_sms_count != exported_sms:
            sms_count_mismatches.append(
                (pid, patients[pid].get("first_name", ""), patients[pid].get("last_name", ""), master_sms_count, exported_sms)
            )

        if not _has_details_csv(folder):
            details_gaps.append(
                (pid, patients[pid].get("first_name", ""), patients[pid].get("last_name", ""))
            )

    return {
        "missing_folders": missing_folders,
        "appointment_empty": appt_gaps,
        "appointment_count": appt_count_mismatches,
        "sms_empty": sms_gaps,
        "sms_count": sms_count_mismatches,
        "details_missing": details_gaps,
        "master_patients": len(patients),
        "export_folders": len(exports),
    }


def validate(facility_folder: str) -> dict[str, list[tuple]]:
    master_dir = master_data_dir(facility_folder)
    records_dir = resolve_patients_base(facility_folder)

    if not os.path.isdir(master_dir):
        print(f"Error: master data folder not found: {master_dir}", file=sys.stderr)
        raise SystemExit(1)
    if not os.path.isdir(records_dir):
        print(f"Error: patients records folder not found: {records_dir}", file=sys.stderr)
        raise SystemExit(1)

    gaps = find_gaps(facility_folder)

    print(f"Facility: {facility_folder}")
    print(f"Master patients: {gaps['master_patients']}")
    print(f"Exported folders: {gaps['export_folders']}")
    print(f"Missing export folders (in master, not on disk): {len(gaps['missing_folders'])}")

    print(f"\nAppointment gaps (master rows, export empty): {len(gaps['appointment_empty'])}")
    for row in gaps["appointment_empty"][:20]:
        print(f"  {row[0]}: {row[1]} {row[2]} ({row[3]} in master)")

    print(f"Appointment count mismatches: {len(gaps['appointment_count'])}")
    for row in gaps["appointment_count"][:20]:
        print(f"  {row[0]}: {row[1]} {row[2]} master={row[3]} export={row[4]}")

    print(f"\nSMS/email log gaps (master rows, export empty): {len(gaps['sms_empty'])}")
    for row in gaps["sms_empty"][:20]:
        print(f"  {row[0]}: {row[1]} {row[2]} ({row[3]} in master)")

    print(f"SMS/email log count mismatches: {len(gaps['sms_count'])}")
    for row in gaps["sms_count"][:20]:
        print(f"  {row[0]}: {row[1]} {row[2]} master={row[3]} export={row[4]}")

    print(f"\nPatient details CSV missing: {len(gaps['details_missing'])}")
    for row in gaps["details_missing"][:20]:
        print(f"  {row[0]}: {row[1]} {row[2]}")

    print(
        "\nNote: Service history, encounters, consents, and invoices are portal exports "
        "and are not in Master Data CSVs (except Payments_List, which maps to invoice PDFs)."
    )

    return gaps


def fix_gaps(facility_folder: str, gaps: dict[str, list[tuple]]) -> int:
    """Backfill appointment/SMS CSVs from Master Data for detected gaps."""
    from backfill_appointments_from_master import backfill as backfill_appts
    from backfill_sms_from_master import backfill as backfill_sms

    appt_ids = [row[0] for row in gaps["appointment_empty"]]
    appt_ids.extend(row[0] for row in gaps["appointment_count"])
    sms_ids = [row[0] for row in gaps["sms_empty"]]
    sms_ids.extend(row[0] for row in gaps["sms_count"])

    appt_ids = sorted(set(appt_ids), key=int)
    sms_ids = sorted(set(sms_ids), key=int)

    exit_code = 0
    if appt_ids:
        print(f"\nBackfilling appointments from master for {len(appt_ids)} patient(s)...")
        code = backfill_appts(facility_folder, appt_ids)
        exit_code = max(exit_code, code)
    else:
        print("\nNo appointment gaps to backfill from master.")

    if sms_ids:
        print(f"\nBackfilling SMS/email logs from master for {len(sms_ids)} patient(s)...")
        code = backfill_sms(facility_folder, sms_ids)
        exit_code = max(exit_code, code)
    else:
        print("No SMS/email log gaps to backfill from master.")

    return exit_code


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
        description="Validate per-patient exports against facility Master Data."
    )
    parser.add_argument(
        "--facility",
        help="Facility folder name under downloads/ (default: from credentials.yaml)",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Backfill appointment/SMS CSVs from Master Data when gaps are found",
    )
    parser.add_argument(
        "--update-index",
        action="store_true",
        help="Regenerate export_index.csv after validation/fix",
    )
    args = parser.parse_args()

    if args.facility:
        facility_folder = args.facility
    else:
        credentials = load_yaml(os.path.join(CONFIG_PATH, "credentials.yaml"))
        facility_folder = sanitize_facility_folder_name(
            credentials.get("facility", "Facility")
        )

    gaps = validate(facility_folder)

    has_gaps = any(
        gaps[key]
        for key in (
            "missing_folders",
            "appointment_empty",
            "appointment_count",
            "sms_empty",
            "sms_count",
            "details_missing",
        )
    )

    exit_code = 2 if has_gaps else 0

    if args.fix and has_gaps:
        fix_code = fix_gaps(facility_folder, gaps)
        exit_code = max(exit_code, fix_code)
        print("\nRe-validating after fix...")
        gaps = validate(facility_folder)
        has_gaps = any(
            gaps[key]
            for key in (
                "missing_folders",
                "appointment_empty",
                "appointment_count",
                "sms_empty",
                "sms_count",
                "details_missing",
            )
        )
        exit_code = 2 if has_gaps else 0

    if args.update_index or args.fix:
        index_path = update_export_index(facility_folder)
        print(f"\nExport index: {index_path}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
