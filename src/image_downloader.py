# Download logic for Patient Images

import os
import re
import yaml
from image_selectors import DOWNLOAD_BUTTON, NEXT_BUTTON, LAST_BUTTON
from download_ledger import (
    LEDGER_FILENAME,
    is_downloaded,
    mark_downloaded,
    normalize_item_key,
)
from page_wait import goto_ready
from patient_naming import name_slug_part, patient_image_filename

_PATIENT_IMAGE_PREFIX = re.compile(r"^patient\s+image\s+", re.IGNORECASE)
_SERVER_IMAGE_RE = re.compile(
    r"^patient[_\s]+image[_\s]+(?P<image_id>\d+)$",
    re.IGNORECASE,
)
_LEGACY_STEM_RE = re.compile(
    r"^(?P<image_id>\d+)_(?P<name>.+)_(?P<date>\d{2}-\d{2}-\d{4})(?:_(?P<time>.+))?$",
    re.IGNORECASE,
)
_OLD_IMAGE_STEM_RE = re.compile(
    r"^(?P<first>[^_]+)_(?P<last>[^_]*)_(?P<patient_id>\d+)_(?P<image_id>\d+)$",
    re.IGNORECASE,
)


def parse_patient_image_stem(stem: str) -> dict | None:
    """Parse `patientId_First_Last_imageId` (new format)."""
    parts = stem.split("_")
    if len(parts) < 3:
        return None
    patient_id = parts[0]
    image_id = parts[-1]
    if not patient_id.isdigit() or not image_id.isdigit():
        return None
    name_parts = parts[1:-1]
    if not name_parts:
        return None
    first = name_parts[0]
    last = "_".join(name_parts[1:]) if len(name_parts) > 1 else ""
    return {
        "first": first,
        "last": last,
        "patient_id": patient_id,
        "image_id": image_id,
    }


def parse_patient_folder_name(folder_name: str) -> tuple[str, str, str]:
    """Parse `{id}_{First}_{Last}` folder names into id + name parts."""
    if not folder_name:
        return "", "", ""
    parts = folder_name.split("_", 1)
    if not parts or not parts[0].isdigit():
        return "", "", ""
    patient_id = parts[0]
    name_parts = parts[1].split("_") if len(parts) > 1 and parts[1] else []
    first = name_parts[0] if name_parts else ""
    last = "_".join(name_parts[1:]) if len(name_parts) > 1 else ""
    return patient_id, first, last


def extract_image_id_from_stem(stem: str) -> str | None:
    """Extract server image id from raw, legacy, or normalized filename stems."""
    stem = _PATIENT_IMAGE_PREFIX.sub("", stem)
    parsed = parse_patient_image_stem(stem)
    if parsed:
        return parsed["image_id"]

    server_match = _SERVER_IMAGE_RE.match(stem)
    if server_match:
        return server_match.group("image_id")

    legacy_match = _LEGACY_STEM_RE.match(stem)
    if legacy_match:
        return legacy_match.group("image_id")

    old_match = _OLD_IMAGE_STEM_RE.match(stem)
    if old_match:
        return old_match.group("image_id")
    return None


def build_patient_image_filename(
    first: str,
    last: str,
    patient_id: str,
    image_id: str,
    ext: str,
) -> str:
    """Build `patientId_First_Last_imageId.ext`."""
    return patient_image_filename(patient_id, first, last, image_id, ext)


def normalize_patient_image_filename(
    filename: str,
    *,
    patient_id: str,
    first_name: str | None = None,
    last_name: str | None = None,
) -> str:
    """Normalize to patientId_First_Last_imageId.ext from portal download names."""
    if not filename or not patient_id:
        return filename

    base = os.path.basename(filename)
    stem, ext = os.path.splitext(_PATIENT_IMAGE_PREFIX.sub("", base))

    first = name_slug_part(first_name or "")
    last = name_slug_part(last_name or "")

    parsed = parse_patient_image_stem(stem)
    if parsed and parsed["patient_id"] == str(patient_id):
        if parsed["first"] == first and parsed["last"] == last:
            return base
        image_id = parsed["image_id"]
    else:
        image_id = extract_image_id_from_stem(stem)
        if not image_id:
            return base

    return build_patient_image_filename(first, last, str(patient_id), image_id, ext)


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


def migrate_patient_image_folder(
    folder_path: str,
    *,
    patient_id: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
) -> int:
    """Rename images in a folder to patientId_First_Last_imageId.ext."""
    if not os.path.isdir(folder_path):
        return 0

    if not patient_id:
        parent_name = os.path.basename(os.path.dirname(folder_path))
        patient_id, folder_first, folder_last = parse_patient_folder_name(parent_name)
    else:
        folder_first, folder_last = "", ""

    first = name_slug_part(first_name or "") or folder_first
    last = name_slug_part(last_name or "") or folder_last

    if not patient_id or not first:
        return 0

    renamed = 0
    for name in sorted(os.listdir(folder_path)):
        if name.startswith(".") or name == LEDGER_FILENAME:
            continue
        src = os.path.join(folder_path, name)
        if not os.path.isfile(src):
            continue

        new_name = normalize_patient_image_filename(
            name,
            patient_id=patient_id,
            first_name=first_name,
            last_name=last_name,
        )
        if new_name == name:
            continue

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


async def download_patient_images(
    page,
    download_dir,
    patient_id="233957",
    per_page=10,
    first_name=None,
    last_name=None,
):
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
                save_filename = normalize_patient_image_filename(
                    original_filename,
                    patient_id=str(patient_id),
                    first_name=first_name,
                    last_name=last_name,
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

    migrate_patient_image_folder(
        download_dir,
        patient_id=str(patient_id),
        first_name=first_name,
        last_name=last_name,
    )

    print(f"[IMAGES] Downloaded {total_downloaded}, skipped existing {total_skipped}")
    return total_downloaded
