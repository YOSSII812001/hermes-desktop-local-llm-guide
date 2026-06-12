from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    watchdog = Path(__file__).with_name("hermes_self_improvement_watchdog.py")

    if not watchdog.exists():
        print(
            json.dumps(
                {
                    "wakeAgent": False,
                    "status": "skipped",
                    "reason": "missing_hermes_self_improvement_watchdog.py",
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                },
                ensure_ascii=False,
            )
        )
        return 0

    extra_args = [arg for arg in sys.argv[1:] if arg != "--no-delegate"]
    command = [sys.executable, str(watchdog), "--no-delegate", *extra_args]
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
