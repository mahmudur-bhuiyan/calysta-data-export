import asyncio
import os
import re
import yaml
import csv
from auth import authenticate_and_select_facility
from encounter_downloader import download_encounter_documents
from consent_downloader import download_consent_documents
from invoice_downloader import download_invoice_documents
from image_downloader import download_patient_images
from membership_invoice_downloader import download_membership_invoices
from appointment_downloader import download_appointment_history
from credits_downloader import download_all_credits
from service_history_downloader import download_service_history
from sms_log_downloader import download_sms_log
from patient_details_downloader import download_patient_details
from logger import init_logger, get_logger
from report_generator import generate_execution_report
from download_ledger import count_content_files, LEDGER_FILENAME
from export_status import (
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
    is_category_done,
    is_patient_export_complete,
    mark_category,
)
from progress_report import generate_progress_report
from client_delivery_report import generate_client_delivery_report

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
CONFIG_PATH = os.path.join(PROJECT_ROOT, 'config')
DOWNLOADS_ROOT = os.path.join(PROJECT_ROOT, 'downloads')
PATIENT_LISTS_DIR = os.path.join(PROJECT_ROOT, 'patient_lists')


def sanitize_facility_folder_name(facility_name):
    """Build a Windows-safe downloads subfolder name from the facility label."""
    name = (facility_name or 'Facility').strip()
    for ch in '<>:"/\\|?*':
        name = name.replace(ch, '')
    name = ' '.join(name.split())
    return name or 'Facility'


