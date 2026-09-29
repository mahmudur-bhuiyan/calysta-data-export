"""Load facility SMS/email logs from Master Data and write per-patient CSVs."""

from __future__ import annotations

import csv
import os
from collections import defaultdict
from typing import Dict, List, Optional

from sms_log_selectors import SMS_LOG_COLUMNS


def find_master_sms_csv(master_dir: str) -> Optional[str]:
    """Return path to *_Sms_Email_Logs_List.csv under Master Data."""
    if not os.path.isdir(master_dir):
        return None
    for name in os.listdir(master_dir):
        lower = name.lower()
        if lower.endswith(".csv") and "sms_email_logs" in lower.replace("_", ""):
            return os.path.join(master_dir, name)
        if lower.endswith(".csv") and "sms" in lower and "email" in lower and "log" in lower:
            return os.path.join(master_dir, name)
    return None


def load_sms_logs_by_patient(master_path: Optional[str]) -> Dict[str, List[dict]]:
    """Index master SMS/email log rows by patient_id."""
    if not master_path or not os.path.isfile(master_path):
        return {}

    by_patient: Dict[str, List[dict]] = defaultdict(list)
    with open(master_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pid = (row.get("patient_id") or "").strip()
            if not pid:
                continue
            by_patient[pid].append({col: (row.get(col) or "").strip() for col in SMS_LOG_COLUMNS})

    for pid in by_patient:
        by_patient[pid].sort(key=lambda r: r.get("sent_on") or "")
    return dict(by_patient)


def write_patient_sms_log(
    download_dir: str,
    patient_name: str,
    rows: List[dict],
) -> tuple[int, int]:
    """
    Write SMS_Log_{PatientName}.csv from master log rows.

    Returns (files_written, row_count).
    """
    os.makedirs(download_dir, exist_ok=True)
    filename = f"SMS_Log_{patient_name}.csv"
    save_path = os.path.join(download_dir, filename)

    with open(save_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=SMS_LOG_COLUMNS)
        writer.writeheader()
        if rows:
            writer.writerows(rows)

    return 1, len(rows)
