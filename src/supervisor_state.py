"""Persistent state for unattended export supervisor (adaptive worker count)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

DEFAULT_STATE_FILENAME = "export_supervisor_state.json"


def state_path(project_root: str, filename: str = DEFAULT_STATE_FILENAME) -> str:
    return os.path.join(project_root, "downloads", filename)


def default_state(worker_start: int = 5) -> Dict[str, Any]:
    return {
        "worker_count": int(worker_start),
        "crash_streak": 0,
        "last_reason": None,
        "last_restart_at": None,
        "updated_at": None,
    }


def load_state(path: str, worker_start: int = 5) -> Dict[str, Any]:
    if not os.path.isfile(path):
        return default_state(worker_start)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return default_state(worker_start)
        base = default_state(worker_start)
        base.update(data)
        base["worker_count"] = int(base.get("worker_count") or worker_start)
        base["crash_streak"] = int(base.get("crash_streak") or 0)
        return base
    except Exception:
        return default_state(worker_start)


def save_state(path: str, state: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    payload = dict(state)
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp, path)


def next_worker_count(
    current: int,
    ladder: List[int],
    worker_min: int,
) -> int:
    """
    Step down the worker ladder after a crash.
    Example ladder [5, 3, 2]: 5→3→2→2...
    """
    cleaned = [max(worker_min, int(x)) for x in (ladder or []) if int(x) >= worker_min]
    if not cleaned:
        return max(worker_min, current - 1) if current > worker_min else worker_min

    # Unique descending
    cleaned = sorted(set(cleaned), reverse=True)
    for value in cleaned:
        if value < current:
            return value
    return max(worker_min, min(cleaned))


def apply_crash_backoff(
    state: Dict[str, Any],
    *,
    ladder: List[int],
    worker_min: int,
    reason: str,
) -> Dict[str, Any]:
    current = int(state.get("worker_count") or (ladder[0] if ladder else 5))
    state["crash_streak"] = int(state.get("crash_streak") or 0) + 1
    state["worker_count"] = next_worker_count(current, ladder, worker_min)
    state["last_reason"] = reason
    state["last_restart_at"] = datetime.now(timezone.utc).isoformat()
    return state


def reset_crash_streak(state: Dict[str, Any]) -> Dict[str, Any]:
    state["crash_streak"] = 0
    return state
