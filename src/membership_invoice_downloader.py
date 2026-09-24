# Download logic for Membership Invoices

import os
import yaml
from membership_invoice_selectors import VIEW_BUTTON_BY_PARENT, DOWNLOAD_BUTTON, NEXT_BUTTON, LAST_BUTTON
from download_ledger import (
    is_downloaded,
    mark_downloaded,
    normalize_item_key,
)
from page_wait import goto_ready


def load_settings():
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'settings.yaml')
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


async def download_membership_invoices(page, download_dir, patient_id="156640", per_page=10):
    """
    Downloads all membership invoices for a patient.
    Skips invoice URLs already in the folder download ledger (crash-safe resume).
    """
    settings = load_settings()
    page_timeout = settings.get('page_timeout', 60000)
    os.makedirs(download_dir, exist_ok=True)
    base_url = f"https://www.calystaproemr.com"
    list_page_url = f"https://www.calystaproemr.com/patient-services-invoices/membership-invoices/{patient_id}?count={per_page}&page=1"
    current_page = 1
    total_downloaded = 0
    total_skipped = 0

    while True:
        url = list_page_url.replace("page=1", f"page={current_page}")
        print(f"[MEMBERSHIP] Navigating to list page {current_page}: {url}")
        await goto_ready(page, url, VIEW_BUTTON_BY_PARENT, timeout=page_timeout)

        view_buttons = await page.query_selector_all(VIEW_BUTTON_BY_PARENT)
        print(f"[MEMBERSHIP] Page {current_page}: Found {len(view_buttons)} membership invoice(s)")
        
        if len(view_buttons) == 0:
            print(f"[MEMBERSHIP] No membership invoices found for patient {patient_id}")
            break
        
        invoice_urls = []
        for view_btn in view_buttons:
            try:
                href = await view_btn.get_attribute('href')
                if href:
                    invoice_urls.append(base_url + href)
            except Exception:
                pass
        
        print(f"[MEMBERSHIP] Found {len(invoice_urls)} membership invoice URLs to process")
        
        for idx, invoice_url in enumerate(invoice_urls):
            key = normalize_item_key(invoice_url) or invoice_url
            if is_downloaded(download_dir, key):
                print(f"[MEMBERSHIP] Skipping already downloaded invoice {idx+1} (key={key})")
                total_skipped += 1
                continue

            try:
                print(f"[MEMBERSHIP] Opening membership invoice {idx+1}/{len(invoice_urls)}: {invoice_url}")
                
                await goto_ready(
                    page, invoice_url, DOWNLOAD_BUTTON,
                    timeout=page_timeout, ready_timeout=page_timeout,
                )
                
                download_btn = await page.query_selector(DOWNLOAD_BUTTON)
                if not download_btn:
                    print(f"[MEMBERSHIP] Invoice {idx+1}: No download button found, skipping")
                    await goto_ready(page, url, VIEW_BUTTON_BY_PARENT, timeout=page_timeout)
                    continue
                
                async with page.expect_download() as download_info:
                    await download_btn.click()
                
                download = await download_info.value
                filename = download.suggested_filename
                save_path = os.path.join(download_dir, filename)
                
                if os.path.exists(save_path):
                    print(f"[MEMBERSHIP] File already exists, skipping save: {filename}")
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
                    print(f"[MEMBERSHIP] Downloaded: {filename}")
                    total_downloaded += 1
                
                await goto_ready(page, url, VIEW_BUTTON_BY_PARENT, timeout=page_timeout)
                
            except Exception as e:
                print(f"[MEMBERSHIP] Error processing membership invoice {idx+1}: {e}")
                try:
                    await goto_ready(page, url, VIEW_BUTTON_BY_PARENT, timeout=page_timeout)
                except Exception:
                    pass

        next_btn = await page.query_selector(NEXT_BUTTON)
        last_btn = await page.query_selector(LAST_BUTTON)
        
        if not next_btn or not last_btn:
            print(f"[MEMBERSHIP] No pagination buttons found. Ending download.")
            break
        
        if not await next_btn.is_visible():
            print(f"[MEMBERSHIP] Next button not visible. Ending download.")
            break
        
        current_page += 1
    
    print(f"[MEMBERSHIP] Downloaded {total_downloaded}, skipped existing {total_skipped}")
    return total_downloaded
