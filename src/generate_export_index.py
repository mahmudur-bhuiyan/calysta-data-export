"""Rebuild export_index.csv from patient list and on-disk export folders."""

import os

from main import (
    CONFIG_PATH,
    DOWNLOADS_ROOT,
    load_patient_data,
    load_yaml,
    sanitize_facility_folder_name,
    select_patient_csv,
    to_pascalcase,
)
from export_index import read_index_rows, summarize_index, write_export_index


def main():
    credentials = load_yaml(os.path.join(CONFIG_PATH, "credentials.yaml"))
    facility_name = credentials.get("facility", "Facility")
    csv_path, _ = select_patient_csv(facility_name)
    if not csv_path:
        print("No patient CSV found in patient_lists/.")
        return

    patient_data = load_patient_data(csv_path)
    if not patient_data:
        print("No valid patient rows in CSV.")
        return

    facility_folder = sanitize_facility_folder_name(facility_name)
    base_downloads_path = os.path.join(DOWNLOADS_ROOT, facility_folder)
    out = write_export_index(patient_data, base_downloads_path, to_pascalcase)
    summary = summarize_index(read_index_rows(out))
    print(f"Export index: {out}")
    print(
        f"  {summary['complete']} complete, {summary['partial']} partial, "
        f"{summary['pending']} pending, {summary['failed']} failed "
        f"(of {summary['total']} total)"
    )


if __name__ == "__main__":
    main()
