# Download logic for Patient Images

import os
import re
from datetime import datetime, timedelta
import yaml
from image_selectors import DOWNLOAD_BUTTON, NEXT_BUTTON, LAST_BUTTON
from download_ledger import (
    LEDGER_FILENAME,
    is_downloaded,
    mark_downloaded,
    normalize_item_key,
)
from page_wait import goto_ready

_PATIENT_IMAGE_PREFIX = re.compile(r"^patient\s+image\s+", re.IGNORECASE)
_IMAGE_STEM_RE = re.compile(
    r"^(?P<id>\d+)_(?P<name>.+)_(?P<date>\d{2}-\d{2}-\d{4})(?:_(?P<time>.+))?$",
    re.IGNORECASE,
)
_TIMESTAMP_SUFFIX_RE = re.compile(r"^\d{2}_\d{2}_\d{2}$")


def parse_patient_image_stem(stem: str) -> dict | None:
    match = _IMAGE_STEM_RE.match(stem)
    if not match:
        return None
    return match.groupdict()


def parse_time_text(text: str) -> datetime | None:
    """Parse a time string from the portal row or legacy filename suffix."""
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return None
    if _TIMESTAMP_SUFFIX_RE.match(text):
        try:
            return datetime.strptime(text, "%H_%M_%S")
        except ValueError:
            return None
    for fmt in ("%I:%M:%S %p", "%I:%M %p", "%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def format_time_for_filename(value: datetime) -> str:
    """Format time as 24h timestamp: 16_04_26 (Windows-safe, no colons)."""
    return value.strftime("%H_%M_%S")


def build_patient_image_filename(
    image_id: str,
    patient_name: str,
    date_str: str,
    ext: str,
    time_str: str | None = None,
) -> str:
    base = f"{image_id}_{patient_name}_{date_str}"
    if time_str:
        base = f"{base}_{time_str}"
    return f"{base}{ext}"


def normalize_patient_image_filename(
    filename: str,
    *,
    time_str: str | None = None,
    fallback_mtime: float | None = None,
) -> str:
    """Normalize to id_name_date_HH_MM_SS.ext (strip 'patient image ' prefix)."""
    if not filename:
        return filename
    base = _PATIENT_IMAGE_PREFIX.sub("", os.path.basename(filename))
    stem, ext = os.path.splitext(base)
    parsed = parse_patient_image_stem(stem)
    if not parsed:
        return base

    time_part = time_str
    if not time_part and parsed.get("time"):
        parsed_time = parse_time_text(parsed["time"])
        if parsed_time and _TIMESTAMP_SUFFIX_RE.match(parsed["time"]):
            time_part = parsed["time"]
        elif parsed_time:
            time_part = format_time_for_filename(parsed_time)
    if not time_part and fallback_mtime is not None:
        time_part = format_time_for_filename(datetime.fromtimestamp(fallback_mtime))

    return build_patient_image_filename(
        parsed["id"],
        parsed["name"],
        parsed["date"],
        ext,
        time_part,
    )


def _assign_unique_timestamps(
    entries: list[tuple[str, float, dict]],
) -> dict[str, str]:
    """
    Map filename -> HH_MM_SS suffix.
    Uses file mtime as base; increments seconds until each suffix is unique.
    """
    used: set[str] = set()
    result: dict[str, str] = {}
    for name, mtime, parsed in sorted(
        entries,
        key=lambda item: (item[1], int(item[2]["id"]), item[0]),
    ):
        dt = datetime.fromtimestamp(mtime)
        time_str = format_time_for_filename(dt)
        while time_str in used:
            dt += timedelta(seconds=1)
            time_str = format_time_for_filename(dt)
        used.add(time_str)
        result[name] = time_str
    return result


def _folder_needs_time_migration(folder_path: str, entries: list[tuple[str, dict]]) -> bool:
    times = [parsed.get("time") or "" for _, parsed in entries]
    if not all(_TIMESTAMP_SUFFIX_RE.match(t) for t in times):
        return True
    return len(times) != len(set(times))


def _unique_path(folder_path: str, filename: str) -> str:
    """Return a non-colliding path inside folder_path."""
    dst = os.path.join(folder_path, filename)
    if not os.path.exists(dst):
        return dst
    stem, ext = os.path.splitext(filename)
    counter = 1
    while True:
        candidate = f"{stem}_{counter}{ext}"
        dst = os.path.join(folder_path, candidate)
        if not os.path.exists(dst):
            return dst
        counter += 1


def migrate_patient_image_folder(folder_path: str) -> int:
    """Ensure id_name_date_HH_MM_SS.ext with unique timestamps per folder."""
    if not os.path.isdir(folder_path):
        return 0

    entries: list[tuple[str, float, dict]] = []
    for name in os.listdir(folder_path):
        if name.startswith(".") or name == LEDGER_FILENAME:
            continue
        src = os.path.join(folder_path, name)
        if not os.path.isfile(src):
            continue
        stem, _ = os.path.splitext(name)
        parsed = parse_patient_image_stem(_PATIENT_IMAGE_PREFIX.sub("", stem))
        if not parsed:
            continue
        entries.append((name, os.path.getmtime(src), parsed))

    if not entries:
        return 0

    parsed_only = [(name, parsed) for name, _, parsed in entries]
    if not _folder_needs_time_migration(folder_path, parsed_only):
        return 0

    time_by_name = _assign_unique_timestamps(entries)
    renamed = 0
    for name, mtime, parsed in entries:
        time_str = time_by_name[name]
        if parsed.get("time") == time_str:
            continue
        ext = os.path.splitext(name)[1]
        new_name = build_patient_image_filename(
            parsed["id"],
            parsed["name"],
            parsed["date"],
            ext,
            time_str,
        )
        if new_name == name:
            continue
        src = os.path.join(folder_path, name)
        dst = _unique_path(folder_path, new_name)
        os.rename(src, dst)
        renamed += 1
    return renamed


def migrate_all_patient_images(base_downloads_path: str) -> int:
    """Normalize patient image filenames under every patient folder in base."""
    if not os.path.isdir(base_downloads_path):
        return 0
    total = 0
    for name in os.listdir(base_downloads_path):
        if not name.split("_", 1)[0].isdigit():
            continue
        images_dir = os.path.join(base_downloads_path, name, "02_Patient_Images")
        total += migrate_patient_image_folder(images_dir)
    return total


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


async def _extract_row_datetime(btn) -> str | None:
    """Read upload/capture time from the list row containing the download button."""
    try:
        raw = await btn.evaluate(
            """(el) => {
                const row = el.closest('tr');
                if (!row) return null;
                const text = (row.innerText || '').replace(/\\s+/g, ' ').trim();
                const m12 = text.match(
                    /\\d{1,2}[\\/-]\\d{1,2}[\\/-]\\d{4}\\s+(\\d{1,2}:\\d{2}(?::\\d{2})?\\s*[AP]M)/i
                );
                if (m12) return m12[1];
                const m24 = text.match(
                    /\\d{1,2}[\\/-]\\d{1,2}[\\/-]\\d{4}\\s+(\\d{1,2}:\\d{2}(?::\\d{2})?)\\b/
                );
                return m24 ? m24[1] : null;
            }"""
        )
    except Exception:
        raw = None
    parsed = parse_time_text(raw)
    if not parsed:
        return None
    return format_time_for_filename(parsed)


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
                row_time = await _extract_row_datetime(btn)
                async with page.expect_download() as download_info:
                    await btn.click()
                
                download = await download_info.value
                original_filename = download.suggested_filename
                save_filename = normalize_patient_image_filename(
                    original_filename,
                    time_str=row_time,
                    fallback_mtime=datetime.now().timestamp(),
                )
                save_path = _unique_path(download_dir, save_filename)
                
                if os.path.basename(save_path) != save_filename:
                    print(f"[IMAGES] Using unique name: {os.path.basename(save_path)}")
                
                if os.path.exists(save_path):
                    print(f"[IMAGES] File already exists, skipping save: {os.path.basename(save_path)}")
                    mark_downloaded(download_dir, key)
                    mark_downloaded(download_dir, normalize_item_key(os.path.basename(save_path)))
                    total_skipped += 1
                    try:
                        await download.cancel()
                    except Exception:
                        pass
                    continue
                
                await download.save_as(save_path)
                mark_downloaded(download_dir, key)
                mark_downloaded(download_dir, normalize_item_key(os.path.basename(save_path)))
                total_downloaded += 1
                try:
                    print(f"[IMAGES] Saved: {os.path.basename(save_path)}")
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

    migrate_patient_image_folder(download_dir)
    
    print(f"[IMAGES] Downloaded {total_downloaded}, skipped existing {total_skipped}")
    return total_downloaded
