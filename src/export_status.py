"""Per-patient export completeness across all 10 categories."""

from __future__ import annotations

import csv
import json
import os
import shutil
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from download_ledger import LEDGER_FILENAME, count_content_files

STATUS_FILENAME = ".export_status.json"
INDEX_FILENAME = "export_index.csv"

# Must match main.PATIENT_SUBFOLDERS order/names
CATEGORY_DETAILS = "01_Patient_Details"
CATEGORY_IMAGES = "02_Patient_Images"
CATEGORY_APPOINTMENTS = "03_Appointment_History"
CATEGORY_SERVICES = "04_Service_History"
CATEGORY_ENCOUNTERS = "05_Encounter_History"
CATEGORY_CONSENTS = "06_Consent_Form_History"
CATEGORY_INVOICES = "07_Patient_Invoices"
CATEGORY_MEMBERSHIP = "08_Membership_Invoices"
CATEGORY_CREDITS = "09_Available_Credits"
CATEGORY_SMS = "10_SMS_Log_History"

ALL_CATEGORIES = [
    CATEGORY_DETAILS,
    CATEGORY_IMAGES,
    CATEGORY_APPOINTMENTS,
    CATEGORY_SERVICES,
    CATEGORY_ENCOUNTERS,
    CATEGORY_CONSENTS,
    CATEGORY_INVOICES,
    CATEGORY_MEMBERSHIP,
    CATEGORY_CREDITS,
    CATEGORY_SMS,
]

