#!/usr/bin/env python3
"""Start a Calysta facility export using config/ and patient_lists/."""

from __future__ import annotations

import os
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
MAIN_SCRIPT = os.path.join(SRC_DIR, "main.py")


def _preflight() -> int:
    cred_path = os.path.join(PROJECT_ROOT, "config", "credentials.yaml")
    settings_path = os.path.join(PROJECT_ROOT, "config", "settings.yaml")

    if not os.path.isfile(cred_path):
        print("Error: missing config/credentials.yaml", file=sys.stderr)
        print("Create it with username, password, and facility.", file=sys.stderr)
        return 1

    if not os.path.isfile(settings_path):
        print("Error: missing config/settings.yaml", file=sys.stderr)
        return 1

    sys.path.insert(0, SRC_DIR)
    from main import (  # noqa: WPS433
        CONFIG_PATH,
        PATIENT_LISTS_DIR,
        load_yaml,
        select_patient_csv,
    )

    os.makedirs(PATIENT_LISTS_DIR, exist_ok=True)
    credentials = load_yaml(os.path.join(CONFIG_PATH, "credentials.yaml"))
    facility = (credentials.get("facility") or "").strip()
    if not facility:
        print("Error: set facility in config/credentials.yaml", file=sys.stderr)
        return 1

    csv_path, candidates = select_patient_csv(facility)
    if not csv_path:
        print(f"Error: no matching patient CSV in {PATIENT_LISTS_DIR}", file=sys.stderr)
        if candidates:
            print(f"Facility: {facility}", file=sys.stderr)
            print("Available CSV files:", file=sys.stderr)
            for path in candidates:
                print(f"  - {os.path.basename(path)}", file=sys.stderr)
            print(
                "Rename or add a CSV whose filename includes the facility name.",
                file=sys.stderr,
            )
        else:
            print(
                "Add a CSV with columns id, first_name, last_name to patient_lists/.",
                file=sys.stderr,
            )
        return 1

    print(f"Facility: {facility}", flush=True)
    print(f"Patient list: {os.path.basename(csv_path)}", flush=True)
    print(f"Output: downloads/{facility}/", flush=True)
    print("Starting export...\n", flush=True)
    return 0


def main() -> int:
    code = _preflight()
    if code != 0:
        return code

    result = subprocess.run(
        [sys.executable, MAIN_SCRIPT],
        cwd=PROJECT_ROOT,
        check=False,
    )
    return int(result.returncode or 0)


if __name__ == "__main__":
    raise SystemExit(main())
