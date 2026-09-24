# Download logic for Patient Images

import os
import yaml
from image_selectors import DOWNLOAD_BUTTON, NEXT_BUTTON, LAST_BUTTON
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


async def _resolve_item_key(btn, current_page, idx):
    try:
        href = await btn.evaluate(
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
    return normalize_item_key(href) or f"image-page{current_page}-idx{idx}"


async def download_patient_images(page, download_dir, patient_id="233957", per_page=10, patient_name=None):
    """
    Downloads all patient images from the images list page.
    Skips items already in the folder download ledger (crash-safe resume).
    """
    settings = load_settings()
    page_timeout = settings.get('page_timeout', 60000)
    os.makedirs(download_dir, exist_ok=True)
    
    list_page_url = f"https://www.calystaproemr.com/patient-images/index/{patient_id}?count={per_page}&page=1"
    current_page = 1
    total_downloaded = 0
    total_skipped = 0

    while True:
        url = list_page_url.replace("page=1", f"page={current_page}")
        print(f"[IMAGES] Navigating to list page {current_page}: {url}")
        
        try:
            await goto_ready(page, url, DOWNLOAD_BUTTON, timeout=page_timeout)
        except Exception as e:
            print(f"[IMAGES] Error navigating to page {current_page}: {e}")
            break

        try:
            download_buttons = await page.query_selector_all(DOWNLOAD_BUTTON)
            print(f"[IMAGES] Page {current_page}: Found {len(download_buttons)} download button(s)")
        except Exception as e:
            print(f"[IMAGES] Error finding download buttons: {e}")
            break
        
        if len(download_buttons) == 0:
            print(f"[IMAGES] No images found for patient {patient_id}")
            break
        
        for idx, btn in enumerate(download_buttons):
            key = await _resolve_item_key(btn, current_page, idx)
            if is_downloaded(download_dir, key):
                print(f"[IMAGES] Skipping already downloaded item {idx+1} (key={key})")
                total_skipped += 1
                continue

            try:
                async with page.expect_download() as download_info:
                    await btn.click()
                
                download = await download_info.value
                original_filename = download.suggested_filename
                save_path = os.path.join(download_dir, original_filename)
                
                if os.path.exists(save_path):
                    print(f"[IMAGES] File already exists, skipping save: {original_filename}")
                    mark_downloaded(download_dir, key)
                    mark_downloaded(download_dir, normalize_item_key(original_filename))
                    total_skipped += 1
                    try:
                        await download.cancel()
                    except Exception:
                        pass
                    continue
                
                await download.save_as(save_path)
                mark_downloaded(download_dir, key)
                mark_downloaded(download_dir, normalize_item_key(original_filename))
                total_downloaded += 1
                try:
                    print(f"[IMAGES] Saved: {original_filename}")
                except Exception:
                    pass
                
            except Exception as e:
                try:
                    print(f"[IMAGES] Error downloading image {idx+1}: {e}")
                except Exception:
                    print(f"[IMAGES] Error downloading image {idx+1}")

        try:
            next_btn = await page.query_selector(NEXT_BUTTON)
            last_btn = await page.query_selector(LAST_BUTTON)
            
            if not next_btn or not last_btn:
                print(f"[IMAGES] No pagination buttons found. Ending download.")
                break
            
            if not await next_btn.is_visible():
                print(f"[IMAGES] Next button not visible. Ending download.")
                break
            
            current_page += 1
        except Exception as e:
            print(f"[IMAGES] Error checking pagination: {e}")
            break
    
    print(f"[IMAGES] Downloaded {total_downloaded}, skipped existing {total_skipped}")
    return total_downloaded
