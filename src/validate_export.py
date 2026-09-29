"""Compare facility Master Data CSVs against per-patient export folders."""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from collections import defaultdict

from facility_paths import master_data_dir, resolve_patients_base
from main import CONFIG_PATH, load_yaml, sanitize_facility_folder_name


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
    with open(path, newline="", encoding="utf-8") as f:
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
    with open(path, newline="", encoding="utf-8") as f:
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
            with open(os.path.join(sub, fn), newline="", encoding="utf-8") as f:
                total += max(0, sum(1 for _ in csv.DictReader(f)))
    return total


def validate(facility_folder: str) -> int:
    master_dir = master_data_dir(facility_folder)
    records_dir = resolve_patients_base(facility_folder)

    if not os.path.isdir(master_dir):
        print(f"Error: master data folder not found: {master_dir}", file=sys.stderr)
        return 1
    if not os.path.isdir(records_dir):
        print(f"Error: patients records folder not found: {records_dir}", file=sys.stderr)
        return 1

    patients = _load_patients(master_dir)
    master_appts = _count_by_patient(master_dir, "appointments_list")
    exports = _index_export_folders(records_dir)

    print(f"Facility: {facility_folder}")
    print(f"Master patients: {len(patients)}")
    print(f"Exported folders: {len(exports)}")
    print(f"Missing from export: {len(set(patients) - set(exports))}")
    print(f"Extra in export: {len(set(exports) - set(patients))}")

    appt_gaps = []
    for pid, count in sorted(master_appts.items(), key=lambda x: int(x[0])):
        if count <= 0:
            continue
        folder = exports.get(pid)
        if not folder:
            continue
        exported = _csv_rows(folder, "03_Appointment_History")
        if exported == 0:
            p = patients.get(pid, {})
            appt_gaps.append(
                (pid, p.get("first_name", ""), p.get("last_name", ""), count)
            )

    print(f"\nAppointment gaps (master has rows, export CSV empty): {len(appt_gaps)}")
    for pid, first, last, count in appt_gaps:
        print(f"  {pid}: {first} {last} ({count} in master)")

    return 2 if appt_gaps else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate per-patient exports against facility Master Data."
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

    return validate(facility_folder)


if __name__ == "__main__":
    raise SystemExit(main())
