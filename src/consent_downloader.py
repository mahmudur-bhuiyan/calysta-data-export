# Download logic for Consent Documents

from consent_selectors import DOWNLOAD_BUTTON, NEXT_BUTTON, LAST_BUTTON
import os
import yaml
from download_ledger import (
    is_downloaded,
    mark_downloaded,
    normalize_item_key,
)
from page_wait import goto_ready


def load_settings():
    """Load timeout from settings."""
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'settings.yaml')
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


async def _resolve_item_key(icon, current_page, idx):
    try:
        href = await icon.evaluate(
            """(el) => {
                const a = el.closest('a');
                if (a && a.getAttribute('href')) return a.getAttribute('href');
                if (el.getAttribute('href')) return el.getAttribute('href');
                const dataHref = el.getAttribute('data-href') || el.getAttribute('data-url');
                if (dataHref) return dataHref;
                return null;
            }"""
        )
    except Exception:
        href = None
    return normalize_item_key(href) or f"consent-page{current_page}-idx{idx}"


async def download_consent_documents(page, download_dir, patient_id="233957", per_page=10):
    """
    Downloads consent form PDFs for a patient directly from the list page.
    Skips items already in the folder download ledger (crash-safe resume).
    """
    settings = load_settings()
    page_timeout = settings.get('page_timeout', 60000)
    os.makedirs(download_dir, exist_ok=True)
    
    list_page_url = f"https://www.calystaproemr.com/patients/list-consent-documents/{patient_id}?count={per_page}&page=1"
    current_page = 1
    total_downloaded = 0
    total_skipped = 0

    while True:
        url = list_page_url.replace("page=1", f"page={current_page}")
        print(f"[CONSENT] Navigating to list page {current_page}: {url}")
        await goto_ready(page, url, DOWNLOAD_BUTTON, timeout=page_timeout)

        download_icons = await page.query_selector_all(DOWNLOAD_BUTTON)
        print(f"[CONSENT] Page {current_page}: Found {len(download_icons)} download button(s)")
        
        if len(download_icons) == 0:
            print(f"[CONSENT] No consent documents found for patient {patient_id}")
            break
        
        for idx, icon in enumerate(download_icons):
            key = await _resolve_item_key(icon, current_page, idx)
            if is_downloaded(download_dir, key):
                print(f"[CONSENT] Skipping already downloaded item {idx+1} (key={key})")
                total_skipped += 1
                continue

            try:
                async with page.expect_download() as download_info:
                    await icon.click()
                
                download = await download_info.value
                filename = download.suggested_filename
                save_path = os.path.join(download_dir, filename)
                
                if os.path.exists(save_path):
                    print(f"[CONSENT] File already exists, skipping save: {filename}")
                    mark_downloaded(download_dir, key)
                    mark_downloaded(download_dir, normalize_item_key(filename))
                    total_skipped += 1
                    try:
                        await download.cancel()
                    except Exception:
                        pass
                    continue
                
                await download.save_as(save_path)
                mark_downloaded(download_dir, key)
                mark_downloaded(download_dir, normalize_item_key(filename))
                total_downloaded += 1
                print(f"[CONSENT] Downloaded: {filename} -> {save_path}")
                    
            except Exception as e:
                print(f"[CONSENT] Button {idx+1}: Error downloading: {e}")

        next_btn = await page.query_selector(NEXT_BUTTON)
        last_btn = await page.query_selector(LAST_BUTTON)
        
        if not next_btn or not last_btn:
            print(f"[CONSENT] No pagination buttons found. Ending download.")
            break
        
        if not await next_btn.is_visible():
            print(f"[CONSENT] Next button not visible. Ending download.")
            break
        
        current_page += 1
    
    print(f"[CONSENT] Downloaded {total_downloaded}, skipped existing {total_skipped}")
    return total_downloaded
