"""Stop a cron-started llama-server once nobody needs it anymore.

Place this file under %LOCALAPPDATA%/hermes/scripts/ (HERMES_HOME/scripts).

Runs as a no_agent cron job. Stays silent (empty stdout, exit 0) in every
case; the only side effect is stopping llama-server and removing the marker
written by ensure_llm.py.

Rules:
- no marker                -> nothing to do
- Hermes Desktop running   -> hand ownership to the desktop watcher, drop marker
- started less than N min  -> leave it warm (a follow-up check-in may need it)
- otherwise                -> run the stop script and drop the marker

N defaults to 30 minutes; override with env HERMES_REAPER_IDLE_MINUTES
(cron passes no argv, so env is the only knob).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from checkin_common import hermes_home, load_json  # noqa: E402

STOP_SCRIPT = Path.home() / ".hermes" / "scripts" / "stop-gemma-llama-server.ps1"
MARKER_NAME = "llama_started_by_cron.json"
LOG_NAME = "reaper_log.jsonl"
DEFAULT_IDLE_MINUTES = 30
STOP_VERIFY_SECONDS = 15


def _image_running(image_name: str) -> bool:
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/FO", "CSV", "/NH"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return image_name in (result.stdout or "")


def desktop_running() -> bool:
    return _image_running("Hermes.exe")


def server_running() -> bool:
    return _image_running("llama-server.exe")


def log_decision(decision: str, **extra: object) -> None:
    """Silent housekeeping is undiagnosable; keep a one-line decision trail."""
    try:
        log_path = hermes_home() / "cron" / LOG_NAME
        log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"at": dt.datetime.now().astimezone().isoformat(), "decision": decision}
        entry.update(extra)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def stop_server() -> None:
    if not STOP_SCRIPT.exists():
        return
    subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(STOP_SCRIPT),
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        marker_path = hermes_home() / "cron" / MARKER_NAME
        marker = load_json(marker_path, default=None)
        if not marker:
            return 0

        if desktop_running():
            # The desktop watcher now owns the server lifecycle.
            marker_path.unlink(missing_ok=True)
            log_decision("handoff_desktop")
            return 0

        idle_minutes = DEFAULT_IDLE_MINUTES
        try:
            idle_minutes = int(os.environ.get("HERMES_REAPER_IDLE_MINUTES", idle_minutes))
        except ValueError:
            pass

        age_minutes = None
        started_at = None
        try:
            started_at = dt.datetime.fromisoformat(str(marker.get("started_at")))
        except (TypeError, ValueError):
            pass
        if started_at is not None:
            now = dt.datetime.now().astimezone()
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=now.tzinfo)
            age_minutes = (now - started_at).total_seconds() / 60
            if age_minutes < idle_minutes:
                log_decision("too_young", age_minutes=round(age_minutes, 1))
                return 0

        if not server_running():
            # Someone already stopped it; just drop the stale marker.
            marker_path.unlink(missing_ok=True)
            log_decision("stale_marker")
            return 0

        stop_server()
        # Keep the marker unless the process is really gone, so the next
        # run retries instead of leaking a running server forever.
        deadline = time.monotonic() + STOP_VERIFY_SECONDS
        while time.monotonic() < deadline and server_running():
            time.sleep(1)
        if server_running():
            log_decision("stop_failed", age_minutes=round(age_minutes, 1) if age_minutes else None)
            return 0
        marker_path.unlink(missing_ok=True)
        log_decision("reaped", age_minutes=round(age_minutes, 1) if age_minutes else None)
    except Exception as exc:
        # Never surface errors to Discord; this is housekeeping.
        log_decision("error", message=str(exc)[:200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
