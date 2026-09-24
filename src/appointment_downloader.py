# Download logic for Appointment History export

import os
import re
import csv
import asyncio
import tempfile
import yaml
from html.parser import HTMLParser
from html import unescape
from appointment_selectors import EXPORT_BUTTON, EMPTY_TABLE_CELL, DATATABLES_INFO
from page_wait import goto_ready


def load_settings():
    """Load timeout from settings."""
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'settings.yaml')
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


class _HtmlTableParser(HTMLParser):
    """Extract headers and rows from the EMR HTML appointment export."""

    def __init__(self):
        super().__init__()
        self.headers = []
        self.rows = []
        self._in_th = False
        self._in_td = False
        self._current_row = None
        self._current_cell = []

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._current_row = []
        elif tag == "th":
            self._in_th = True
            self._current_cell = []
        elif tag == "td":
            self._in_td = True
            self._current_cell = []
        elif tag == "br" and (self._in_td or self._in_th):
            self._current_cell.append("; ")

    def handle_endtag(self, tag):
        if tag == "th":
            text = unescape("".join(self._current_cell)).strip()
            text = re.sub(r"\s+", " ", text)
            self.headers.append(text)
            self._in_th = False
        elif tag == "td":
            text = unescape("".join(self._current_cell)).strip()
            text = re.sub(r"\s+", " ", text)
            if self._current_row is not None:
                self._current_row.append(text)
            self._in_td = False
        elif tag == "tr":
            if self._current_row:
                self.rows.append(self._current_row)
            self._current_row = None

    def handle_data(self, data):
        if self._in_th or self._in_td:
            self._current_cell.append(data)


def html_export_to_csv_rows(html_content):
    """Convert EMR HTML table export into (headers, rows)."""
    if not html_content:
        return [], []

    cleaned = html_content
    cleaned = re.sub(r'width="[^"]*"\s*<tr>', 'width="60%"><tr>', cleaned, count=1, flags=re.I)
    cleaned = cleaned.replace("<tr><tr>", "<tr>")
    # EMR often emits broken attributes like: style=""text-align:center>
    cleaned = re.sub(r'\sstyle=""([^"=<>]*)>', r' style="\1">', cleaned, flags=re.I)
    cleaned = re.sub(r'\sstyle=""[^>]*>', '>', cleaned, flags=re.I)

    parser = _HtmlTableParser()
    try:
        parser.feed(cleaned)
        if parser.headers or parser.rows:
            return parser.headers, parser.rows
    except Exception:
        pass

    # Fallback regex if HTMLParser struggles with malformed markup
    headers = [
        re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", h))).strip()
        for h in re.findall(r"<th[^>]*>(.*?)</th>", cleaned, flags=re.I | re.S)
    ]
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", cleaned, flags=re.I | re.S):
        cells = []
        for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.I | re.S):
            c = re.sub(r"<br\s*/?>", "; ", c, flags=re.I)
            c = re.sub(r"<[^>]+>", "", c)
            c = re.sub(r"\s+", " ", unescape(c)).strip()
            cells.append(c)
        if cells:
            rows.append(cells)
    return headers, rows


def write_appointment_csv(save_path, headers, rows):
    """Write a real CSV file Excel can open without format warnings."""
    if not headers:
        headers = [
            "Patient",
            "Patient Email Address",
            "Cell Phone",
            "Home Phone",
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

    # Drop phone columns from the exported CSV
    drop_headers = {"cell phone", "home phone"}
    keep_indexes = [
        i for i, h in enumerate(headers)
        if (h or "").strip().lower() not in drop_headers
    ]
    filtered_headers = [headers[i] for i in keep_indexes]

    with open(save_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(filtered_headers)
        for row in rows:
            padded = list(row[: len(headers)]) + [""] * max(0, len(headers) - len(row))
            writer.writerow([padded[i] for i in keep_indexes])


async def _is_appointment_list_empty(page):
    """Return True when the appointment history page has no appointments."""
    empty_cell = await page.query_selector(EMPTY_TABLE_CELL)
    if empty_cell and await empty_cell.is_visible():
        return True

    info_el = await page.query_selector(DATATABLES_INFO)
    if info_el:
        info_text = (await info_el.inner_text() or '').lower()
        if '0 record' in info_text or 'out of 0 total' in info_text:
            return True

    rows = await page.query_selector_all('table tbody tr')
    if len(rows) == 0:
        return True

    return False


async def download_appointment_history(page, download_dir, patient_id, patient_name):
    """
    Download appointment export, convert EMR HTML/.xls payload to a real CSV,
    and save as Appointment_History_{PatientName}.csv.
    """
    settings = load_settings()
    page_timeout = settings.get('page_timeout', 60000)

    list_page_url = f"https://www.calystaproemr.com/appointments/appointment-list/{patient_id}"
    print(f"[APPOINTMENT] Navigating to: {list_page_url}")

    try:
        await goto_ready(
            page, list_page_url,
            f"{EXPORT_BUTTON}, {EMPTY_TABLE_CELL}, {DATATABLES_INFO}",
            timeout=page_timeout,
        )

        if await _is_appointment_list_empty(page):
            print(f"[APPOINTMENT] No appointments for patient {patient_id} — skipping")
            return 0

        export_btn = await page.query_selector(EXPORT_BUTTON)
        if not export_btn:
            print(f"[APPOINTMENT] Export button not found for patient {patient_id}")
            return 0

        async with page.expect_download(timeout=page_timeout) as download_info:
            await export_btn.click()

        download = await download_info.value

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = os.path.join(tmp_dir, download.suggested_filename or "appointment_export.xls")
            await download.save_as(tmp_path)
            with open(tmp_path, "r", encoding="utf-8", errors="replace") as f:
                html_content = f.read()

        headers, rows = html_export_to_csv_rows(html_content)
        if not rows and not headers:
            print(f"[APPOINTMENT] Could not parse appointment export for patient {patient_id}")
            return 0

        save_filename = f"Appointment_History_{patient_name}.csv"
        save_path = os.path.join(download_dir, save_filename)
        write_appointment_csv(save_path, headers, rows)

        # Remove leftover mismatched .xls from earlier runs if present
        legacy_xls = os.path.join(download_dir, f"Appointment_History_{patient_name}.xls")
        if os.path.exists(legacy_xls):
            try:
                os.remove(legacy_xls)
            except OSError:
                pass

        print(f"[APPOINTMENT] Wrote {save_filename} ({len(rows)} row(s))")
        return 1

    except Exception as e:
        print(f"[APPOINTMENT] Error downloading appointment history for {patient_id}: {e}")
        return 0
