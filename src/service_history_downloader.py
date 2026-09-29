# Scrape patient Service History table into Service_History_{PatientName}.csv

import os
import csv
import asyncio
import yaml
from service_history_selectors import (
    SERVICE_HISTORY_URL,
    SERVICE_HISTORY_COLUMNS,
    NEXT_BUTTON,
    DATATABLES_EMPTY,
)
from page_wait import goto_ready

# UI placeholders that mean "no real value"
BLANK_PLACEHOLDERS = {
    "",
    "-",
    "--",
    "---",
    "-----",
    "n/a",
    "na",
    "add received date",
}

SERVICE_PLACEHOLDER_NAME = "no data found for this patient"


def load_settings():
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "settings.yaml")
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def cell_or_na(value):
    """Return N/A for blank / placeholder cells."""
    text = (value or "").strip()
    text = " ".join(text.split())
    if text.lower() in BLANK_PLACEHOLDERS:
        return "N/A"
    return text if text else "N/A"


def is_placeholder_service_csv(path: str) -> bool:
    """True when the CSV is the legacy single-row 'no data found' placeholder."""
    if not os.path.isfile(path) or not path.lower().endswith(".csv"):
        return False
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
    except Exception:
        return False
    return (
        len(rows) == 1
        and (rows[0].get("Service Name") or "").strip().lower() == SERVICE_PLACEHOLDER_NAME
    )


async def _wait_for_service_table(page, timeout=30000):
    """Wait until the service table shows rows or a confirmed empty state."""
    try:
        await page.wait_for_function(
            """() => {
              for (const table of document.querySelectorAll('table')) {
                const ths = Array.from(table.querySelectorAll('thead th')).map(th =>
                  th.innerText.trim().toLowerCase()
                );
                if (!ths.includes('service name')) continue;

                const emptyCell = table.querySelector('td.dataTables_empty, .dataTables_empty');
                const bodyRows = Array.from(table.querySelectorAll('tbody tr')).filter(tr => {
                  if (tr.querySelector('.dataTables_empty, td.dataTables_empty')) return false;
                  return tr.querySelectorAll('td').length > 0;
                });
                if (bodyRows.length > 0) return true;
                if (emptyCell && emptyCell.innerText.trim()) return true;
              }
              return false;
            }""",
            timeout=timeout,
        )
    except Exception:
        pass


async def _extract_service_rows_current_page(page):
    """
    Extract selected columns from the services table on the current page.
    Returns list of dicts keyed by SERVICE_HISTORY_COLUMNS.
    """
    data = await page.evaluate(
        """({ wantedColumns }) => {
          const tables = Array.from(document.querySelectorAll('table'));
          for (const table of tables) {
            const ths = Array.from(table.querySelectorAll('thead th')).map(th =>
              th.innerText.trim().replace(/\\s+/g, ' ')
            );
            const hasService = ths.some(h => h.toLowerCase() === 'service name');
            if (!hasService) continue;

            const empty = table.querySelector('td.dataTables_empty, .dataTables_empty');
            if (empty) {
              return { empty: true, headers: ths, rows: [] };
            }

            const indexMap = {};
            // Page header is "Appointments"; CSV header is "Appointment Date"
            const headerAliases = {
              'Appointment Date': ['Appointment Date', 'Appointments'],
            };
            for (const col of wantedColumns) {
              const aliases = headerAliases[col] || [col];
              let idx = -1;
              for (const alias of aliases) {
                idx = ths.findIndex(h => h.toLowerCase() === alias.toLowerCase());
                if (idx >= 0) break;
              }
              indexMap[col] = idx;
            }

            const rows = [];
            for (const tr of table.querySelectorAll('tbody tr')) {
              const tds = Array.from(tr.querySelectorAll('td')).map(td =>
                td.innerText.trim().replace(/\\s+/g, ' ')
              );
              if (!tds.length) continue;
              const row = {};
              for (const col of wantedColumns) {
                const idx = indexMap[col];
                row[col] = idx >= 0 && idx < tds.length ? tds[idx] : '';
              }
              rows.push(row);
            }
            return { empty: false, headers: ths, rows };
          }
          return { empty: true, headers: [], rows: [] };
        }""",
        {"wantedColumns": SERVICE_HISTORY_COLUMNS},
    )
    return data


async def _is_next_disabled(page):
    next_btn = await page.query_selector(NEXT_BUTTON)
    if not next_btn:
        return True
    if not await next_btn.is_visible():
        return True
    try:
        return await next_btn.evaluate(
            """el => {
              const cls = ((el.className || '') + ' ' +
                ((el.parentElement && el.parentElement.className) || '')).toLowerCase();
              if (cls.includes('disabled')) return true;
              if (el.getAttribute('aria-disabled') === 'true') return true;
              if (el.hasAttribute('disabled')) return true;
              return false;
            }"""
        )
    except Exception:
        return False


async def _collect_all_service_rows(page):
    """Paginate through the services table and collect all rows."""
    all_rows = []
    seen_fingerprints = set()
    max_pages = 100

    for _ in range(max_pages):
        data = await _extract_service_rows_current_page(page)
        if data.get("empty"):
            break

        page_rows = data.get("rows") or []
        if not page_rows:
            break

        fingerprint = tuple(tuple(r.get(c, "") for c in SERVICE_HISTORY_COLUMNS) for r in page_rows)
        if fingerprint in seen_fingerprints:
            break
        seen_fingerprints.add(fingerprint)

        for raw in page_rows:
            all_rows.append({col: cell_or_na(raw.get(col, "")) for col in SERVICE_HISTORY_COLUMNS})

        if await _is_next_disabled(page):
            break

        next_btn = await page.query_selector(NEXT_BUTTON)
        try:
            await next_btn.click()
            await page.wait_for_load_state("domcontentloaded")
        except Exception:
            break

    return all_rows


async def download_service_history(page, download_dir, patient_id, patient_name):
    """
    Scrape patient service history into Service_History_{PatientName}.csv.

    Columns: Service Name, Package Name, Date Received, Appointment Date, Created on
    Blank cells become N/A. Empty list returns 0 (caller marks category empty ok).

    Returns row count on success, 0 when empty or on failure.
    """
    settings = load_settings()
    page_timeout = settings.get("page_timeout", 60000)
    url = SERVICE_HISTORY_URL.format(patient_id=patient_id)

    print(f"[SERVICE] Navigating to: {url}")
    try:
        await goto_ready(
            page, url,
            "table thead th",
            timeout=page_timeout,
            ready_timeout=min(int(page_timeout), 30000),
        )
        await _wait_for_service_table(page)

        rows = await _collect_all_service_rows(page)

        if not rows:
            print(f"[SERVICE] No service history rows for {patient_id}")
            return 0

        os.makedirs(download_dir, exist_ok=True)
        filename = f"Service_History_{patient_name}.csv"
        save_path = os.path.join(download_dir, filename)

        with open(save_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=SERVICE_HISTORY_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

        print(f"[SERVICE] Wrote {filename} ({len(rows)} row(s))")
        return len(rows)

    except Exception as e:
        print(f"[SERVICE] Error collecting service history for {patient_id}: {e}")
        return 0
