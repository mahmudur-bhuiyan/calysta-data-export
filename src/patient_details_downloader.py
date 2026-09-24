# Scrape patient profile details into {PatientName}_details.csv

import os
import csv
import asyncio
import yaml
from patient_details_selectors import PATIENT_DETAILS_URL, PATIENT_DETAIL_FIELDS
from page_wait import goto_ready


def load_settings():
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "settings.yaml")
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def cell_or_na(value):
    text = (value or "").strip()
    text = " ".join(text.split())
    return text if text else "N/A"


async def _extract_detail_fields(page):
    """
    Read h6/p pairs on the patient view page and map to PATIENT_DETAIL_FIELDS.
    Referral Code may be a link href when the <p> text is empty or partial.
    """
    return await page.evaluate(
        r"""({ wantedFields }) => {
          const map = {};
          const headings = Array.from(document.querySelectorAll('h6'));
          for (const h6 of headings) {
            const label = (h6.innerText || '').trim().replace(/\s+/g, ' ');
            if (!label) continue;
            const parent = h6.parentElement;
            if (!parent) continue;

            let value = '';
            const p = parent.querySelector('p');
            if (p) value = (p.innerText || '').trim();

            // Prefer referral join URL when present (avoid action buttons like send-sms)
            if (/^referral code$/i.test(label)) {
              const pOnly = parent.querySelector(':scope > p, p');
              if (pOnly) {
                const pText = (pOnly.innerText || '').trim();
                if (/patients\/join\//i.test(pText) || /^https?:\/\//i.test(pText)) {
                  value = pText;
                }
              }
              if (!value || /send.?sms|send.?e-?mail|send-referral|sms-details/i.test(value)) {
                const blob = parent.innerText || '';
                const m = blob.match(/https?:\/\/[^\s"'<>]*patients\/join\/[A-Za-z0-9]+/i);
                if (m) value = m[0];
              }
            }

            // Keep first non-empty match for each label (case-insensitive)
            const key = wantedFields.find(f => f.toLowerCase() === label.toLowerCase());
            if (key && (map[key] === undefined || map[key] === '')) {
              map[key] = value;
            }
          }
          return map;
        }""",
        {"wantedFields": PATIENT_DETAIL_FIELDS},
    )


async def download_patient_details(page, download_dir, patient_id, patient_name):
    """
    Scrape patient details from /patients/view/{id} into {PatientName}_details.csv
    as a single row with fixed columns. Empty values become N/A.

    Returns 1 on success, 0 on failure.
    """
    settings = load_settings()
    page_timeout = settings.get("page_timeout", 60000)
    url = PATIENT_DETAILS_URL.format(patient_id=patient_id)

    print(f"[DETAILS] Navigating to: {url}")
    last_error = None
    for attempt in range(1, 3):
        try:
            await goto_ready(page, url, "h6", timeout=page_timeout, ready_timeout=min(page_timeout, 20000))
            if not await page.query_selector("h6"):
                print(f"[DETAILS] h6 headings not found quickly on attempt {attempt}; scraping page anyway")

            scraped = await _extract_detail_fields(page) or {}
            # If nothing scraped, retry once more before writing an all-N/A row
            if attempt == 1 and not any((v or "").strip() for v in scraped.values()):
                raise Exception("No patient detail fields found on page")

            # Fallback: locate referral join URL anywhere on the page if needed
            referral = scraped.get("Referral Code", "")
            if (
                not referral
                or "send-referral" in referral.lower()
                or "sms-details" in referral.lower()
                or "send sms" in referral.lower()
                or "send e-mail" in referral.lower()
                or "send email" in referral.lower()
            ):
                join_url = await page.evaluate(
                    r"""() => {
                      const body = document.body.innerText || '';
                      const m = body.match(/https?:\/\/[^\s]*patients\/join\/[A-Za-z0-9]+/i);
                      return m ? m[0] : '';
                    }"""
                )
                if join_url:
                    scraped["Referral Code"] = join_url

            row = {field: cell_or_na(scraped.get(field)) for field in PATIENT_DETAIL_FIELDS}

            os.makedirs(download_dir, exist_ok=True)
            filename = f"{patient_name}_details.csv"
            save_path = os.path.join(download_dir, filename)

            with open(save_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=PATIENT_DETAIL_FIELDS)
                writer.writeheader()
                writer.writerow(row)

            print(f"[DETAILS] Wrote {filename}")
            return 1

        except Exception as e:
            last_error = e
            print(f"[DETAILS] Attempt {attempt}/2 failed for {patient_id}: {e}")
            await asyncio.sleep(1)

    print(f"[DETAILS] Error collecting patient details for {patient_id}: {last_error}")
    return 0
