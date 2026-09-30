"""Write per-patient SMS log CSVs and prune header-only exports."""

from __future__ import annotations

import csv
import os
from typing import List

from sms_log_selectors import SMS_LOG_COLUMNS


def sms_log_csv_path(download_dir: str, patient_name: str) -> str:
    return os.path.join(download_dir, f"SMS_Log_{patient_name}.csv")


def is_header_only_sms_csv(path: str) -> bool:
    """True when the SMS CSV exists but has no data rows."""
    from export_status import is_header_only_csv

    return is_header_only_csv(path)


def prune_header_only_sms_files(sms_dir: str) -> int:
    """Delete empty export files in an SMS category folder."""
    from export_status import prune_empty_files_in_category

    return prune_empty_files_in_category(sms_dir)


def write_patient_sms_log(
    download_dir: str,
    patient_name: str,
    rows: List[dict],
) -> tuple[int, int]:
    """
    Write SMS_Log_{PatientName}.csv from scraped portal rows.

    When there are no rows, any existing SMS CSV is removed and no file is written.

    Returns (files_written, row_count).
    """
    save_path = sms_log_csv_path(download_dir, patient_name)

    if not rows:
        if os.path.isfile(save_path):
            os.remove(save_path)
        return 0, 0

    os.makedirs(download_dir, exist_ok=True)
    with open(save_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=SMS_LOG_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    return 1, len(rows)
