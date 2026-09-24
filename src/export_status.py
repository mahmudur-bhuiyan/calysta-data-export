"""Per-patient export completeness across all 10 categories."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from download_ledger import LEDGER_FILENAME, count_content_files

STATUS_FILENAME = ".export_status.json"

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

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
PDF_EXTS = {".pdf"}
CSV_EXTS = {".csv"}


def status_path(patient_folder: str) -> str:
    return os.path.join(patient_folder, STATUS_FILENAME)


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
    return state in DONE_STATES


def is_patient_export_complete(patient_folder: str) -> bool:
    """True only when all 10 categories are done or done_empty."""
    if not os.path.isdir(patient_folder):
        return False
    status = load_export_status(patient_folder)
    if status.get("complete"):
        return True
    # Legacy / repaired: if status file missing but we can prove all 10 from disk
    # do not auto-skip legacy incomplete 5-folder patients.
    return False


def folder_file_summary(folder_path: str) -> Tuple[int, str]:
    """
    Count content files and build a short label like '5 pdf', '10 jpg', '1 csv'.
    Returns (count, label_without_empty_ok).
    """
    if not os.path.isdir(folder_path):
        return 0, "pending"

    counts: Dict[str, int] = {}
    total = 0
    for name in os.listdir(folder_path):
        if name.startswith(".") or name.endswith(".tmp") or name == LEDGER_FILENAME:
            continue
        if name == STATUS_FILENAME:
            continue
        full = os.path.join(folder_path, name)
        if not os.path.isfile(full):
            continue
        total += 1
        ext = os.path.splitext(name)[1].lower()
        if ext in PDF_EXTS:
            key = "pdf"
        elif ext in IMAGE_EXTS:
            key = ext.lstrip(".") or "img"
            if key == "jpeg":
                key = "jpg"
        elif ext in CSV_EXTS:
            key = "csv"
        elif ext:
            key = ext.lstrip(".")
        else:
            key = "file"
        counts[key] = counts.get(key, 0) + 1

    if total == 0:
        return 0, "pending"

    # Prefer a single dominant type label
    parts = [f"{n} {k}" for k, n in sorted(counts.items(), key=lambda x: (-x[1], x[0]))]
    return total, ", ".join(parts)


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
            elif label in ("done", "pending", "") and sub:
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
