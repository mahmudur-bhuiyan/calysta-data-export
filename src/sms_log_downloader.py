# Scrape patient SMS conversation into SMS_Log_{PatientName}.csv

import os
import re
import csv
import asyncio
import yaml
from sms_log_selectors import (
    SMS_LOG_URL,
    CHAT_CONTAINER,
    MESSAGE_BUBBLE,
    SENDER_CHAT,
    RECEIVER_CHAT,
    MESSAGE_TIME,
    SMS_LOG_COLUMNS,
)
from page_wait import goto_ready


def load_settings():
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "settings.yaml")
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def normalize_date(date_text):
    """Collapse whitespace in date/time text."""
    text = (date_text or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text if text else "N/A"


def strip_emojis(text):
    """Remove emoji / pictographic characters; keep plain text only."""
    if not text:
        return text
    # Emoticons, symbols, transport, flags, variation selectors, ZWJ, etc.
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U0001F900-\U0001F9FF"  # supplemental symbols
        "\U0001FA00-\U0001FAFF"  # extended-A
        "\U00002700-\U000027BF"  # dingbats
        "\U00002600-\U000026FF"  # misc symbols
        "\U00002300-\U000023FF"  # misc technical
        "\U0000FE00-\U0000FE0F"  # variation selectors
        "\U0000200D"            # zero width joiner
        "\U0000200B-\U0000200F"  # zero width / directional marks
        "]+",
        flags=re.UNICODE,
    )
    cleaned = emoji_pattern.sub(" ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


async def _scroll_chat_to_load_all(page):
    """
    Scroll the chat container top↔bottom so lazy-loaded messages appear.
    Stops when scrollHeight stops growing.
    """
    chat = await page.query_selector(CHAT_CONTAINER)
    if not chat:
        return

    stable_rounds = 0
    last_height = -1

    for _ in range(40):
        height = await chat.evaluate("el => el.scrollHeight")
        # Scroll to top (older messages often load here)
        await chat.evaluate("el => { el.scrollTop = 0 }")
        await asyncio.sleep(0.35)
        # Then to bottom
        await chat.evaluate("el => { el.scrollTop = el.scrollHeight }")
        await asyncio.sleep(0.35)
        # Back to top again to encourage loading older
        await chat.evaluate("el => { el.scrollTop = 0 }")
        await asyncio.sleep(0.35)

        new_height = await chat.evaluate("el => el.scrollHeight")
        if new_height == last_height:
            stable_rounds += 1
        else:
            stable_rounds = 0
            last_height = new_height

        if stable_rounds >= 3:
            break

    # Finish at top so DOM order is stable for reading
    await chat.evaluate("el => { el.scrollTop = 0 }")
    await asyncio.sleep(0.3)


async def _extract_messages(page, patient_name):
    """
    Extract chat bubbles into From / Message / Date rows.
    sender-chat = patient (patient_name), receiver-chat = Facility.
    Returns newest-first as rendered; caller may reverse for chronological order.
    """
    return await page.evaluate(
        """({ bubbleSel, senderClass, receiverClass, timeSel, patientName }) => {
          const bubbles = Array.from(document.querySelectorAll(bubbleSel));
          const rows = [];
          for (const el of bubbles) {
            const isSender = el.classList.contains(senderClass);
            const isReceiver = el.classList.contains(receiverClass);
            if (!isSender && !isReceiver) continue;

            const timeEl = el.querySelector(timeSel);
            let date = timeEl ? timeEl.innerText.trim() : '';
            date = date.replace(/\\s+/g, ' ');

            // Clone and remove time node so message text excludes timestamp
            const clone = el.cloneNode(true);
            const cloneTime = clone.querySelector(timeSel);
            if (cloneTime) cloneTime.remove();
            let message = (clone.innerText || '').trim().replace(/\\s+/g, ' ');

            if (!message && !date) continue;

            rows.push({
              From: isSender ? patientName : 'Facility',
              Message: message || 'N/A',
              Date: date || 'N/A'
            });
          }
          return rows;
        }""",
        {
            "bubbleSel": MESSAGE_BUBBLE,
            "senderClass": SENDER_CHAT,
            "receiverClass": RECEIVER_CHAT,
            "timeSel": MESSAGE_TIME,
            "patientName": patient_name,
        },
    )


async def download_sms_log(page, download_dir, patient_id, patient_name):
    """
    Scrape SMS conversation for a patient into SMS_Log_{PatientName}.csv.

    Columns: From, Message, Date
    - Facility messages: From = "Facility"
    - Patient messages: From = patient_name
    Empty conversation writes one "no data found for this patient" row.

    Returns 1 on success, 0 on failure.
    """
    settings = load_settings()
    page_timeout = settings.get("page_timeout", 60000)
    url = SMS_LOG_URL.format(patient_id=patient_id)

    print(f"[SMS] Navigating to: {url}")
    try:
        await goto_ready(page, url, CHAT_CONTAINER, timeout=page_timeout)

        await _scroll_chat_to_load_all(page)

        rows = await _extract_messages(page, patient_name)
        # Chat UI lists newest first; reverse for chronological conversation order
        rows = list(reversed(rows)) if rows else []

        for row in rows:
            row["Date"] = normalize_date(row.get("Date"))
            row["Message"] = strip_emojis(row.get("Message") or "")
            if not (row.get("Message") or "").strip():
                row["Message"] = "N/A"

        if not rows:
            rows = [{
                "From": "N/A",
                "Message": "no data found for this patient",
                "Date": "N/A",
            }]

        os.makedirs(download_dir, exist_ok=True)
        filename = f"SMS_Log_{patient_name}.csv"
        save_path = os.path.join(download_dir, filename)

        with open(save_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=SMS_LOG_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

        print(f"[SMS] Wrote {filename} ({len(rows)} row(s))")
        return 1

    except Exception as e:
        print(f"[SMS] Error collecting SMS log for {patient_id}: {e}")
        return 0
