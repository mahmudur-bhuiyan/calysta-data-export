# Write per-patient SMS/email logs from facility Master Data CSV

import os

from sms_log_master import write_patient_sms_log
from sms_log_selectors import SMS_LOG_COLUMNS


def export_sms_log(download_dir, patient_id, patient_name, sms_by_patient):
    """
    Write SMS_Log_{PatientName}.csv from the facility Master Data log export.

    Columns: patient_id, patient_name, type, message, category, sent_on
    Empty patients get a header-only CSV.

    Returns 1 on success, 0 on failure.
    """
    try:
        rows = sms_by_patient.get(str(patient_id).strip(), [])
        files_written, row_count = write_patient_sms_log(download_dir, patient_name, rows)
        filename = f"SMS_Log_{patient_name}.csv"
        print(f"[SMS] Wrote {filename} ({row_count} row(s)) from master data")
        return files_written
    except Exception as e:
        print(f"[SMS] Error writing SMS log for {patient_id}: {e}")
        return 0