def csv_has_patient_columns(csv_path):
    """Return True if the CSV header includes id, first_name, last_name."""
    try:
        with open(csv_path, 'r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            fields = {((h or '').strip().lower()) for h in (reader.fieldnames or [])}
        return {'id', 'first_name', 'last_name'}.issubset(fields)
    except Exception:
        return False


_FACILITY_MATCH_STOPWORDS = frozenset({'and', 'the', 'of', 'a', 'an'})


def _normalize_facility_key(name):
    """Alphanumeric tokens (minus stopwords) joined for loose filename matching."""
    tokens = re.findall(r'[a-z0-9]+', (name or '').lower())
    tokens = [t for t in tokens if t not in _FACILITY_MATCH_STOPWORDS]
    return ''.join(tokens)


def filename_matches_facility(facility_name, csv_path):
    """True if the CSV basename matches the configured facility name."""
    facility_key = _normalize_facility_key(facility_name)
    if not facility_key:
        return False
    file_key = _normalize_facility_key(os.path.splitext(os.path.basename(csv_path))[0])
    return facility_key in file_key or file_key in facility_key


def discover_patient_csvs():
    """
    Find patient-list CSV files in patient_lists/ only.
    CSVs anywhere else in the project are ignored.
    """
    matches = []
    if not os.path.isdir(PATIENT_LISTS_DIR):
        return matches
    for name in os.listdir(PATIENT_LISTS_DIR):
        if not name.lower().endswith('.csv'):
            continue
        path = os.path.join(PATIENT_LISTS_DIR, name)
        if not os.path.isfile(path):
            continue
        if csv_has_patient_columns(path):
            matches.append(path)
    return sorted(matches, key=lambda p: os.path.getmtime(p), reverse=True)


def select_patient_csv(facility_name=None):
    """
    Pick the patient CSV for the configured facility from patient_lists/.
    Only files in patient_lists/ are considered.
    """
    candidates = discover_patient_csvs()
    if not candidates:
        return None, []

    facility = (facility_name or '').strip()
    if not facility:
        return None, candidates

    matched = [path for path in candidates if filename_matches_facility(facility, path)]
    if not matched:
        return None, candidates

    if len(matched) == 1:
        return matched[0], candidates

    matched.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return matched[0], candidates

# Patient subfolders in display/process serial order (numeric prefix keeps name-sort order)
PATIENT_SUBFOLDERS = [
    '01_Patient_Details',
    '02_Patient_Images',
    '03_Appointment_History',
    '04_Service_History',
    '05_Encounter_History',
    '06_Consent_Form_History',
    '07_Patient_Invoices',
    '08_Membership_Invoices',
    '09_Available_Credits',
    '10_SMS_Log_History',
]
FOLDER_DETAILS = PATIENT_SUBFOLDERS[0]
FOLDER_IMAGES = PATIENT_SUBFOLDERS[1]
FOLDER_APPOINTMENTS = PATIENT_SUBFOLDERS[2]
FOLDER_SERVICES = PATIENT_SUBFOLDERS[3]
FOLDER_ENCOUNTERS = PATIENT_SUBFOLDERS[4]
FOLDER_CONSENTS = PATIENT_SUBFOLDERS[5]
FOLDER_INVOICES = PATIENT_SUBFOLDERS[6]
FOLDER_MEMBERSHIP = PATIENT_SUBFOLDERS[7]
FOLDER_CREDITS = PATIENT_SUBFOLDERS[8]
FOLDER_SMS = PATIENT_SUBFOLDERS[9]

def load_yaml(path):
    with open(path, 'r') as f:
        return yaml.safe_load(f)

def load_patient_ids(csv_path):
    """Load patient IDs from CSV file."""
    patient_ids = []
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            patient_id = row.get('id', '').strip()
            if patient_id:
                patient_ids.append(patient_id)
    return patient_ids

def to_pascalcase(text):
    """Convert text to Title Case (capitalize first letter of each word)."""
    return ' '.join(word.capitalize() for word in text.split())

def patient_already_processed(patient_folder_path):
    """True only when all 10 export categories are marked done / done_empty."""
    return is_patient_export_complete(patient_folder_path)

def count_files_in_folder(folder_path):
    """Count downloaded content files (ignores resume ledger / hidden files)."""
    return count_content_files(folder_path)

def rename_files_in_folder(folder_path, patient_name, document_type):
    """
    Rename files in a folder based on document type.
    
    Format conventions:
    - Encounter: 'ProcedureName_PatientName_MM-DD-YYYY_#.pdf'
      Example: 'Dermal Fillers_QA Tamzida_04-30-2026_1.pdf'
    - Consent: 'ConsentFormName_PatientName_MM-DD-YYYY_#.pdf'
      Example: 'Dermal Fillers_Mushfiq Rahman_01-20-2024_1.pdf'
    - Invoice: 'Invoice_PatientName_MM-DD-YYYY.pdf'
      Example: 'Invoice_Mushfiq Rahman_01-25-2024.pdf'
    - Image: 'FILENAME_PatientName_MM-DD-YYYY_#.{ext}'
      Example: 'patient_photo_Vip Patient_04-30-2026_1.jpg', 'scan_Vip Patient_04-30-2026_2.png'
    - Membership Invoice: 'MembershipInvoice_PatientName_MM-DD-YYYY.pdf'
      Example: 'MembershipInvoice_John Doe_04-30-2026.pdf'
    """
    if not os.path.exists(folder_path):
        return
    
    try:
        import re
        from datetime import datetime
        
        files = [
            f for f in os.listdir(folder_path)
            if os.path.isfile(os.path.join(folder_path, f))
            and not f.startswith('.')
            and f != LEDGER_FILENAME
        ]
        
        for filename in files:
            # Already renamed in a prior run — leave as-is (crash-safe resume)
            if f"_{patient_name}_" in filename:
                continue

            # Extract file extension
            file_extension = os.path.splitext(filename)[1]
            
            # Try to extract document name and date from original filename
            name_without_ext = os.path.splitext(filename)[0]
            
            # Try to find a date pattern (YYYY-MM-DD or MM-DD-YYYY or other formats)
            date_match = re.search(r'\d{4}-\d{2}-\d{2}|\d{2}-\d{2}-\d{4}|\d{1,2}/\d{1,2}/\d{4}', name_without_ext)
            
            if date_match:
                # Date found - extract and convert to MM-DD-YYYY format
                date_str_raw = date_match.group()
                try:
                    # Try parsing YYYY-MM-DD format
                    if len(date_str_raw.split('-')[0]) == 4:
                        date_obj = datetime.strptime(date_str_raw, '%Y-%m-%d')
                    # Try parsing MM-DD-YYYY format
                    elif len(date_str_raw.split('-')[2]) == 4:
                        date_obj = datetime.strptime(date_str_raw, '%m-%d-%Y')
                    # Try parsing slash format MM/DD/YYYY
                    else:
                        date_obj = datetime.strptime(date_str_raw, '%m/%d/%Y')
                    date_str = date_obj.strftime('%m-%d-%Y')
                except Exception:
                    # If parsing fails, use current date
                    date_str = datetime.now().strftime('%m-%d-%Y')
                
                # Remove date from the name to get document name
                document_name = name_without_ext.replace(date_str_raw, '').strip('_- /')
                # Clean up the document name (replace underscores/slashes/time patterns with spaces)
                document_name = re.sub(r'_|\s+-\s+\d+:\d+\s*[ap]m', ' ', document_name, flags=re.IGNORECASE)
                document_name = document_name.replace('/', ' ').strip()
            else:
                # No date found - use current date
                date_str = datetime.now().strftime('%m-%d-%Y')
                # Use the filename without extension as document name
                document_name = re.sub(r'_|\s+-\s+\d+:\d+\s*[ap]m', ' ', name_without_ext, flags=re.IGNORECASE)
                document_name = document_name.replace('/', ' ').strip()
            
            # Format filename based on document type
            if document_type == 'Invoice':
                # Format: Invoice_PatientName_MM-DD-YYYY.extension
                new_filename = f"Invoice_{patient_name}_{date_str}{file_extension}"
            elif document_type == 'Consent':
                # Format: ConsentFormName_PatientName_MM-DD-YYYY_#.extension
                # Extract procedure name from parentheses if present
                consent_name = document_name
                
                # Look for procedure name in parentheses - improved regex
                procedure_match = re.search(r'\(([^)]+)\)', document_name)
                if procedure_match:
                    consent_name = procedure_match.group(1).strip()
                    print(f"  Extracted procedure from parentheses: '{consent_name}'")
                else:
                    # Clean up the document name - remove patient name prefix and time stamps
                    # Remove patient name from the beginning if present
                    patient_name_variants = [
                        patient_name,
                        patient_name.replace(' ', '_'),
                        patient_name.replace(' ', '').lower(),
                        patient_name.lower()
                    ]
                    
                    for variant in patient_name_variants:
                        if consent_name.lower().startswith(variant.lower()):
                            consent_name = consent_name[len(variant):].strip('_- ')
                            break
                    
                    # Remove common patterns like " - 6 01 am" or similar timestamps
                    consent_name = re.sub(r'\s*-\s*\d+\s+\d+\s+[ap]m.*$', '', consent_name, flags=re.IGNORECASE)
                    
                    # If nothing meaningful remains, use "Consent Form"
                    if not consent_name.strip():
                        consent_name = "Consent Form"
                    
                    print(f"  Cleaned consent name: '{consent_name}'")
                
                # Create base filename without sequence number
                base_filename = f"{consent_name}_{patient_name}_{date_str}"
                new_filename = f"{base_filename}{file_extension}"
                
                # Handle multiple consent forms with same date by adding sequence numbers
                final_path = os.path.join(folder_path, new_filename)
                if os.path.exists(final_path):
                    counter = 1
                    while True:
                        sequenced_filename = f"{base_filename}_{counter}{file_extension}"
                        final_path = os.path.join(folder_path, sequenced_filename)
                        if not os.path.exists(final_path):
                            new_filename = sequenced_filename
                            break
                        counter += 1
            elif document_type == 'Image':
                # Format: FILENAME_PatientName_MM-DD-YYYY_#.extension
                # Use the original filename (without extension) as the identifier
                # Clean up the document name and use it directly
                if document_name.strip():
                    # Remove common prefixes like "Image", "Photo", "IMG" etc.
                    clean_name = document_name
                    for prefix in ['Image_', 'Photo_', 'IMG_', 'image_', 'photo_', 'img_']:
                        if clean_name.startswith(prefix):
                            clean_name = clean_name[len(prefix):]
                    # If still has content, use it; otherwise use original
                    filename_base = clean_name if clean_name.strip() else document_name
                else:
                    # Use original filename without extension
                    filename_base = os.path.splitext(filename)[0]
                
                # Create base filename without sequence number
                base_filename = f"{filename_base}_{patient_name}_{date_str}"
                new_filename = f"{base_filename}{file_extension}"
                
                # Handle multiple files with same date by adding sequence numbers
                final_path = os.path.join(folder_path, new_filename)
                if os.path.exists(final_path):
                    counter = 1
                    while True:
                        sequenced_filename = f"{base_filename}_{counter}{file_extension}"
                        final_path = os.path.join(folder_path, sequenced_filename)
                        if not os.path.exists(final_path):
                            new_filename = sequenced_filename
                            break
                        counter += 1
            elif document_type == 'Membership Invoice':
                # Format: MembershipInvoice_PatientName_MM-DD-YYYY.extension
                new_filename = f"MembershipInvoice_{patient_name}_{date_str}{file_extension}"
            else:  # Encounter or other types
                # Format: ProcedureName_PatientName_MM-DD-YYYY_#.extension
                # Extract procedure name from parentheses if present
                encounter_name = document_name
                
                # Look for procedure name in parentheses - improved regex
                procedure_match = re.search(r'\(([^)]+)\)', document_name)
                if procedure_match:
                    encounter_name = procedure_match.group(1).strip()
                    print(f"  Extracted procedure from parentheses: '{encounter_name}'")
                else:
                    # Clean up the document name - remove patient name prefix and time stamps
                    # Remove patient name from the beginning if present
                    patient_name_variants = [
                        patient_name,
                        patient_name.replace(' ', '_'),
                        patient_name.replace(' ', '').lower(),
                        patient_name.lower()
                    ]
                    
                    for variant in patient_name_variants:
                        if encounter_name.lower().startswith(variant.lower()):
                            encounter_name = encounter_name[len(variant):].strip('_- ')
                            break
                    
                    # Remove common patterns like " - 6 01 am" or similar timestamps
                    encounter_name = re.sub(r'\s*-\s*\d+\s+\d+\s+[ap]m.*$', '', encounter_name, flags=re.IGNORECASE)
                    
                    # Remove other timestamp patterns
                    encounter_name = re.sub(r'\s*-\s*\d{1,2}:\d{2}\s*[ap]m.*$', '', encounter_name, flags=re.IGNORECASE)
                    
                    # If nothing meaningful remains, use "Encounter"
                    if not encounter_name.strip():
                        encounter_name = "Encounter"
                    
                    print(f"  Cleaned encounter name: '{encounter_name}'")
                
                # Create base filename without sequence number
                base_filename = f"{encounter_name}_{patient_name}_{date_str}"
                new_filename = f"{base_filename}{file_extension}"
                
                # Handle multiple encounters with same date by adding sequence numbers
                final_path = os.path.join(folder_path, new_filename)
                if os.path.exists(final_path):
                    counter = 1
                    while True:
                        sequenced_filename = f"{base_filename}_{counter}{file_extension}"
                        final_path = os.path.join(folder_path, sequenced_filename)
                        if not os.path.exists(final_path):
                            new_filename = sequenced_filename
                            break
                        counter += 1
            
            # Full paths
            old_path = os.path.join(folder_path, filename)
            new_path = os.path.join(folder_path, new_filename)
            
            # Check if target filename already exists and add counter if needed
            if os.path.exists(new_path) and old_path != new_path:
                # Extract base name and extension
                base_name = os.path.splitext(new_filename)[0]
                ext = os.path.splitext(new_filename)[1]
                
                # Find next available number
                counter = 1
                while os.path.exists(os.path.join(folder_path, f"{base_name}_{counter}{ext}")):
                    counter += 1
                
                new_filename = f"{base_name}_{counter}{ext}"
                new_path = os.path.join(folder_path, new_filename)
            
            try:
                os.rename(old_path, new_path)
                try:
                    print(f"  Renamed: {filename} -> {new_filename}")
                except Exception:
                    pass
            except Exception as e:
                try:
                    print(f"Warning: Could not rename {filename} to {new_filename}: {e}")
                except Exception:
                    print(f"Warning: Could not rename a file in {folder_path}")
    except Exception as e:
        print(f"Warning: Error renaming files in {folder_path}: {e}")

async def check_if_new_records_pending(page, patient_id, patient_folder_path):
    """
    Check if there are new records pending to be downloaded.
    This function checks the system for updated record counts and compares with local downloads.
    """
    try:
        # Get current counts from the system for this patient
        encounter_count_system = await get_encounter_count_from_system(page, patient_id)
        invoice_count_system = await get_invoice_count_from_system(page, patient_id)
        consent_count_system = await get_consent_count_from_system(page, patient_id)
        
        # Get local downloaded counts
        encounter_path = os.path.join(patient_folder_path, FOLDER_ENCOUNTERS)
        invoice_path = os.path.join(patient_folder_path, FOLDER_INVOICES)
        
        encounter_count_local = count_files_in_folder(encounter_path)
        invoice_count_local = count_files_in_folder(invoice_path)
        
        consent_count_local = count_files_in_folder(os.path.join(patient_folder_path, FOLDER_CONSENTS))
        
        # Check if counts match
        if (encounter_count_local < encounter_count_system or 
            invoice_count_local < invoice_count_system or 
            consent_count_local < consent_count_system):
            return True  # New records pending
        
        return False  # All records are up to date
        
    except Exception as e:
        print(f"Warning: Could not check for new records: {e}. Re-downloading to be safe.")
        return True  # If we can't verify, re-download to be safe

async def get_encounter_count_from_system(page, patient_id):
    """Get the total count of encounters for a patient from the system."""
    # This should be implemented based on your system's UI/API
    # For now, returning a placeholder that you need to implement
    # You'll need to navigate to the encounters section and extract the count
    try:
        # Example: await page.goto(f'...encounters page for patient {patient_id}...')
        # count = await page.text_content('...count element selector...')
        # return int(count) or 0
        return 0
    except Exception:
        return 0

async def get_invoice_count_from_system(page, patient_id):
    """Get the total count of invoices for a patient from the system."""
    # This should be implemented based on your system's UI/API
    try:
        # Example: await page.goto(f'...invoices page for patient {patient_id}...')
        # count = await page.text_content('...count element selector...')
        # return int(count) or 0
        return 0
    except Exception:
        return 0

async def get_consent_count_from_system(page, patient_id):
    """Get the total count of consent forms for a patient from the system."""
    # This should be implemented based on your system's UI/API
    try:
        # Example: await page.goto(f'...consent page for patient {patient_id}...')
        # count = await page.text_content('...count element selector...')
        # return int(count) or 0
        return 0
    except Exception:
        return 0

def load_patient_data(csv_path):
    """Load patient data from CSV file."""
    patient_data = []
    with open(csv_path, 'r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            patient_id = (row.get('id') or '').strip()
            first_name = (row.get('first_name') or '').strip()
            last_name = (row.get('last_name') or '').strip()
            if patient_id and first_name and last_name:
                patient_data.append({
                    'id': patient_id,
                    'first_name': first_name,
                    'last_name': last_name,
                    # Optional contact fields for client delivery report / search
                    'email': (row.get('email') or '').strip(),
                    'work_phone': (row.get('work_phone') or '').strip(),
                    'home_phone': (row.get('home_phone') or '').strip(),
                    'cell_phone': (
                        (row.get('cell_phone') or row.get('work_phone') or '').strip()
                    ),
                })
    return patient_data


def shard_patients(patients, worker_count):
    """Split patients into contiguous shards for parallel workers."""
    worker_count = max(1, int(worker_count))
    n = len(patients)
    if n == 0:
        return []
    size = (n + worker_count - 1) // worker_count
    shards = []
    for i in range(worker_count):
        chunk = patients[i * size:(i + 1) * size]
        if chunk:
            shards.append(chunk)
    return shards


def expected_patient_folder(base_downloads_path, patient):
    """Folder path this run would create for a patient row."""
    first = to_pascalcase(patient['first_name'])
    last = to_pascalcase(patient['last_name'])
    return os.path.join(
        base_downloads_path, f"{patient['id']}_{first}_{last}"
    )


def index_patient_folders_by_id(base_downloads_path):
    """Map patient_id -> existing download folder (first match for that id)."""
    index = {}
    if not os.path.isdir(base_downloads_path):
        return index
    for name in os.listdir(base_downloads_path):
        path = os.path.join(base_downloads_path, name)
        if not os.path.isdir(path):
            continue
        pid = name.split('_', 1)[0]
        if pid.isdigit() and pid not in index:
            index[pid] = path
    return index


def partition_patients_by_progress(patients, base_downloads_path):
    """
    Split into incomplete (folder exists, not all 10 cats done),
    not_started (no folder yet), and complete (all 10 cats done).
    Incomplete must be finished before any not_started work.
    """
    folders_by_id = index_patient_folders_by_id(base_downloads_path)
    incomplete = []
    not_started = []
    complete = []
    for patient in patients:
        pid = str(patient['id']).strip()
        folder = folders_by_id.get(pid) or expected_patient_folder(
            base_downloads_path, patient
        )
        if is_patient_export_complete(folder):
            complete.append(patient)
        elif os.path.isdir(folder):
            incomplete.append(patient)
        else:
            not_started.append(patient)
    return incomplete, not_started, complete


async def run_worker_pool(
    patients, worker_count, credentials, settings, base_downloads_path,
    per_page, log, list_total, position_base, phase_label,
):
    """Shard patients and run workers; returns merged outcome counts/rows."""
    empty = {
        'processed': 0,
        'skipped': 0,
        'files_downloaded': 0,
        'report_rows': [],
    }
    if not patients:
        return empty

    shards = shard_patients(patients, worker_count)
    log.section(phase_label)
    log.info(f"Patients in this phase: {len(patients)}")
    log.info(f"Workers: {len(shards)}")
    for i, shard in enumerate(shards):
        log.info(
            f"  Worker {i + 1}: {len(shard)} patients "
            f"({shard[0]['id']} … {shard[-1]['id']})"
        )

    position_offsets = []
    offset = position_base
    for shard in shards:
        position_offsets.append(offset)
        offset += len(shard)

    outcomes = await asyncio.gather(*[
        worker(
            i + 1,
            shard,
            credentials,
            settings,
            base_downloads_path,
            per_page,
            log,
            list_total,
            position_offsets[i],
        )
        for i, shard in enumerate(shards)
    ], return_exceptions=True)

    merged = {
        'processed': 0,
        'skipped': 0,
        'files_downloaded': 0,
        'report_rows': [],
    }
    for i, outcome in enumerate(outcomes):
        if isinstance(outcome, Exception):
            log.error(f"Worker {i + 1} crashed: {outcome}")
            continue
        merged['processed'] += outcome['processed']
        merged['skipped'] += outcome['skipped']
        merged['files_downloaded'] += outcome['files_downloaded']
        merged['report_rows'].extend(outcome['report_rows'])
    return merged


def _failed_report_row(patient_id, full_name):
    return {
        'patient_id': patient_id,
        'patient_name': full_name,
        'status': 'Failed',
        'patient_details': 0,
        'encounters': 0,
        'consent_forms': 0,
        'invoices': 0,
        'images': 0,
        'membership_invoices': 0,
        'appointment_history': 0,
        'available_credits': 0,
        'service_history': 0,
        'sms_log': 0,
        'total_files': 0,
    }


async def process_one_patient(
    page, patient, base_downloads_path, per_page, log,
    list_position, list_total, worker_id,
):
    """
    Export all document types for one patient.
    Returns (report_row | None, files_added, skipped).
    report_row is None when patient was skipped as already complete.
    Resumes incomplete patients; skips categories already marked done in .export_status.json.
    """
    patient_id = patient['id']
    first_name = patient['first_name']
    last_name = patient['last_name']

    first_name_pascal = to_pascalcase(first_name)
    last_name_pascal = to_pascalcase(last_name)
    full_name = f"{first_name_pascal} {last_name_pascal}"

    folder_name = f"{patient_id}_{first_name_pascal}_{last_name_pascal}"
    patient_folder_path = os.path.join(base_downloads_path, folder_name)
    # Prefer an existing download folder for this id (crash / naming drift)
    if not os.path.isdir(patient_folder_path) and os.path.isdir(base_downloads_path):
        prefix = f"{patient_id}_"
        for name in os.listdir(base_downloads_path):
            if name.startswith(prefix):
                candidate = os.path.join(base_downloads_path, name)
                if os.path.isdir(candidate):
                    patient_folder_path = candidate
                    break

    log.patient_start(
        patient_id, first_name, last_name, list_position, list_total, worker_id=worker_id
    )

    if patient_already_processed(patient_folder_path):
        has_new_records = await check_if_new_records_pending(
            page, patient_id, patient_folder_path
        )
        if not has_new_records:
            log.patient_skipped(patient_id, first_name, last_name, worker_id=worker_id)
            return None, 0, True
        log.warning(f"[W{worker_id}] Patient has new records - re-downloading")
    elif os.path.exists(patient_folder_path):
        log.info(
            f"[W{worker_id}] Resuming incomplete patient {patient_id} — "
            f"done categories skipped; partial folders continue via ledger"
        )

    details_count = images_count = appointment_count = service_count = 0
    encounter_count = consent_count = invoice_count = membership_count = 0
    credits_count = sms_count = 0

    try:
        for subfolder in PATIENT_SUBFOLDERS:
            os.makedirs(os.path.join(patient_folder_path, subfolder), exist_ok=True)

        # 1) Patient details
        if is_category_done(patient_folder_path, CATEGORY_DETAILS):
            details_count = count_files_in_folder(
                os.path.join(patient_folder_path, FOLDER_DETAILS)
            )
            log.info(f"  [W{worker_id}] Skipping Patient Details (already done)")
        else:
            log.patient_download_start('Patient Details', full_name)
            details_count = await download_patient_details(
                page,
                os.path.join(patient_folder_path, FOLDER_DETAILS),
                patient_id=patient_id,
                patient_name=full_name,
            )
            log.patient_download_complete('Patient Details', details_count, full_name)
            if details_count > 0:
                mark_category(patient_folder_path, CATEGORY_DETAILS, file_count=details_count)
            else:
                mark_category(patient_folder_path, CATEGORY_DETAILS, failed=True, label="failed")

        # 2) Images
        images_download_path = os.path.join(patient_folder_path, FOLDER_IMAGES)
        if is_category_done(patient_folder_path, CATEGORY_IMAGES):
            images_count = count_files_in_folder(images_download_path)
            log.info(f"  [W{worker_id}] Skipping Images (already done)")
        else:
            log.patient_download_start('Image', full_name)
            await download_patient_images(
                page, images_download_path,
                patient_id=patient_id, per_page=per_page, patient_name=full_name,
            )
            rename_files_in_folder(images_download_path, full_name, 'Image')
            images_count = count_files_in_folder(images_download_path)
            log.patient_download_complete('Image', images_count, full_name)
            mark_category(
                patient_folder_path, CATEGORY_IMAGES,
                file_count=images_count, empty_ok=(images_count == 0),
            )

        # 3) Appointments
        if is_category_done(patient_folder_path, CATEGORY_APPOINTMENTS):
            appointment_count = count_files_in_folder(
                os.path.join(patient_folder_path, FOLDER_APPOINTMENTS)
            )
            log.info(f"  [W{worker_id}] Skipping Appointments (already done)")
        else:
            log.patient_download_start('Appointment History', full_name)
            appointment_count = await download_appointment_history(
                page,
                os.path.join(patient_folder_path, FOLDER_APPOINTMENTS),
                patient_id=patient_id,
                patient_name=full_name,
            )
            log.patient_download_complete('Appointment History', appointment_count, full_name)
            mark_category(
                patient_folder_path, CATEGORY_APPOINTMENTS,
                file_count=appointment_count, empty_ok=(appointment_count == 0),
            )

        # 4) Services
        if is_category_done(patient_folder_path, CATEGORY_SERVICES):
            service_count = count_files_in_folder(
                os.path.join(patient_folder_path, FOLDER_SERVICES)
            )
            log.info(f"  [W{worker_id}] Skipping Services (already done)")
        else:
            log.patient_download_start('Service History', full_name)
            service_count = await download_service_history(
                page,
                os.path.join(patient_folder_path, FOLDER_SERVICES),
                patient_id=patient_id,
                patient_name=full_name,
            )
            log.patient_download_complete('Service History', service_count, full_name)
            if service_count > 0:
                mark_category(patient_folder_path, CATEGORY_SERVICES, file_count=service_count)
            else:
                mark_category(patient_folder_path, CATEGORY_SERVICES, failed=True, label="failed")

        # 5) Encounters
        encounter_path = os.path.join(patient_folder_path, FOLDER_ENCOUNTERS)
        if is_category_done(patient_folder_path, CATEGORY_ENCOUNTERS):
            encounter_count = count_files_in_folder(encounter_path)
            log.info(f"  [W{worker_id}] Skipping Encounters (already done)")
        else:
            log.patient_download_start('Encounter', full_name)
            await download_encounter_documents(
                page, encounter_path, patient_id=patient_id, per_page=per_page
            )
            rename_files_in_folder(encounter_path, full_name, 'Encounter')
            encounter_count = count_files_in_folder(encounter_path)
            log.patient_download_complete('Encounter', encounter_count, full_name)
            mark_category(
                patient_folder_path, CATEGORY_ENCOUNTERS,
                file_count=encounter_count, empty_ok=(encounter_count == 0),
            )

        # 6) Consents
        consent_path = os.path.join(patient_folder_path, FOLDER_CONSENTS)
        if is_category_done(patient_folder_path, CATEGORY_CONSENTS):
            consent_count = count_files_in_folder(consent_path)
            log.info(f"  [W{worker_id}] Skipping Consents (already done)")
        else:
            log.patient_download_start('Consent', full_name)
            await download_consent_documents(
                page, consent_path, patient_id=patient_id, per_page=per_page
            )
            rename_files_in_folder(consent_path, full_name, 'Consent')
            consent_count = count_files_in_folder(consent_path)
            log.patient_download_complete('Consent', consent_count, full_name)
            mark_category(
                patient_folder_path, CATEGORY_CONSENTS,
                file_count=consent_count, empty_ok=(consent_count == 0),
            )

        # 7) Invoices
        invoice_path = os.path.join(patient_folder_path, FOLDER_INVOICES)
        if is_category_done(patient_folder_path, CATEGORY_INVOICES):
            invoice_count = count_files_in_folder(invoice_path)
            log.info(f"  [W{worker_id}] Skipping Invoices (already done)")
        else:
            log.patient_download_start('Invoice', full_name)
            await download_invoice_documents(
                page, invoice_path, patient_id=patient_id, per_page=per_page
            )
            rename_files_in_folder(invoice_path, full_name, 'Invoice')
            invoice_count = count_files_in_folder(invoice_path)
            log.patient_download_complete('Invoice', invoice_count, full_name)
            mark_category(
                patient_folder_path, CATEGORY_INVOICES,
                file_count=invoice_count, empty_ok=(invoice_count == 0),
            )

        # 8) Membership
        membership_path = os.path.join(patient_folder_path, FOLDER_MEMBERSHIP)
        if is_category_done(patient_folder_path, CATEGORY_MEMBERSHIP):
            membership_count = count_files_in_folder(membership_path)
            log.info(f"  [W{worker_id}] Skipping Membership (already done)")
        else:
            log.patient_download_start('Membership Invoice', full_name)
            await download_membership_invoices(
                page, membership_path, patient_id=patient_id, per_page=per_page
            )
            rename_files_in_folder(membership_path, full_name, 'Membership Invoice')
            membership_count = count_files_in_folder(membership_path)
            log.patient_download_complete('Membership Invoice', membership_count, full_name)
            mark_category(
                patient_folder_path, CATEGORY_MEMBERSHIP,
                file_count=membership_count, empty_ok=(membership_count == 0),
            )

        # 9) Credits
        if is_category_done(patient_folder_path, CATEGORY_CREDITS):
            credits_count = count_files_in_folder(
                os.path.join(patient_folder_path, FOLDER_CREDITS)
            )
            log.info(f"  [W{worker_id}] Skipping Credits (already done)")
        else:
            log.patient_download_start('Available Credits', full_name)
            credits_count = await download_all_credits(
                page,
                os.path.join(patient_folder_path, FOLDER_CREDITS),
                patient_id=patient_id,
                patient_name=full_name,
            )
            log.patient_download_complete('Available Credits', credits_count, full_name)
            if credits_count > 0:
                mark_category(patient_folder_path, CATEGORY_CREDITS, file_count=credits_count)
            else:
                mark_category(patient_folder_path, CATEGORY_CREDITS, failed=True, label="failed")

        # 10) SMS
        if is_category_done(patient_folder_path, CATEGORY_SMS):
            sms_count = count_files_in_folder(
                os.path.join(patient_folder_path, FOLDER_SMS)
            )
            log.info(f"  [W{worker_id}] Skipping SMS (already done)")
        else:
            log.patient_download_start('SMS Log', full_name)
            sms_count = await download_sms_log(
                page,
                os.path.join(patient_folder_path, FOLDER_SMS),
                patient_id=patient_id,
                patient_name=full_name,
            )
            log.patient_download_complete('SMS Log', sms_count, full_name)
            if sms_count > 0:
                mark_category(patient_folder_path, CATEGORY_SMS, file_count=sms_count)
            else:
                mark_category(patient_folder_path, CATEGORY_SMS, failed=True, label="failed")

        log.patient_complete(patient_id, first_name, last_name, worker_id=worker_id)

        total_files = (
            details_count + encounter_count + consent_count + invoice_count
            + images_count + membership_count + appointment_count
            + credits_count + service_count + sms_count
        )
        export_complete = patient_already_processed(patient_folder_path)
        report_row = {
            'patient_id': patient_id,
            'patient_name': full_name,
            'status': 'Completed' if export_complete else 'Partial',
            'patient_details': details_count,
            'encounters': encounter_count,
            'consent_forms': consent_count,
            'invoices': invoice_count,
            'images': images_count,
            'membership_invoices': membership_count,
            'appointment_history': appointment_count,
            'available_credits': credits_count,
            'service_history': service_count,
            'sms_log': sms_count,
            'total_files': total_files,
        }
        return report_row, total_files, False

    except Exception as e:
        log.error(
            f"[W{worker_id}] Failed to process patient {patient_id} "
            f"({first_name} {last_name}): {e}"
        )
        return _failed_report_row(patient_id, full_name), 0, False


async def worker(
    worker_id, patients, credentials, settings, base_downloads_path,
    per_page, log, list_total, position_offset,
):
    """
    One browser session processing a contiguous patient shard.
    Returns dict with report rows and counts.
    """
    stagger = int(settings.get('worker_login_stagger_sec', 3) or 0) * (worker_id - 1)
    if stagger:
        log.info(f"[W{worker_id}] Waiting {stagger}s before login (stagger)")
        await asyncio.sleep(stagger)

    first_id = patients[0]['id']
    last_id = patients[-1]['id']
    log.info(
        f"[W{worker_id}] Authenticating — {len(patients)} patients "
        f"({first_id} … {last_id})"
    )
    playwright, browser, context, page = await authenticate_and_select_facility(
        credentials, settings
    )
    log.success(f"[W{worker_id}] Authentication successful")

    report_rows = []
    files_downloaded = 0
    skipped = 0
    processed = 0
    recycle_every = int(settings.get('recycle_browser_every_n_patients') or 0)

    try:
        for i, patient in enumerate(patients):
            list_position = position_offset + i + 1
            row, files_added, was_skipped = await process_one_patient(
                page, patient, base_downloads_path, per_page, log,
                list_position, list_total, worker_id,
            )
            if was_skipped:
                skipped += 1
                continue
            processed += 1
            files_downloaded += files_added
            if row:
                report_rows.append(row)

            # Periodic browser recycle to limit RAM growth on long overnight runs
            if (
                recycle_every > 0
                and processed > 0
                and processed % recycle_every == 0
                and i < len(patients) - 1
            ):
                log.info(
                    f"[W{worker_id}] Recycling browser after {processed} "
                    f"processed patient(s) (RAM hygiene)"
                )
                try:
                    await browser.close()
                except Exception:
                    pass
                try:
                    await playwright.stop()
                except Exception:
                    pass
                playwright, browser, context, page = await authenticate_and_select_facility(
                    credentials, settings
                )
                log.success(f"[W{worker_id}] Browser recycle — re-authenticated")
    finally:
        try:
            await browser.close()
        except Exception:
            pass
        try:
            await playwright.stop()
        except Exception:
            pass
        log.info(
            f"[W{worker_id}] Finished — processed={processed}, "
            f"skipped={skipped}, files={files_downloaded}"
        )

    return {
        'worker_id': worker_id,
        'report_rows': report_rows,
        'processed': processed,
        'skipped': skipped,
        'files_downloaded': files_downloaded,
    }


async def main():
    # Initialize logger
    log = init_logger(os.path.join(DOWNLOADS_ROOT, 'logs'))

    # Load credentials and settings first (facility used for CSV + output folder)
    credentials = load_yaml(os.path.join(CONFIG_PATH, 'credentials.yaml'))
    settings = load_yaml(os.path.join(CONFIG_PATH, 'settings.yaml'))
    facility_name = credentials.get('facility', 'Facility')

    os.makedirs(PATIENT_LISTS_DIR, exist_ok=True)

    csv_path, csv_candidates = select_patient_csv(facility_name)
    if not csv_path:
        if not csv_candidates:
            log.error(f"No patient list CSV found in: {PATIENT_LISTS_DIR}")
            log.info(
                "Add a CSV with columns id, first_name, last_name to patient_lists/. "
                "The filename should include the facility name from credentials.yaml."
            )
        else:
            log.error(
                f"No patient list CSV in patient_lists/ matches facility '{facility_name}'."
            )
            log.info(f"Found {len(csv_candidates)} CSV file(s) in patient_lists/:")
            for path in csv_candidates:
                log.info(f"  - {os.path.basename(path)}")
            log.info(
                "Rename or add a CSV whose filename includes the facility name "
                f"(e.g. '{facility_name}_Patients.csv')."
            )
        return

    if len(csv_candidates) > 1:
        log.info(f"Found {len(csv_candidates)} patient CSV file(s) in patient_lists/:")
        for path in csv_candidates:
            marker = "← selected" if os.path.abspath(path) == os.path.abspath(csv_path) else ""
            log.info(f"  - {os.path.basename(path)} {marker}".rstrip())
    else:
        log.info(f"Found patient list CSV in patient_lists/: {os.path.basename(csv_path)}")

    log.info(f"Starting export with patient list: {os.path.basename(csv_path)}")
    log.info(f"Full path: {csv_path}")

    patient_data = load_patient_data(csv_path)
    if not patient_data:
        log.error(f"No valid patient rows found in {os.path.basename(csv_path)}.")
        return

    facility_folder = sanitize_facility_folder_name(facility_name)
    base_downloads_path = os.path.join(DOWNLOADS_ROOT, facility_folder)
    os.makedirs(base_downloads_path, exist_ok=True)

    worker_count = max(1, int(settings.get('worker_count', 1) or 1))
    # Supervisor can override via EXPORT_WORKER_COUNT (adaptive 5→3→2)
    env_workers = (os.environ.get('EXPORT_WORKER_COUNT') or '').strip()
    if env_workers.isdigit():
        worker_count = max(1, int(env_workers))
        log.info(f"Worker count overridden by supervisor: {worker_count}")
    per_page = max(1, int(settings.get('per_page', 50) or 50))

    log.section("STARTING FACILITY DOCUMENT DOWNLOAD")
    log.info(f"Facility: {facility_name}")
    log.info(f"Output folder: {base_downloads_path}")
    log.info(f"Patients to process: {len(patient_data)}")
    log.info(f"Workers: {worker_count} | per_page: {per_page}")

    start_from_patient_id = str(settings.get('start_from_patient_id') or '').strip()
    if start_from_patient_id:
        match_indexes = [
            i for i, p in enumerate(patient_data)
            if str(p['id']).strip() == start_from_patient_id
        ]
        if not match_indexes:
            log.error(
                f"start_from_patient_id '{start_from_patient_id}' was not found in the patient list."
            )
            return
        start_index = match_indexes[0]
        start_patient = patient_data[start_index]
        log.info(
            f"Continuing from patient {start_from_patient_id} "
            f"({start_patient['first_name']} {start_patient['last_name']}) "
            f"at position {start_index + 1}/{len(patient_data)} "
            f"— skipping {start_index} earlier patient(s)"
        )
    else:
        start_index = 0

    remaining = patient_data[start_index:]
    incomplete, not_started, already_complete = partition_patients_by_progress(
        remaining, base_downloads_path
    )

    log.info(
        f"Progress split — incomplete (resume first): {len(incomplete)}, "
        f"not started: {len(not_started)}, "
        f"already complete (skip): {len(already_complete)}"
    )
    if incomplete:
        sample = ", ".join(p['id'] for p in incomplete[:15])
        more = "" if len(incomplete) <= 15 else f", … (+{len(incomplete) - 15} more)"
        log.info(f"Incomplete patient ids: {sample}{more}")

    processed_count = 0
    skipped_count = start_index + len(already_complete)
    total_files_downloaded = 0
    patients_report_data = []

    # Phase 1: finish every crash-interrupted / partial patient before any new ones
    phase1 = await run_worker_pool(
        incomplete,
        worker_count,
        credentials,
        settings,
        base_downloads_path,
        per_page,
        log,
        len(patient_data),
        start_index,
        "PHASE 1 — FINISH INCOMPLETE PATIENTS (all 10 folders) BEFORE NEW EXPORTS",
    )
    processed_count += phase1['processed']
    skipped_count += phase1['skipped']
    total_files_downloaded += phase1['files_downloaded']
    patients_report_data.extend(phase1['report_rows'])

    # Phase 2: only patients that never had a download folder
    phase2 = await run_worker_pool(
        not_started,
        worker_count,
        credentials,
        settings,
        base_downloads_path,
        per_page,
        log,
        len(patient_data),
        start_index + len(incomplete),
        "PHASE 2 — NEW PATIENTS (incomplete phase finished)",
    )
    processed_count += phase2['processed']
    skipped_count += phase2['skipped']
    total_files_downloaded += phase2['files_downloaded']
    patients_report_data.extend(phase2['report_rows'])

    log.summary(len(patient_data), processed_count, skipped_count, total_files_downloaded)

    # Generate HTML execution report
    log.info("Generating execution report...")
    reports_dir = os.path.join(DOWNLOADS_ROOT, 'reports')
    os.makedirs(reports_dir, exist_ok=True)

    facility_name_safe = sanitize_facility_folder_name(facility_name).replace(' ', '_')
    facility_name_safe = facility_name_safe.replace('(', '').replace(')', '')

    from datetime import datetime
    report_date = datetime.now().strftime('%m-%d-%Y')
    report_filename = f"{facility_name_safe}_Export_Report_{report_date}.html"

    report_data = {
        'facility_name': facility_name,
        'total_patients': len(patient_data),
        'processed_patients': processed_count,
        'skipped_patients': skipped_count,
        'total_files_downloaded': total_files_downloaded,
        'patients': patients_report_data,
    }

    report_path = generate_execution_report(report_data, reports_dir, report_filename)
    log.success(f"Report generated: {report_path}")

    log.info("Generating facility progress report (all patients in CSV)...")
    facility_safe = sanitize_facility_folder_name(facility_name).replace(' ', '_')
    facility_safe = facility_safe.replace('(', '').replace(')', '')
    progress_filename = f"{facility_safe}_Export_Progress_{report_date}.html"
    progress_path = generate_progress_report(
        facility_name=facility_name,
        patient_data=patient_data,
        base_downloads_path=base_downloads_path,
        output_dir=reports_dir,
        to_pascalcase=to_pascalcase,
        custom_filename=progress_filename,
    )
    log.success(f"Progress report generated: {progress_path}")

    log.info("Generating client-facing delivery report...")
    client_filename = f"{facility_safe}_Client_Delivery_Report_{report_date}.html"
    client_path = generate_client_delivery_report(
        facility_name=facility_name,
        patient_data=patient_data,
        base_downloads_path=base_downloads_path,
        output_dir=reports_dir,
        to_pascalcase=to_pascalcase,
        custom_filename=client_filename,
    )
    log.success(f"Client delivery report generated: {client_path}")

if __name__ == "__main__":
    asyncio.run(main())
