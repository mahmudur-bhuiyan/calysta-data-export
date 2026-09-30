"""Facility-level export_index.csv — live patient status sorted by patient id."""

from __future__ import annotations

import asyncio
import csv
import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from export_status import (
    ALL_CATEGORIES,
    CATEGORY_APPOINTMENTS,
    CATEGORY_CONSENTS,
    CATEGORY_CREDITS,
    CATEGORY_DETAILS,
    CATEGORY_ENCOUNTERS,
    CATEGORY_IMAGES,
    CATEGORY_INVOICES,
    CATEGORY_MEMBERSHIP,
    CATEGORY_SERVICES,
    CATEGORY_SMS,
    load_export_status,
    patient_progress_row,
)

INDEX_FILENAME = "export_index.csv"

CATEGORY_CSV_COLUMNS = {
    CATEGORY_DETAILS: "01_details",
    CATEGORY_IMAGES: "02_images",
    CATEGORY_APPOINTMENTS: "03_appointments",
    CATEGORY_SERVICES: "04_services",
    CATEGORY_ENCOUNTERS: "05_encounters",
    CATEGORY_CONSENTS: "06_consents",
    CATEGORY_INVOICES: "07_invoices",
    CATEGORY_MEMBERSHIP: "08_membership",
    CATEGORY_CREDITS: "09_credits",
    CATEGORY_SMS: "10_sms",
}

FIELDNAMES = [
    "patient_id",
    "first_name",
    "last_name",
    "folder_name",
    "overall_status",
    "categories_done",
    "total_files",
    *CATEGORY_CSV_COLUMNS.values(),
    "exported_at",
    "last_updated",
]


def index_path(base_downloads_path: str) -> str:
    return os.path.join(base_downloads_path, INDEX_FILENAME)


def resolve_patient_folder(
    base_downloads_path: str,
    patient: Dict[str, str],
    to_pascalcase: Callable[[str], str],
) -> str:
    """Expected folder path, or an existing folder matching this patient id."""
    from patient_naming import patient_file_slug

    patient_id = str(patient["id"]).strip()
    expected = os.path.join(
        base_downloads_path,
        patient_file_slug(patient_id, patient["first_name"], patient["last_name"]),
    )
    if os.path.isdir(expected):
        return expected
    if os.path.isdir(base_downloads_path):
        prefix = f"{patient_id}_"
        for name in os.listdir(base_downloads_path):
            if name.startswith(prefix):
                candidate = os.path.join(base_downloads_path, name)
                if os.path.isdir(candidate):
                    return candidate
    return expected


def _sort_key(patient_id: str) -> tuple:
    pid = str(patient_id).strip()
    if pid.isdigit():
        return (0, int(pid))
    return (1, pid)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _exported_at_from_folder(patient_folder: str, overall_status: str) -> str:
    if overall_status not in ("Complete", "Skipped"):
        return ""
    if not os.path.isdir(patient_folder):
        return ""
    status = load_export_status(patient_folder)
    if status.get("updated_at"):
        return str(status["updated_at"])
    return _utc_now()


def build_csv_row(
    patient: Dict[str, str],
    base_downloads_path: str,
    to_pascalcase: Callable[[str], str],
    *,
    last_updated: Optional[str] = None,
) -> Dict[str, str]:
    """Build one CSV row from disk state (export status + folder contents)."""
    patient_folder = resolve_patient_folder(base_downloads_path, patient, to_pascalcase)
    first = to_pascalcase(patient["first_name"])
    last = to_pascalcase(patient["last_name"])
    full_name = f"{first} {last}"
    progress = patient_progress_row(str(patient["id"]), full_name, patient_folder)

    folder_name = ""
    if os.path.isdir(patient_folder):
        folder_name = os.path.basename(patient_folder)

    total_files = sum(
        int((progress["categories"].get(cat) or {}).get("files") or 0)
        for cat in ALL_CATEGORIES
    )
    overall = progress["status"]

    row: Dict[str, str] = {
        "patient_id": str(patient["id"]).strip(),
        "first_name": first,
        "last_name": last,
        "folder_name": folder_name,
        "overall_status": overall,
        "categories_done": (
            f"{progress['done_categories']}/{progress['total_categories']}"
        ),
        "total_files": str(total_files),
        "exported_at": _exported_at_from_folder(patient_folder, overall),
        "last_updated": last_updated or _utc_now(),
    }
    for cat in ALL_CATEGORIES:
        col = CATEGORY_CSV_COLUMNS[cat]
        row[col] = (progress["categories"].get(cat) or {}).get("label") or "pending"
    return row


