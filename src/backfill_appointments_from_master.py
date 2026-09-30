"""Re-scrape per-patient appointment CSVs from the Calysta portal."""

from __future__ import annotations

import argparse
import asyncio

from reexport_appointments import reexport_appointments


def backfill(facility_folder: str, patient_ids: list[str] | None = None) -> int:
    if not patient_ids:
        print("No patient IDs provided.")
        return 1
    return asyncio.run(reexport_appointments(patient_ids))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Re-scrape appointment CSVs from the Calysta portal."
    )
    parser.add_argument(
        "patient_ids",
        nargs="+",
        help="Patient IDs to re-export",
    )
    args = parser.parse_args()
    return backfill("", args.patient_ids)


if __name__ == "__main__":
    raise SystemExit(main())