# Must match export_index.CATEGORY_CSV_COLUMNS
INDEX_CATEGORY_COLUMNS = {
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

# Short labels for HTML table headers
CATEGORY_SHORT = {
    CATEGORY_DETAILS: "Details",
    CATEGORY_IMAGES: "Images",
    CATEGORY_APPOINTMENTS: "Appts",
    CATEGORY_SERVICES: "Services",
    CATEGORY_ENCOUNTERS: "Encounters",
    CATEGORY_CONSENTS: "Consents",
    CATEGORY_INVOICES: "Invoices",
    CATEGORY_MEMBERSHIP: "Membership",
    CATEGORY_CREDITS: "Credits",
    CATEGORY_SMS: "SMS",
}

STATUS_DONE = "done"
STATUS_DONE_EMPTY = "done_empty"
STATUS_PENDING = "pending"
STATUS_FAILED = "failed"

DONE_STATES = {STATUS_DONE, STATUS_DONE_EMPTY}

def status_path(patient_folder: str) -> str:
    return os.path.join(patient_folder, STATUS_FILENAME)


def _patient_id_from_folder(patient_folder: str) -> str:
    return os.path.basename(patient_folder).split("_", 1)[0]


def _read_export_index_row(patient_folder: str) -> Optional[Dict[str, str]]:
    index_path = os.path.join(os.path.dirname(patient_folder), INDEX_FILENAME)
    if not os.path.isfile(index_path):
        return None
    patient_id = _patient_id_from_folder(patient_folder)
    try:
        with open(index_path, "r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                if (row.get("patient_id") or "").strip() == patient_id:
                    return {k: (row.get(k) or "") for k in row}
    except Exception:
        return None
    return None


def _index_row_is_complete(index_row: Optional[Dict[str, str]]) -> bool:
    return (index_row or {}).get("overall_status", "").strip().lower() == "complete"


def _progress_row_from_export_index(
    patient_id: str,
    full_name: str,
    index_row: Dict[str, str],
) -> Dict[str, Any]:
    cells: Dict[str, Dict[str, Any]] = {}
    done_count = 0
    total_files = 0
    for cat in ALL_CATEGORIES:
        col = INDEX_CATEGORY_COLUMNS[cat]
        label = (index_row.get(col) or "pending").strip() or "pending"
        lower = label.lower()
        if lower in ("pending", "failed"):
            state = STATUS_FAILED if lower == "failed" else STATUS_PENDING
        elif label == "empty ok":
            state = STATUS_DONE_EMPTY
            done_count += 1
        else:
            state = STATUS_DONE
            done_count += 1
            total_files += max(1, label.count(";") + 1)
        cells[cat] = {"state": state, "label": label, "files": 0}

    overall = (index_row.get("overall_status") or "Partial").strip() or "Partial"
    if done_count == len(ALL_CATEGORIES):
        overall = "Complete"

    return {
        "patient_id": patient_id,
        "patient_name": full_name,
        "status": overall,
        "done_categories": done_count,
        "total_categories": len(ALL_CATEGORIES),
        "categories": cells,
    }


def remove_all_export_status_files(base_downloads_path: str) -> int:
    """Remove .export_status.json resume files after export/report completes."""
    if not os.path.isdir(base_downloads_path):
        return 0
    removed = 0
    for name in os.listdir(base_downloads_path):
        path = os.path.join(base_downloads_path, name)
        if not os.path.isdir(path):
            continue
        status_file = status_path(path)
        if not os.path.isfile(status_file):
            continue
        try:
            os.remove(status_file)
            removed += 1
        except OSError:
            pass
    return removed


def _empty_categories() -> Dict[str, Any]:
    return {cat: {"state": STATUS_PENDING, "files": 0, "label": "pending"} for cat in ALL_CATEGORIES}


def load_export_status(patient_folder: str) -> Dict[str, Any]:
    path = status_path(patient_folder)
    if not os.path.isfile(path):
        return {
            "categories": _empty_categories(),
            "complete": False,
            "updated_at": None,
        }
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {
            "categories": _empty_categories(),
            "complete": False,
            "updated_at": None,
        }

    cats = _empty_categories()
    raw = data.get("categories") or {}
    for cat in ALL_CATEGORIES:
        if cat in raw and isinstance(raw[cat], dict):
            cats[cat] = {
                "state": raw[cat].get("state", STATUS_PENDING),
                "files": int(raw[cat].get("files") or 0),
                "label": raw[cat].get("label") or raw[cat].get("state", STATUS_PENDING),
            }
    complete = all(cats[c]["state"] in DONE_STATES for c in ALL_CATEGORIES)
    return {
        "categories": cats,
        "complete": complete,
        "updated_at": data.get("updated_at"),
    }


def save_export_status(patient_folder: str, status: Dict[str, Any]) -> None:
    os.makedirs(patient_folder, exist_ok=True)
    cats = status.get("categories") or _empty_categories()
    complete = all(
        (cats.get(c) or {}).get("state") in DONE_STATES for c in ALL_CATEGORIES
    )
    payload = {
        "categories": cats,
        "complete": complete,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    path = status_path(patient_folder)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp, path)


def is_category_done(patient_folder: str, category: str) -> bool:
    status = load_export_status(patient_folder)
    state = (status["categories"].get(category) or {}).get("state")
    if state in DONE_STATES:
        return True
    if not os.path.isfile(status_path(patient_folder)):
        return _index_row_is_complete(_read_export_index_row(patient_folder))
    return False


def is_patient_export_complete(patient_folder: str) -> bool:
    """True only when all 10 categories are done or done_empty."""
    if not os.path.isdir(patient_folder):
        return False
    status = load_export_status(patient_folder)
    if status.get("complete"):
        return True
    if not os.path.isfile(status_path(patient_folder)):
        return _index_row_is_complete(_read_export_index_row(patient_folder))
    return False


def is_header_only_csv(path: str) -> bool:
    """True when a CSV exists but has no data rows."""
    if not os.path.isfile(path) or not path.lower().endswith(".csv"):
        return False
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            return len(list(csv.DictReader(f))) == 0
    except Exception:
        return False


def is_empty_export_file(path: str) -> bool:
    """True when a file has no real exported content and should be removed."""
    if not os.path.isfile(path):
        return False
    if os.path.getsize(path) == 0:
        return True
    if path.lower().endswith(".csv"):
        try:
            from service_history_downloader import is_placeholder_service_csv

            if is_placeholder_service_csv(path):
                return True
        except ImportError:
            pass
        return is_header_only_csv(path)
    return False


def prune_empty_files_in_category(folder_path: str) -> int:
    """Delete header-only CSVs, zero-byte files, and legacy placeholder exports."""
    if not os.path.isdir(folder_path):
        return 0
    removed = 0
    for name in list(os.listdir(folder_path)):
        if name.startswith(".") or name.endswith(".tmp") or name == LEDGER_FILENAME:
            continue
        full = os.path.join(folder_path, name)
        if os.path.isfile(full) and is_empty_export_file(full):
            os.remove(full)
            removed += 1
    return removed


def folder_file_summary(folder_path: str) -> Tuple[int, str]:
    """
    Count content files and build a label listing each filename (semicolon-separated).
    Returns (count, label_without_empty_ok).
    """
    if not os.path.isdir(folder_path):
        return 0, "pending"

    prune_empty_files_in_category(folder_path)

    names: List[str] = []
    for name in sorted(os.listdir(folder_path)):
        if name.startswith(".") or name.endswith(".tmp") or name == LEDGER_FILENAME:
            continue
        if name == STATUS_FILENAME:
            continue
        full = os.path.join(folder_path, name)
        if not os.path.isfile(full):
            continue
        if is_empty_export_file(full):
            continue
        names.append(name)

    if not names:
        return 0, "pending"

    return len(names), "; ".join(names)


def remove_empty_category_folders(patient_folder: str) -> int:
    """Delete category subfolders with no exported content files."""
    if not os.path.isdir(patient_folder):
        return 0
    removed = 0
    for cat in ALL_CATEGORIES:
        sub = os.path.join(patient_folder, cat)
        if not os.path.isdir(sub):
            continue
        prune_empty_files_in_category(sub)
        count, _ = folder_file_summary(sub)
        if count == 0:
            shutil.rmtree(sub, ignore_errors=True)
            removed += 1
    return removed


def cleanup_empty_folders_in_base(base_downloads_path: str) -> Tuple[int, int]:
    """
    Remove empty category subfolders under every patient folder in base.
    Returns (patients_touched, folders_removed).
    """
    if not os.path.isdir(base_downloads_path):
        return 0, 0
    patients_touched = 0
    folders_removed = 0
    for name in os.listdir(base_downloads_path):
        path = os.path.join(base_downloads_path, name)
        if not os.path.isdir(path):
            continue
        if name == "export_index.csv" or not name.split("_", 1)[0].isdigit():
            continue
        n = remove_empty_category_folders(path)
        if n:
            patients_touched += 1
            folders_removed += n
    return patients_touched, folders_removed


def reset_category(patient_folder: str, category: str) -> None:
    """Mark one category pending so a selective re-export will run it again."""
    status = load_export_status(patient_folder)
    cats = status["categories"]
    cats[category] = {"state": STATUS_PENDING, "files": 0, "label": "pending"}
    status["categories"] = cats
    status["complete"] = False
    save_export_status(patient_folder, status)


def mark_category(
    patient_folder: str,
    category: str,
    *,
    file_count: Optional[int] = None,
    empty_ok: bool = False,
    failed: bool = False,
    label: Optional[str] = None,
) -> None:
    """Update one category after a downloader finishes (or fails)."""
    status = load_export_status(patient_folder)
    cats = status["categories"]

    sub = os.path.join(patient_folder, category)
    counted, auto_label = folder_file_summary(sub)
    if file_count is None:
        file_count = counted

    if failed:
        state = STATUS_FAILED
        cell = label or "failed"
    elif empty_ok or file_count == 0:
        state = STATUS_DONE_EMPTY
        cell = "empty ok"
        file_count = 0
    else:
        state = STATUS_DONE
        cell = label or auto_label or f"{file_count} file"

    cats[category] = {
        "state": state,
        "files": int(file_count),
        "label": cell,
    }
    status["categories"] = cats
    save_export_status(patient_folder, status)


def _progress_row_from_disk(
    patient_id: str,
    full_name: str,
    patient_folder: str,
) -> Dict[str, Any]:
    """Infer export progress from on-disk folders (missing folder = empty ok)."""
    cells: Dict[str, Dict[str, Any]] = {}
    done_count = 0
    for cat in ALL_CATEGORIES:
        sub = os.path.join(patient_folder, cat)
        if os.path.isdir(sub):
            count, label = folder_file_summary(sub)
            if count > 0:
                cells[cat] = {"state": STATUS_DONE, "label": label, "files": count}
            else:
                cells[cat] = {"state": STATUS_DONE_EMPTY, "label": "empty ok", "files": 0}
            done_count += 1
        else:
            cells[cat] = {"state": STATUS_DONE_EMPTY, "label": "empty ok", "files": 0}
            done_count += 1

    if done_count == len(ALL_CATEGORIES):
        overall = "Complete"
    elif done_count == 0:
        overall = "Pending"
    elif any(cells[c]["state"] == STATUS_PENDING for c in ALL_CATEGORIES):
        overall = "Partial"
    else:
        overall = "Partial"

    return {
        "patient_id": patient_id,
        "patient_name": full_name,
        "status": overall,
        "done_categories": done_count,
        "total_categories": len(ALL_CATEGORIES),
        "categories": cells,
    }


def patient_progress_row(
    patient_id: str,
    full_name: str,
    patient_folder: str,
) -> Dict[str, Any]:
    """
    Build one audit row for the progress HTML report.
    Infers labels from disk when status is pending but files exist.
    """
    exists = os.path.isdir(patient_folder)
    if exists and not os.path.isfile(status_path(patient_folder)):
        return _progress_row_from_disk(patient_id, full_name, patient_folder)

    status = load_export_status(patient_folder) if exists else {
        "categories": _empty_categories(),
        "complete": False,
    }
    cats = status["categories"]
    cells = {}
    done_count = 0

    for cat in ALL_CATEGORIES:
        info = cats.get(cat) or {"state": STATUS_PENDING, "files": 0, "label": "pending"}
        state = info.get("state", STATUS_PENDING)
        label = info.get("label") or state
        sub = os.path.join(patient_folder, cat) if exists else ""

        if state in DONE_STATES:
            done_count += 1
            if state == STATUS_DONE_EMPTY:
                label = "empty ok"
            elif sub:
                _, label = folder_file_summary(sub)
        elif exists and sub and os.path.isdir(sub):
            count, disk_label = folder_file_summary(sub)
            if count > 0:
                # Partial: files on disk but category not marked complete
                label = f"partial ({disk_label})"
                state = "partial"
            else:
                label = "pending"
                state = STATUS_PENDING
        else:
            label = "pending"
            state = STATUS_PENDING

        cells[cat] = {"state": state, "label": label, "files": info.get("files", 0)}

    if not exists:
        overall = "Pending"
    elif done_count == len(ALL_CATEGORIES):
        overall = "Complete"
    elif any(cells[c]["state"] == STATUS_FAILED for c in ALL_CATEGORIES):
        overall = "Failed"
    elif done_count == 0 and all(cells[c]["state"] == STATUS_PENDING for c in ALL_CATEGORIES):
        # Has folder but nothing marked / no content
        has_any = any(
            folder_file_summary(os.path.join(patient_folder, c))[0] > 0
            for c in ALL_CATEGORIES
            if os.path.isdir(os.path.join(patient_folder, c))
        )
        overall = "Partial" if has_any else "Pending"
    else:
        overall = "Partial"

    return {
        "patient_id": patient_id,
        "patient_name": full_name,
        "status": overall,
        "done_categories": done_count,
        "total_categories": len(ALL_CATEGORIES),
        "categories": cells,
    }
