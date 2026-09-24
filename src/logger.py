# Clean logging utility for readable terminal output

import os
import sys
import threading
from datetime import datetime


def _safe_print(message):
    """Print safely on Windows consoles that are not UTF-8."""
    try:
        print(message)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "ascii"
        print(message.encode(encoding, errors="replace").decode(encoding, errors="replace"))


class EMRLogger:
    """Handles clean, readable logging for EMR script execution."""
    
    def __init__(self, log_dir="downloads/logs"):
        self.log_dir = log_dir
        self._lock = threading.Lock()
        os.makedirs(log_dir, exist_ok=True)
        
        # Create log file with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.log_file = os.path.join(log_dir, f"execution_{timestamp}.log")
        
        # Write header to log file
        with open(self.log_file, 'w', encoding='utf-8') as f:
            f.write(f"{'='*80}\n")
            f.write(f"Facility Document Downloader - Execution Log\n")
            f.write(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'='*80}\n\n")
    
    def log(self, message, level="INFO"):
        """Log message to both console and file (safe for concurrent workers)."""
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_message = f"[{timestamp}] {message}"
        
        with self._lock:
            _safe_print(log_message)
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(log_message + "\n")
    
    def section(self, title):
        """Log a section header."""
        separator = "-" * 80
        self.log(f"\n{separator}")
        self.log(f"  {title}")
        self.log(f"{separator}")
    
    def success(self, message):
        """Log success message."""
        self.log(f"[OK] {message}")
    
    def info(self, message):
        """Log info message."""
        self.log(f"[INFO] {message}")
    
    def warning(self, message):
        """Log warning message."""
        self.log(f"[WARN] {message}")
    
    def error(self, message):
        """Log error message."""
        self.log(f"[ERROR] {message}")
    
    def patient_start(self, patient_id, first_name, last_name, current, total, worker_id=None):
        """Log patient processing start."""
        prefix = f"[W{worker_id}] " if worker_id is not None else ""
        self.log(f"\n{'-'*80}")
        self.log(f"{prefix}[{current}/{total}] Processing Patient: {patient_id} | {first_name} {last_name}")
        self.log(f"{'-'*80}")
    
    def patient_skipped(self, patient_id, first_name, last_name, worker_id=None):
        """Log patient being skipped."""
        prefix = f"[W{worker_id}] " if worker_id is not None else ""
        self.log(f"{prefix}[OK] SKIPPED - Patient {patient_id} ({first_name} {last_name}) already processed with all documents")
    
    def patient_download_start(self, doc_type, patient_name):
        """Log download start for a document type."""
        self.log(f"  Starting {doc_type} download for {patient_name}...")
    
    def patient_download_complete(self, doc_type, count, patient_name):
        """Log download completion for a document type."""
        self.log(f"  [OK] {doc_type}: Downloaded {count} file(s) for {patient_name}")
    
    def patient_download_failed(self, doc_type, patient_name, error):
        """Log download failure for a document type."""
        self.log(f"  [ERROR] {doc_type}: Failed for {patient_name} - {error}")
    
    def patient_complete(self, patient_id, first_name, last_name, worker_id=None):
        """Log patient processing complete."""
        prefix = f"[W{worker_id}] " if worker_id is not None else ""
        self.log(f"{prefix}[OK] COMPLETED - Patient {patient_id} ({first_name} {last_name}) all files processed")
    
    def summary(self, total, processed, skipped, total_files):
        """Log execution summary."""
        self.section("EXECUTION SUMMARY")
        self.log(f"Total Patients:      {total}")
        self.log(f"Processed:           {processed}")
        self.log(f"Skipped:             {skipped}")
        self.log(f"Total Files Downloaded: {total_files}")
        self.log(f"\nLog file: {self.log_file}")
        self.log(f"{'='*80}\n")

# Global logger instance
logger = None

def init_logger(log_dir="downloads/logs"):
    """Initialize global logger."""
    global logger
    logger = EMRLogger(log_dir)
    return logger

def get_logger():
    """Get global logger instance."""
    global logger
    if logger is None:
        logger = EMRLogger()
    return logger
