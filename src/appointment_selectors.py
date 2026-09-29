# Selectors for appointment history export

# Export button on the appointment list page
EXPORT_BUTTON = 'button.btn-calysta-border:has-text("Export")'

# DataTables empty-state cell (shown when patient has no appointments)
EMPTY_TABLE_CELL = 'td.dataTables_empty, .dataTables_empty'

# DataTables pagination/info text, e.g. "showing 0 record(s) out of 0 total"
DATATABLES_INFO = '.dataTables_info'

# Portal export columns (phone columns are dropped when writing CSV)
APPOINTMENT_PORTAL_HEADERS = [
    "Patient",
    "Patient Email Address",
    "Provider",
    "Resource",
    "Booked By",
    "Services",
    "Appointment note",
    "Appointment date",
    "Appointment time",
    "Booking Date",
    "Booking Time",
    "Appointment status",
]

APPOINTMENT_CSV_COLUMNS = ["patient_id"] + APPOINTMENT_PORTAL_HEADERS
