# Download logic for Invoice Documents

import os
import yaml
from invoice_selectors import VIEW_BUTTON_BY_HREF, DOWNLOAD_BUTTON, NEXT_BUTTON, LAST_BUTTON
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


async def download_invoice_documents(page, download_dir, patient_id="233957", per_page=10):
    """
    Downloads all invoice PDFs for a patient.
    Skips invoice URLs already in the folder download ledger (crash-safe resume).
    """
    settings = load_settings()
    page_timeout = settings.get('page_timeout', 60000)
    os.makedirs(download_dir, exist_ok=True)
    
    base_url = f"https://www.calystaproemr.com"
    list_page_url = f"https://www.calystaproemr.com/patient-services-invoices/all-invoices/{patient_id}?count={per_page}&page=1"
    current_page = 1
    total_downloaded = 0
    total_skipped = 0

    while True:
        url = list_page_url.replace("page=1", f"page={current_page}")
        print(f"[INVOICE] Navigating to list page {current_page}: {url}")
        await goto_ready(page, url, VIEW_BUTTON_BY_HREF, timeout=page_timeout)

        view_buttons = await page.query_selector_all(VIEW_BUTTON_BY_HREF)
        print(f"[INVOICE] Page {current_page}: Found {len(view_buttons)} invoice(s)")
        
        if len(view_buttons) == 0:
            print(f"[INVOICE] No invoices found for patient {patient_id}")
            break
        
        invoice_urls = []
        for view_btn in view_buttons:
            try:
                href = await view_btn.get_attribute('href')
                if href:
                    invoice_urls.append(base_url + href)
            except Exception:
                pass
        
        print(f"[INVOICE] Found {len(invoice_urls)} invoice URLs to process")
        
        for idx, invoice_url in enumerate(invoice_urls):
            key = normalize_item_key(invoice_url) or invoice_url
            if is_downloaded(download_dir, key):
                print(f"[INVOICE] Skipping already downloaded invoice {idx+1} (key={key})")
                total_skipped += 1
                continue

            try:
                print(f"[INVOICE] Opening invoice {idx+1}/{len(invoice_urls)}: {invoice_url}")
                
                await goto_ready(
                    page, invoice_url, DOWNLOAD_BUTTON,
                    timeout=page_timeout, ready_timeout=page_timeout,
                )
                
                download_btn = await page.query_selector(DOWNLOAD_BUTTON)
                if not download_btn:
                    print(f"[INVOICE] Invoice {idx+1}: No download button found, skipping")
                    await goto_ready(page, url, VIEW_BUTTON_BY_HREF, timeout=page_timeout)
                    continue
                
                async with page.expect_download() as download_info:
                    await download_btn.click()
                
                download = await download_info.value
                filename = download.suggested_filename
                save_path = os.path.join(download_dir, filename)
                
                if os.path.exists(save_path):
                    print(f"[INVOICE] File already exists, skipping save: {filename}")
                    mark_downloaded(download_dir, key)
                    mark_downloaded(download_dir, normalize_item_key(filename))
                    total_skipped += 1
                    try:
                        await download.cancel()
                    except Exception:
                        pass
                else:
                    await download.save_as(save_path)
                    mark_downloaded(download_dir, key)
                    mark_downloaded(download_dir, normalize_item_key(filename))
                    print(f"[INVOICE] Downloaded: {filename}")
                    total_downloaded += 1
                
                await goto_ready(page, url, VIEW_BUTTON_BY_HREF, timeout=page_timeout)
                
            except Exception as e:
                print(f"[INVOICE] Error processing invoice {idx+1}: {e}")
                try:
                    await goto_ready(page, url, VIEW_BUTTON_BY_HREF, timeout=page_timeout)
                except Exception:
                    pass

        next_btn = await page.query_selector(NEXT_BUTTON)
        last_btn = await page.query_selector(LAST_BUTTON)
        
        if not next_btn or not last_btn:
            print(f"[INVOICE] No pagination buttons found. Ending download.")
            break
        
        if not await next_btn.is_visible():
            print(f"[INVOICE] Next button not visible. Ending download.")
            break
        
        current_page += 1
    
    print(f"[INVOICE] Downloaded {total_downloaded}, skipped existing {total_skipped}")
    return total_downloaded
