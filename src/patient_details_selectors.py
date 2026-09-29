# Selectors / field list for patient details view page

PATIENT_DETAILS_URL = "https://www.calystaproemr.com/patients/view/{patient_id}"

# Exact CSV column headers (and page h6 labels to match)
PATIENT_DETAIL_FIELDS = [
    "First name",
    "Last name",
    "Date of birth",
    "Gender",
    "Patient Since",
    "Email",
    "Cell phone",
    "Home phone",
    "Address",
    "ZIP",
    "State",
    "City",
    "Sms texting",
    "Email notification",
    "Source",
    "Referred By",
    "Total Referred",
    "Referral Code",
    "Primary Pharmacy Name",
    "Primary Pharmacy Address",
    "Alternative Pharmacy",
    "Alternative Pharmacy Address",
]

# Written to CSV (patient_id is supplied by the exporter, not scraped from the page)
PATIENT_DETAIL_CSV_COLUMNS = ["patient_id"] + PATIENT_DETAIL_FIELDS
