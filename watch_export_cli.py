#!/usr/bin/env python3
"""Start the unattended export supervisor (auto-restart on crash)."""

from __future__ import annotations

import os
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
WATCH_SCRIPT = os.path.join(PROJECT_ROOT, "src", "watch_export.py")


def main() -> int:
    if not os.path.isfile(os.path.join(PROJECT_ROOT, "config", "credentials.yaml")):
        print("Error: missing config/credentials.yaml", file=sys.stderr)
        return 1

    print("Starting export supervisor (auto-restart enabled)...\n")
    result = subprocess.run(
        [sys.executable, WATCH_SCRIPT, *sys.argv[1:]],
        cwd=PROJECT_ROOT,
        check=False,
    )
    return int(result.returncode or 0)


if __name__ == "__main__":
    raise SystemExit(main())
