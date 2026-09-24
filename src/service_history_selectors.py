# Selectors for patient Service History page

SERVICE_HISTORY_URL = "https://www.calystaproemr.com/patients/patient-services/{patient_id}"

# Columns to export (exact CSV headers)
SERVICE_HISTORY_COLUMNS = [
    "Service Name",
    "Package Name",
    "Date Received",
    "Appointment Date",
    "Created on",
]

NEXT_BUTTON = 'a:has-text("next >")'
DATATABLES_EMPTY = "td.dataTables_empty, .dataTables_empty"
