"""Ensure the local llama-server is reachable before an LLM-backed cron job runs.

Place this file under %LOCALAPPDATA%/hermes/scripts/ (HERMES_HOME/scripts).

Background: mentor check-in cron jobs (no_agent=false) need the local
llama-server, but the desktop launcher stops it when Hermes Desktop exits.
This module probes /health, starts the server on demand via the existing
start script, and leaves a marker so gemma_cron_reaper.py can stop the
server later when nobody is using it.

Run manually:
    python ensure_llm.py --status   # probe only
    python ensure_llm.py            # probe, start if needed, wait for ready
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from checkin_common import atomic_write_json, hermes_home, load_json  # noqa: E402

HEALTH_URL = "http://127.0.0.1:8080/health"
START_SCRIPT = Path.home() / ".hermes" / "scripts" / "start-gemma-llama-server.ps1"
MARKER_NAME = "llama_started_by_cron.json"
READY_WAIT_SECONDS = 240
POLL_INTERVAL_SECONDS = 2
START_ACTION_PREFIX = "HERMES_LLAMA_SERVER_ACTION="
START_ACTIONS = frozenset({"started", "reused"})


def marker_path() -> Path:
    return hermes_home() / "cron" / MARKER_NAME


def probe() -> str:
    """Return 'ready', 'loading', or 'down'."""
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=3) as response:
            return "ready" if response.status == 200 else "loading"
    except urllib.error.HTTPError as exc:
        # llama-server answers 503 while the model is still loading.
        return "loading" if exc.code == 503 else "down"
    except (urllib.error.URLError, OSError):
        return "down"


def wait_until_ready(max_wait: int = READY_WAIT_SECONDS) -> bool:
    deadline = time.monotonic() + max_wait
    while time.monotonic() < deadline:
        if probe() == "ready":
            return True
        time.sleep(POLL_INTERVAL_SECONDS)
    return probe() == "ready"


def parse_start_action(stdout: str) -> str | None:
    """Return the unique valid launcher sentinel, if present."""
    sentinel_lines = [
        line for line in stdout.splitlines()
        if line.startswith(START_ACTION_PREFIX)
    ]
    if len(sentinel_lines) != 1:
        return None

    action = sentinel_lines[0][len(START_ACTION_PREFIX):]
    return action if action in START_ACTIONS else None


def write_marker() -> None:
    atomic_write_json(
        marker_path(),
        {
            "started_at": dt.datetime.now().astimezone().isoformat(),
            "started_by": "ensure_llm",
        },
    )


def ensure(max_wait: int = READY_WAIT_SECONDS) -> bool:
    """Make sure llama-server is ready. Returns True when it is."""
    if not START_SCRIPT.exists():
        return False

    try:
        with tempfile.NamedTemporaryFile(
            prefix="hermes-llama-action-", suffix=".txt", delete=False
        ) as action_handle:
            action_path = Path(action_handle.name)
    except OSError:
        return False

    try:
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(START_SCRIPT),
                "-ActionFile",
                str(action_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    finally:
        try:
            action_output = action_path.read_text(encoding="utf-8")
        except OSError:
            action_output = ""
        try:
            action_path.unlink(missing_ok=True)
        except OSError:
            pass

    if result.returncode != 0:
        return False

    action = parse_start_action(action_output)
    if action is None:
        return False
    if action == "started":
        # We initiated this start; record it so the reaper can clean up later.
        write_marker()
    return wait_until_ready(max_wait)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Ensure local llama-server availability.")
    parser.add_argument("--status", action="store_true", help="Probe only, do not start.")
    args = parser.parse_args()

    if args.status:
        marker = load_json(marker_path(), default=None)
        print(json.dumps({"health": probe(), "marker": marker}, ensure_ascii=False, indent=2))
        return 0

    ok = ensure()
    print(json.dumps({"ready": ok, "health": probe()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
