# Scrape patient credit balances and write All_Credits_{PatientName}.csv

import os
import re
import csv
import asyncio
import yaml
from credits_selectors import (
    BOOKING_CREDITS_URL,
    BANKED_CREDITS_URL,
    EGIFT_CARDS_URL,
    REFERRAL_CREDITS_URL,
    PAGE_CONTENT,
    AVAILABLE_LABEL_AMOUNT_RE,
    NEXT_BUTTON,
    DATATABLES_EMPTY,
    NO_RESULTS_TEXT,
)
from page_wait import goto_ready


def load_settings():
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'settings.yaml')
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def format_money(amount):
    """Normalize money strings to $X or $X.XX (no space after $)."""
    if amount is None:
        return "$0"
    if isinstance(amount, (int, float)):
        value = float(amount)
    else:
        text = str(amount).strip()
        cleaned = re.sub(r"[^\d.\-]", "", text.replace(",", ""))
        if cleaned in ("", ".", "-", "-."):
            return "$0"
        try:
            value = float(cleaned)
        except ValueError:
            return "$0"
    if value == int(value):
        return f"${int(value)}"
    return f"${value:.2f}"


def parse_money(amount_text):
    """Parse a money string into a float."""
    if amount_text is None:
        return 0.0
    cleaned = re.sub(r"[^\d.\-]", "", str(amount_text).replace(",", ""))
    if cleaned in ("", ".", "-", "-."):
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


async def _page_text(page):
    root = await page.query_selector(PAGE_CONTENT)
    if root:
        return await root.inner_text()
    return await page.inner_text("body")


async def _find_available_label_amount(page, label_contains=None):
    """
    Find 'Available ... : $X' on the page.
    If label_contains is set, return the first match whose label contains that text.
    Returns (label, amount_str) or (None, None).
    """
    text = await _page_text(page)
    for match in re.finditer(AVAILABLE_LABEL_AMOUNT_RE, text, flags=re.IGNORECASE):
        label = re.sub(r"\s+", " ", match.group(1)).strip()
        amount = format_money(match.group(2))
        if label_contains is None or label_contains.lower() in label.lower():
            return label, amount
    return None, None


async def _table_column_values(page, header_name):
    """
    Return list of cell texts for the column whose header matches header_name
    (case-insensitive), across the currently visible table page.
    Also returns companion first-column values (often coupon codes).
    """
    return await page.evaluate(
        """({ headerName }) => {
          const tables = Array.from(document.querySelectorAll('table'));
          for (const table of tables) {
            const ths = Array.from(table.querySelectorAll('thead th')).map(th => th.innerText.trim());
            const idx = ths.findIndex(h => h.toLowerCase() === headerName.toLowerCase());
            if (idx < 0) continue;
            const empty = table.querySelector('td.dataTables_empty, .dataTables_empty');
            if (empty) return { values: [], labels: [], headers: ths };
            const rows = Array.from(table.querySelectorAll('tbody tr'));
            const values = [];
            const labels = [];
            for (const tr of rows) {
              const tds = Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim().replace(/\\s+/g, ' '));
              if (!tds.length) continue;
              values.push(tds[idx] || '');
              labels.push(tds[0] || '');
            }
            return { values, labels, headers: ths };
          }
          return { values: [], labels: [], headers: [] };
        }""",
        {"headerName": header_name},
    )


async def _collect_column_all_pages(page, header_name, page_timeout):
    """Collect a table column across DataTables pages (stops on last/duplicate page)."""
    all_values = []
    all_labels = []
    seen_fingerprints = set()
    seen_pages = 0
    max_pages = 50

    while seen_pages < max_pages:
        seen_pages += 1
        data = await _table_column_values(page, header_name)
        values = data.get("values") or []
        labels = data.get("labels") or []
        if not values:
            break

        fingerprint = tuple(zip(labels, values))
        if fingerprint in seen_fingerprints:
            # Same page content again — stop to avoid infinite loops
            break
        seen_fingerprints.add(fingerprint)

        all_values.extend(values)
        all_labels.extend(labels)

        next_btn = await page.query_selector(NEXT_BUTTON)
        if not next_btn:
            break

        try:
            is_disabled = await next_btn.evaluate(
                """el => {
                  const cls = ((el.className || '') + ' ' + ((el.parentElement && el.parentElement.className) || '')).toLowerCase();
                  if (cls.includes('disabled')) return true;
                  if (el.getAttribute('aria-disabled') === 'true') return true;
                  if (el.hasAttribute('disabled')) return true;
                  return false;
                }"""
            )
        except Exception:
            is_disabled = False

        if is_disabled:
            break
        if not await next_btn.is_visible():
            break

        try:
            await next_btn.click()
            await page.wait_for_load_state("domcontentloaded")
        except Exception:
            break

    return all_labels, all_values


