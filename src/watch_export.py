"""
Unattended export supervisor.

Starts src/main.py, watches the log for browser/RAM failures or idle hangs,
kills orphaned Playwright browsers, reduces worker_count (e.g. 5→3→2),
and restarts. Each restart uses main.py Phase 1 incomplete-first resume.

Usage (project root):
  python src/watch_export.py
  python src/watch_export.py --log bg_dose_export.log
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from typing import List, Optional, Tuple

import yaml

from supervisor_state import (
    apply_crash_backoff,
    load_state,
    reset_crash_streak,
    save_state,
    state_path,
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config")
MAIN_PY = os.path.join(SCRIPT_DIR, "main.py")

DEFAULT_CRASH_PATTERNS = [
    "MemoryError",
    "Connection closed while reading from the driver",
    "Target page, context or browser has been closed",
    "browser has been closed",
    "socket.send() raised exception",
]


def load_settings() -> dict:
    path = os.path.join(CONFIG_PATH, "settings.yaml")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def supervisor_cfg(settings: dict) -> dict:
    raw = settings.get("supervisor") or {}
    ladder = raw.get("worker_backoff") or [5, 3, 2]
    ladder = [int(x) for x in ladder]
    return {
        "idle_timeout_sec": int(raw.get("idle_timeout_sec", 900) or 900),
        "poll_interval_sec": int(raw.get("poll_interval_sec", 30) or 30),
        "crash_hit_threshold": int(raw.get("crash_hit_threshold", 8) or 8),
        "crash_window_sec": int(raw.get("crash_window_sec", 120) or 120),
        "worker_start": int(raw.get("worker_start", settings.get("worker_count", 5)) or 5),
        "worker_min": int(raw.get("worker_min", 2) or 2),
        "worker_backoff": ladder,
        "crash_patterns": list(raw.get("crash_patterns") or DEFAULT_CRASH_PATTERNS),
        "max_restarts": int(raw.get("max_restarts", 40) or 40),
        "restart_cooldown_sec": int(raw.get("restart_cooldown_sec", 20) or 20),
        "log_file": (raw.get("log_file") or "").strip(),
    }


def default_log_path(settings: dict, explicit: Optional[str]) -> str:
    if explicit:
        path = explicit if os.path.isabs(explicit) else os.path.join(PROJECT_ROOT, explicit)
        return path
    cfg = supervisor_cfg(settings)
    if cfg["log_file"]:
        p = cfg["log_file"]
        return p if os.path.isabs(p) else os.path.join(PROJECT_ROOT, p)
    # Facility-based default
    try:
        with open(os.path.join(CONFIG_PATH, "credentials.yaml"), "r", encoding="utf-8") as f:
            cred = yaml.safe_load(f) or {}
        facility = (cred.get("facility") or "export").strip()
    except Exception:
        facility = "export"
    safe = "".join(c if c.isalnum() or c in " _-" else "" for c in facility).strip()
    safe = safe.replace(" ", "_") or "export"
    return os.path.join(PROJECT_ROOT, f"{safe}_supervised.log")


def kill_playwright_orphans() -> None:
    """Best-effort cleanup of headless Chromium left behind after crashes."""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/IM", "headless_shell.exe", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        subprocess.run(
            ["pkill", "-f", "headless_shell"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )


def kill_process_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        kill_playwright_orphans()
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            time.sleep(2)
            if proc.poll() is None:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    try:
        proc.wait(timeout=15)
    except Exception:
        pass
    kill_playwright_orphans()


def start_export(worker_count: int, log_path: str) -> subprocess.Popen:
    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
    env = os.environ.copy()
    env["EXPORT_WORKER_COUNT"] = str(worker_count)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    # Append supervisor banner to log
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(
            f"\n[{datetime.now().strftime('%H:%M:%S')}] "
            f"[SUPERVISOR] Starting main.py with workers={worker_count}\n"
        )

    log_f = open(log_path, "a", encoding="utf-8", errors="replace")
    creationflags = 0
    preexec_fn = None
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        preexec_fn = os.setsid

    proc = subprocess.Popen(
        [sys.executable, MAIN_PY],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
        preexec_fn=preexec_fn,
    )
    # Keep handle alive on proc
    proc._supervisor_log_f = log_f  # type: ignore[attr-defined]
    return proc


def close_proc_log(proc: subprocess.Popen) -> None:
    log_f = getattr(proc, "_supervisor_log_f", None)
    if log_f:
        try:
            log_f.close()
        except Exception:
            pass


def read_new_text(path: str, offset: int) -> Tuple[str, int]:
    if not os.path.isfile(path):
        return "", offset
    size = os.path.getsize(path)
    if size < offset:
        offset = 0
    if size == offset:
        return "", offset
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        f.seek(offset)
        chunk = f.read()
    return chunk, size


def count_pattern_hits(text: str, patterns: List[str]) -> int:
    hits = 0
    for pat in patterns:
        if not pat:
            continue
        hits += text.count(pat)
    return hits


def export_fully_complete() -> Optional[bool]:
    """
    True if no incomplete/not_started remain.
    None if status cannot be determined.
    """
    try:
        # Import lazily so supervisor stays light if deps missing mid-edit
        sys.path.insert(0, SCRIPT_DIR)
        from main import (
            CONFIG_PATH as MAIN_CONFIG,
            DOWNLOADS_ROOT,
            load_yaml,
            load_patient_data,
            select_patient_csv,
            sanitize_facility_folder_name,
            partition_patients_by_progress,
        )

        credentials = load_yaml(os.path.join(MAIN_CONFIG, "credentials.yaml"))
        facility = credentials.get("facility", "Facility")
        csv_path, _ = select_patient_csv(facility)
        if not csv_path:
            return None
        patients = load_patient_data(csv_path)
        base = os.path.join(DOWNLOADS_ROOT, sanitize_facility_folder_name(facility))
        incomplete, not_started, _done = partition_patients_by_progress(patients, base)
        return len(incomplete) == 0 and len(not_started) == 0
    except Exception as e:
        print(f"[SUPERVISOR] Could not evaluate completion: {e}")
        return None


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [SUPERVISOR] {msg}", flush=True)


def run(log_path: str) -> int:
    settings = load_settings()
    cfg = supervisor_cfg(settings)
    spath = state_path(PROJECT_ROOT)
    state = load_state(spath, worker_start=cfg["worker_start"])

    # Bootstrap worker count
    if not state.get("worker_count"):
        state["worker_count"] = cfg["worker_start"]
    state["worker_count"] = max(cfg["worker_min"], int(state["worker_count"]))
    save_state(spath, state)

    restarts = 0
    crash_hits: List[float] = []  # timestamps of crash-pattern hits

    log(
        f"Watching export — start workers={state['worker_count']} "
        f"(min={cfg['worker_min']}), idle={cfg['idle_timeout_sec']}s, "
        f"log={log_path}"
    )
    log("Each restart resumes Phase 1 incomplete patients first via main.py.")

    while restarts <= cfg["max_restarts"]:
        workers = max(cfg["worker_min"], int(state["worker_count"]))
        kill_playwright_orphans()
        time.sleep(1)

        proc = start_export(workers, log_path)
        log(f"Spawned main.py pid={proc.pid} workers={workers}")
        offset = os.path.getsize(log_path) if os.path.isfile(log_path) else 0
        last_activity = time.time()
        crash_hits = []
        force_restart_reason: Optional[str] = None

        while proc.poll() is None:
            time.sleep(cfg["poll_interval_sec"])
            chunk, offset = read_new_text(log_path, offset)
            if chunk.strip():
                last_activity = time.time()
                hits = count_pattern_hits(chunk, cfg["crash_patterns"])
                now = time.time()
                for _ in range(hits):
                    crash_hits.append(now)
                # Keep only recent hits
                window = cfg["crash_window_sec"]
                crash_hits = [t for t in crash_hits if now - t <= window]
                if len(crash_hits) >= cfg["crash_hit_threshold"]:
                    force_restart_reason = (
                        f"crash patterns x{len(crash_hits)} "
                        f"in {window}s (MemoryError/browser closed/etc)"
                    )
                    break

            idle_for = time.time() - last_activity
            if idle_for >= cfg["idle_timeout_sec"]:
                force_restart_reason = (
                    f"log idle for {int(idle_for)}s "
                    f"(threshold {cfg['idle_timeout_sec']}s)"
                )
                break

        if force_restart_reason:
            log(f"Restarting — {force_restart_reason}")
            kill_process_tree(proc)
            close_proc_log(proc)
            state = apply_crash_backoff(
                state,
                ladder=cfg["worker_backoff"],
                worker_min=cfg["worker_min"],
                reason=force_restart_reason,
            )
            save_state(spath, state)
            log(
                f"Backoff workers → {state['worker_count']} "
                f"(crash_streak={state['crash_streak']})"
            )
            restarts += 1
            time.sleep(cfg["restart_cooldown_sec"])
            continue

        # Process exited on its own
        exit_code = proc.wait()
        close_proc_log(proc)
        kill_playwright_orphans()
        log(f"main.py exited code={exit_code}")

        done = export_fully_complete()
        if done is True:
            state = reset_crash_streak(state)
            state["last_reason"] = "export complete"
            save_state(spath, state)
            log("All patients complete. Supervisor stopping.")
            return 0

        if exit_code == 0 and done is False:
            # Clean exit but work remains (shouldn't happen often) — retry same workers
            log("Clean exit but incomplete/not-started remain — restarting same worker count.")
            state["last_reason"] = "clean exit with remaining work"
            state["last_restart_at"] = datetime.now().isoformat()
            save_state(spath, state)
            restarts += 1
            time.sleep(cfg["restart_cooldown_sec"])
            continue

        # Non-zero or unknown — treat as crash
        reason = f"main.py exit code {exit_code}"
        log(f"Treating as failure — {reason}")
        state = apply_crash_backoff(
            state,
            ladder=cfg["worker_backoff"],
            worker_min=cfg["worker_min"],
            reason=reason,
        )
        save_state(spath, state)
        log(f"Backoff workers → {state['worker_count']}")
        restarts += 1
        time.sleep(cfg["restart_cooldown_sec"])

    log(f"Max restarts ({cfg['max_restarts']}) reached — stopping.")
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Unattended facility export supervisor")
    parser.add_argument(
        "--log",
        default=None,
        help="Log file path (default: downloads/<facility>_supervised.log or settings)",
    )
    args = parser.parse_args()
    settings = load_settings()
    log_path = default_log_path(settings, args.log)
    raise SystemExit(run(log_path))


if __name__ == "__main__":
    main()
