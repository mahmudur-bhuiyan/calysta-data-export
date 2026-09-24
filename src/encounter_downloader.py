from encounter_selectors import DOWNLOAD_BUTTON, NEXT_BUTTON, LAST_BUTTON
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

async def download_encounter_documents(page, download_dir, patient_id="233957", per_page=10):
    """
    Downloads all encounter PDFs for a patient, paginating as needed.
    Skips items already recorded in the folder download ledger (crash-safe resume).
    """
    settings = load_settings()
    page_timeout = settings.get('page_timeout', 60000)
    os.makedirs(download_dir, exist_ok=True)
    
    base_url = f"https://www.calystaproemr.com/patient-encounters/encounter-history/{patient_id}/global_view?count={per_page}&page=1"
    current_page = 1
    total_downloaded = 0
    total_skipped = 0

    while True:
        url = base_url.replace("page=1", f"page={current_page}")
        await goto_ready(page, url, DOWNLOAD_BUTTON, timeout=page_timeout)

        download_links = await page.query_selector_all(DOWNLOAD_BUTTON)
        print(f"[ENCOUNTER] Page {current_page}: Found {len(download_links)} download button(s)")

        for idx, link in enumerate(download_links):
            try:
                href = await link.get_attribute('href')
            except Exception:
                href = None
            key = normalize_item_key(href) or f"page{current_page}-idx{idx}"

            if is_downloaded(download_dir, key):
                print(f"[ENCOUNTER] Skipping already downloaded item {idx+1} (key={key})")
                total_skipped += 1
                continue

            try:
                async with page.expect_download() as download_info:
                    await link.click()
                download = await download_info.value
                filename = download.suggested_filename
                save_path = os.path.join(download_dir, filename)

                # If original suggested name still present (pre-rename crash), keep it
                if os.path.exists(save_path):
                    print(f"[ENCOUNTER] File already exists, skipping save: {filename}")
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
                print(f"[ENCOUNTER] Downloaded: {filename}")
            except Exception as e:
                print(f"[ENCOUNTER] Error downloading item {idx+1}: {e}")

        next_btn = await page.query_selector(NEXT_BUTTON)
        last_btn = await page.query_selector(LAST_BUTTON)
        if not next_btn or not last_btn:
            break
        if not await next_btn.is_visible():
            break
        current_page += 1

    print(f"[ENCOUNTER] Downloaded {total_downloaded}, skipped existing {total_skipped}")
    return total_downloaded