async def _goto(page, url, page_timeout):
    print(f"[CREDITS] Navigating to: {url}")
    await goto_ready(page, url, PAGE_CONTENT, timeout=page_timeout)


async def download_all_credits(page, download_dir, patient_id, patient_name):
    """
    Scrape booking, banked, e-gift, and referral credit pages and write:
    All_Credits_{PatientName}.csv with columns TYPE OF CREDIT, AMOUNT.

    Always writes a CSV (including $0 rows when balances are empty).
    Returns 1 on success, 0 on failure.
    """
    settings = load_settings()
    page_timeout = settings.get("page_timeout", 60000)
    rows = []

    try:
        # 1) Booking credits
        await _goto(page, BOOKING_CREDITS_URL.format(patient_id=patient_id), page_timeout)
        booking_label, booking_amount = await _find_available_label_amount(
            page, label_contains="Booking"
        )
        rows.append({
            "TYPE OF CREDIT": booking_label or "Available Booking Credits",
            "AMOUNT": booking_amount or "$0",
        })

        # 2) Banked credits — CSV type uses fixed name per requirements
        await _goto(page, BANKED_CREDITS_URL.format(patient_id=patient_id), page_timeout)
        _, banked_amount = await _find_available_label_amount(page, label_contains="Credit Amount")
        if banked_amount is None:
            _, banked_amount = await _find_available_label_amount(page, label_contains="Available")
        rows.append({
            "TYPE OF CREDIT": "Available Banked Credit Amount",
            "AMOUNT": banked_amount or "$0",
        })

        # 3) E-gift cards — prefer exact on-page Available label; else sum Remaining Amount
        await _goto(page, EGIFT_CARDS_URL.format(patient_id=patient_id), page_timeout)
        page_text = await _page_text(page)
        egift_label, egift_amount = await _find_available_label_amount(page)

        if egift_label and egift_amount:
            rows.append({"TYPE OF CREDIT": egift_label, "AMOUNT": egift_amount})
        elif NO_RESULTS_TEXT.lower() in page_text.lower():
            # No on-page available title when empty — keep a stable type name at $0
            rows.append({"TYPE OF CREDIT": "Available E-gift Cards Credit", "AMOUNT": "$0"})
        else:
            _, remaining_values = await _collect_column_all_pages(
                page, "Remaining Amount", page_timeout
            )
            total = sum(parse_money(v) for v in remaining_values)
            # Use exact table header context when Available banner is missing
            rows.append({
                "TYPE OF CREDIT": "E-gift Cards Remaining Amount",
                "AMOUNT": format_money(total) if remaining_values else "$0",
            })

        # 4) Referral credits — one row per remaining line, then total at bottom
        await _goto(page, REFERRAL_CREDITS_URL.format(patient_id=patient_id), page_timeout)
        coupon_labels, remaining_values = await _collect_column_all_pages(
            page, "Remaining Amount", page_timeout
        )

        referral_total = 0.0
        if remaining_values:
            for coupon, remaining in zip(coupon_labels, remaining_values):
                amount_value = parse_money(remaining)
                referral_total += amount_value
                coupon_name = coupon.strip() if coupon else "Referral"
                rows.append({
                    "TYPE OF CREDIT": f"Referral Credit - {coupon_name}",
                    "AMOUNT": format_money(amount_value),
                })
        else:
            # Still emit a zero line-level placeholder so all types appear
            rows.append({
                "TYPE OF CREDIT": "Referral Credit",
                "AMOUNT": "$0",
            })

        rows.append({
            "TYPE OF CREDIT": "Total Remaining Referral Credit",
            "AMOUNT": format_money(referral_total),
        })

        # Write CSV
        os.makedirs(download_dir, exist_ok=True)
        filename = f"All_Credits_{patient_name}.csv"
        save_path = os.path.join(download_dir, filename)
        with open(save_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["TYPE OF CREDIT", "AMOUNT"])
            writer.writeheader()
            writer.writerows(rows)

        print(f"[CREDITS] Wrote {filename} ({len(rows)} rows)")
        return 1

    except Exception as e:
        print(f"[CREDITS] Error collecting credits for patient {patient_id}: {e}")
        return 0
