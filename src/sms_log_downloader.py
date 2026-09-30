# Scrape per-patient SMS conversation from the Calysta portal

import os
import yaml

from page_wait import goto_ready
from sms_log_master import write_patient_sms_log
from sms_log_selectors import (
    SMS_LOG_URL,
    CHAT_CONTAINER,
    NO_RESULTS_TEXT,
    SMS_LOG_COLUMNS,
)


def load_settings():
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "settings.yaml")
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


async def _wait_for_sms_page(page, timeout=30000):
    """Wait until the SMS page shows messages or a confirmed empty state."""
    try:
        await page.wait_for_function(
            f"""() => {{
              const body = (document.body?.innerText || '').toLowerCase();
              if (body.includes('{NO_RESULTS_TEXT}')) return true;
              return !!document.querySelector('{CHAT_CONTAINER} .single-chat-bot');
            }}""",
            timeout=timeout,
        )
    except Exception:
        pass


async def _extract_sms_rows(page, patient_id, patient_display_name):
    """Return SMS rows keyed by SMS_LOG_COLUMNS."""
    data = await page.evaluate(
        r"""({ patientId, patientDisplayName, noResultsText }) => {
          const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
          const body = norm(document.body ? document.body.innerText : '');
          if (body.toLowerCase().includes(noResultsText)) {
            return { empty: true, rows: [] };
          }

          const bubbles = Array.from(document.querySelectorAll('.entire-chat-bot .single-chat-bot'));
          const rows = bubbles.map((el) => {
            const classes = el.className || '';
            const isPatient = /\bsender-chat\b/.test(classes)
              || !!el.querySelector('.sender-chat');
            const timeEl = el.querySelector('.time-right');
            const sentOn = norm(timeEl ? timeEl.innerText : '');
            let message = norm(el.innerText);
            if (sentOn && message.endsWith(sentOn)) {
              message = norm(message.slice(0, message.length - sentOn.length));
            }
            const categoryEl = el.querySelector('.category, .msg-category, .badge');
            const category = norm(categoryEl ? categoryEl.innerText : '');
            return {
              patient_id: String(patientId),
              from: isPatient ? patientDisplayName : 'Facility',
              message,
              category,
              sent_on: sentOn,
            };
          }).filter((row) => row.message || row.sent_on);

          return { empty: rows.length === 0, rows };
        }""",
        {
            "patientId": str(patient_id).strip(),
            "patientDisplayName": patient_display_name,
            "noResultsText": NO_RESULTS_TEXT,
        },
    )
    rows = data.get("rows") or []
    return [
        {col: (row.get(col) or "").strip() for col in SMS_LOG_COLUMNS}
        for row in rows
    ]


async def download_sms_log(page, download_dir, patient_id, patient_name, patient_display_name):
    """
    Scrape SMS_Log_{PatientName}.csv from /sms-details/index/{patient_id}.

    Patients with no conversation rows do not get a CSV file.

    Returns 1 when a CSV with data rows is written, 0 when empty or on failure.
    """
    settings = load_settings()
    page_timeout = int(settings.get("page_timeout", 60000))
    url = SMS_LOG_URL.format(patient_id=patient_id)

    print(f"[SMS] Navigating to: {url}")
    try:
        await goto_ready(
            page,
            url,
            CHAT_CONTAINER,
            timeout=page_timeout,
            ready_timeout=min(page_timeout, 15000),
        )
        await _wait_for_sms_page(page, timeout=min(page_timeout, 30000))

        rows = await _extract_sms_rows(page, patient_id, patient_display_name)
        files_written, row_count = write_patient_sms_log(download_dir, patient_name, rows)
        filename = f"SMS_Log_{patient_name}.csv"
        if files_written:
            print(f"[SMS] Wrote {filename} ({row_count} row(s)) from portal")
        else:
            print(f"[SMS] No SMS rows for {patient_id}; skipped file")
        return files_written
    except Exception as e:
        print(f"[SMS] Error collecting SMS log for {patient_id}: {e}")
        return 0
