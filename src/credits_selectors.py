# Selectors / patterns for patient credit pages

BOOKING_CREDITS_URL = "https://www.calystaproemr.com/payments/online-booking-payments/{patient_id}"
BANKED_CREDITS_URL = "https://www.calystaproemr.com/patients/bank-credits/{patient_id}"
EGIFT_CARDS_URL = "https://www.calystaproemr.com/patient-services-invoices/egift-cards/{patient_id}"
REFERRAL_CREDITS_URL = "https://www.calystaproemr.com/patient-services-invoices/referral-credits/{patient_id}"

PAGE_CONTENT = ".page-wrapper, .container-fluid, body"

# Label:Amount patterns scraped from page text
AVAILABLE_LABEL_AMOUNT_RE = r"(Available\s+[A-Za-z0-9][A-Za-z0-9 \-]{0,60}?)\s*:\s*(\$\s*[\d,]+\.?\d*)"

# DataTables pagination
NEXT_BUTTON = 'a:has-text("next >")'
DATATABLES_EMPTY = "td.dataTables_empty, .dataTables_empty"
NO_RESULTS_TEXT = "No results found"
