"""Facility download folder layout under downloads/."""

from __future__ import annotations

import os
import shutil
from typing import Dict, Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DOWNLOADS_ROOT = os.path.join(PROJECT_ROOT, "downloads")

MASTER_DATA_SUFFIX = "Master Data"
PATIENTS_RECORDS_SUFFIX = "Patients Records"
DELIVERY_REPORT_SUFFIX = "Delivery Report"

INDEX_FILENAME = "export_index.csv"


def facility_root(facility_folder: str) -> str:
    return os.path.join(DOWNLOADS_ROOT, facility_folder)


def master_data_dir(facility_folder: str) -> str:
    return os.path.join(
        facility_root(facility_folder),
        f"{facility_folder} - {MASTER_DATA_SUFFIX}",
    )


def patients_records_dir(facility_folder: str) -> str:
    return os.path.join(
        facility_root(facility_folder),
        f"{facility_folder} - {PATIENTS_RECORDS_SUFFIX}",
    )


def delivery_report_dir(facility_folder: str) -> str:
    return os.path.join(
        facility_root(facility_folder),
        f"{facility_folder} - {DELIVERY_REPORT_SUFFIX}",
    )


def is_layout_subfolder(name: str) -> bool:
    return (
        name.endswith(f" - {MASTER_DATA_SUFFIX}")
        or name.endswith(f" - {PATIENTS_RECORDS_SUFFIX}")
        or name.endswith(f" - {DELIVERY_REPORT_SUFFIX}")
    )


def _looks_like_patient_folder(name: str) -> bool:
    if not name or is_layout_subfolder(name):
        return False
    prefix = name.split("_", 1)[0]
    return prefix.isdigit()


def _dir_has_patient_folders(directory: str) -> bool:
    if not os.path.isdir(directory):
        return False
    for name in os.listdir(directory):
        if _looks_like_patient_folder(name) and os.path.isdir(
            os.path.join(directory, name)
        ):
            return True
    return False


def ensure_facility_layout(facility_folder: str) -> Dict[str, str]:
    """Create facility root and the three standard subfolders."""
    paths = {
        "root": facility_root(facility_folder),
        "master_data": master_data_dir(facility_folder),
        "patients_records": patients_records_dir(facility_folder),
        "delivery_report": delivery_report_dir(facility_folder),
    }
    for path in paths.values():
        os.makedirs(path, exist_ok=True)
    return paths


def resolve_patients_base(facility_folder: str) -> str:
    """
    Directory that holds patient id_* folders.
    Uses the Patients Records subfolder for new exports; falls back to the
    legacy flat layout when an in-progress export already wrote there.
    """
    new_path = patients_records_dir(facility_folder)
    legacy_path = facility_root(facility_folder)
    if _dir_has_patient_folders(new_path):
        return new_path
    if _dir_has_patient_folders(legacy_path):
        return legacy_path
    return new_path


def resolve_export_index_path(facility_folder: str) -> str:
    """export_index.csv path (Master Data for new exports; legacy root fallback)."""
    new_path = os.path.join(master_data_dir(facility_folder), INDEX_FILENAME)
    legacy_path = os.path.join(facility_root(facility_folder), INDEX_FILENAME)
    if os.path.isfile(new_path):
        return new_path
    if os.path.isfile(legacy_path):
        return legacy_path
    return new_path


def copy_patient_list_to_master_data(facility_folder: str, csv_path: str) -> Optional[str]:
    """Copy the source patient list CSV into Master Data for client delivery."""
    if not csv_path or not os.path.isfile(csv_path):
        return None
    dest = os.path.join(master_data_dir(facility_folder), os.path.basename(csv_path))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.abspath(csv_path) != os.path.abspath(dest):
        shutil.copy2(csv_path, dest)
    return dest


def migrate_legacy_facility_layout(facility_folder: str) -> Dict[str, int]:
    """
    Move a flat legacy facility folder into the three-subfolder layout.
    Safe to re-run: skips items already in the correct place.
    """
    paths = ensure_facility_layout(facility_folder)
    root = paths["root"]
    stats = {
        "patient_folders_moved": 0,
        "master_files_moved": 0,
        "skipped": 0,
    }

    if os.path.isdir(root):
        for name in os.listdir(root):
            src = os.path.join(root, name)
            if name in {
                os.path.basename(paths["master_data"]),
                os.path.basename(paths["patients_records"]),
                os.path.basename(paths["delivery_report"]),
            }:
                continue
            if os.path.isdir(src) and _looks_like_patient_folder(name):
                dest = os.path.join(paths["patients_records"], name)
                if os.path.abspath(src) == os.path.abspath(dest):
                    stats["skipped"] += 1
                    continue
                if os.path.exists(dest):
                    stats["skipped"] += 1
                    continue
                shutil.move(src, dest)
                stats["patient_folders_moved"] += 1
            elif os.path.isfile(src) and name.lower().endswith(".csv"):
                dest = os.path.join(paths["master_data"], name)
                if os.path.abspath(src) == os.path.abspath(dest):
                    stats["skipped"] += 1
                    continue
                if os.path.exists(dest):
                    os.remove(src)
                    stats["skipped"] += 1
                    continue
                shutil.move(src, dest)
                stats["master_files_moved"] += 1

    return stats