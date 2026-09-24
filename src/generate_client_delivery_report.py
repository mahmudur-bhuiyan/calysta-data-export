"""Generate client-facing delivery HTML without running a full export."""

import os
from datetime import datetime

from main import (
    CONFIG_PATH,
    DOWNLOADS_ROOT,
    load_yaml,
    load_patient_data,
    select_patient_csv,
    sanitize_facility_folder_name,
    to_pascalcase,
)
from client_delivery_report import generate_client_delivery_report


def main():
    credentials = load_yaml(os.path.join(CONFIG_PATH, "credentials.yaml"))
    facility_name = credentials.get("facility", "Facility")
    csv_path, _ = select_patient_csv(facility_name)
    if not csv_path:
        print("No patient CSV found in project root.")
        return

    patient_data = load_patient_data(csv_path)
    facility_folder = sanitize_facility_folder_name(facility_name)
    base_downloads_path = os.path.join(DOWNLOADS_ROOT, facility_folder)
    reports_dir = os.path.join(DOWNLOADS_ROOT, "reports")
    os.makedirs(reports_dir, exist_ok=True)

    safe = facility_folder.replace(" ", "_").replace("(", "").replace(")", "")
    delivery_date = datetime.now()
    filename = f"{safe}_Client_Delivery_Report_{delivery_date.strftime('%m-%d-%Y')}.html"
    path = generate_client_delivery_report(
        facility_name=facility_name,
        patient_data=patient_data,
        base_downloads_path=base_downloads_path,
        output_dir=reports_dir,
        to_pascalcase=to_pascalcase,
        custom_filename=filename,
        delivery_date=delivery_date,
    )
    print(f"Client delivery report: {path}")


if __name__ == "__main__":
    main()