def read_index_rows(path: str) -> Dict[str, Dict[str, str]]:
    if not os.path.isfile(path):
        return {}
    rows: Dict[str, Dict[str, str]] = {}
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            pid = (raw.get("patient_id") or "").strip()
            if pid:
                rows[pid] = {k: (raw.get(k) or "") for k in FIELDNAMES}
    return rows


def _write_rows(path: str, rows: Dict[str, Dict[str, str]]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    ordered = sorted(rows.values(), key=lambda r: _sort_key(r.get("patient_id", "")))
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for row in ordered:
            writer.writerow({k: row.get(k, "") for k in FIELDNAMES})
    os.replace(tmp, path)


def write_export_index(
    patient_data: List[Dict[str, str]],
    base_downloads_path: str,
    to_pascalcase: Callable[[str], str],
    *,
    path: Optional[str] = None,
) -> str:
    """
    Build or refresh the full export index from the patient list and disk state.
    Returns path to the CSV file.
    """
    out = path or index_path(base_downloads_path)
    rows: Dict[str, Dict[str, str]] = {}
    for patient in patient_data:
        pid = str(patient["id"]).strip()
        rows[pid] = build_csv_row(patient, base_downloads_path, to_pascalcase)
    _write_rows(out, rows)
    return out


def summarize_index(rows: Dict[str, Dict[str, str]]) -> Dict[str, int]:
    summary = {"total": len(rows), "complete": 0, "partial": 0, "pending": 0, "failed": 0}
    for row in rows.values():
        status = (row.get("overall_status") or "").lower()
        if status == "complete":
            summary["complete"] += 1
        elif status == "partial":
            summary["partial"] += 1
        elif status == "failed":
            summary["failed"] += 1
        else:
            summary["pending"] += 1
    return summary


class ExportIndex:
    """Thread-safe (async) export index updated by all workers after each patient."""

    def __init__(self, path: str):
        self.path = path
        self._lock = asyncio.Lock()

    def initialize(
        self,
        patient_data: List[Dict[str, str]],
        base_downloads_path: str,
        to_pascalcase: Callable[[str], str],
    ) -> Dict[str, int]:
        """Create or refresh index from patient list + on-disk export state."""
        rows: Dict[str, Dict[str, str]] = {}
        for patient in patient_data:
            pid = str(patient["id"]).strip()
            rows[pid] = build_csv_row(patient, base_downloads_path, to_pascalcase)
        _write_rows(self.path, rows)
        return summarize_index(rows)

    async def update_patient(
        self,
        patient: Dict[str, str],
        base_downloads_path: str,
        to_pascalcase: Callable[[str], str],
    ) -> None:
        """Update one patient row and rewrite the CSV sorted by patient id."""
        pid = str(patient["id"]).strip()
        async with self._lock:
            rows = read_index_rows(self.path)
            if not rows:
                rows = {
                    str(p["id"]).strip(): build_csv_row(
                        p, base_downloads_path, to_pascalcase
                    )
                    for p in [patient]
                }
            else:
                rows[pid] = build_csv_row(
                    patient, base_downloads_path, to_pascalcase
                )
            _write_rows(self.path, rows)
