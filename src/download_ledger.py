"""Per-folder ledger of successfully downloaded items for crash-safe resume."""

from __future__ import annotations

import json
import os
import re
from typing import Iterable, Set
from urllib.parse import urlparse

LEDGER_FILENAME = ".download_ledger.json"


def ledger_path(download_dir: str) -> str:
    return os.path.join(download_dir, LEDGER_FILENAME)


def load_ledger(download_dir: str) -> Set[str]:
    path = ledger_path(download_dir)
    if not os.path.isfile(path):
        return set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        keys = data.get("keys", data if isinstance(data, list) else [])
        return {str(k) for k in keys if k}
    except Exception:
        return set()


def save_ledger(download_dir: str, keys: Iterable[str]) -> None:
    os.makedirs(download_dir, exist_ok=True)
    path = ledger_path(download_dir)
    payload = {"keys": sorted({str(k) for k in keys if k})}
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp_path, path)


def mark_downloaded(download_dir: str, key: str) -> None:
    if not key:
        return
    keys = load_ledger(download_dir)
    if key in keys:
        return
    keys.add(key)
    save_ledger(download_dir, keys)


def is_downloaded(download_dir: str, key: str) -> bool:
    if not key:
        return False
    return key in load_ledger(download_dir)


def normalize_item_key(value: str | None) -> str | None:
    """Build a stable resume key from an href/URL or filename."""
    if not value:
        return None
    value = value.strip()
    if not value:
        return None

    # Absolute or relative URL / path — keep enough path to stay unique
    if "://" in value or value.startswith("/"):
        parsed = urlparse(value if "://" in value else f"https://local{value}")
        path = (parsed.path or value).rstrip("/")
        if not path:
            return None
        # Prefer trailing numeric id when the parent path also contributes uniqueness
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 2 and parts[-1].isdigit():
            return "/".join(parts[-2:])
        if parts:
            return parts[-1]
        return path

    # Filename / other opaque id
    return os.path.basename(value)


def count_content_files(folder_path: str) -> int:
    """Count real download files (ignore ledger / temp / hidden)."""
    if not os.path.isdir(folder_path):
        return 0
    count = 0
    for name in os.listdir(folder_path):
        if name.startswith(".") or name.endswith(".tmp"):
            continue
        full = os.path.join(folder_path, name)
        if os.path.isfile(full):
            count += 1
    return count
