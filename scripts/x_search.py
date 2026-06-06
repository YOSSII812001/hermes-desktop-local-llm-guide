from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _default_hermes_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "hermes" / "hermes-agent"
    return Path.home() / "AppData" / "Local" / "hermes" / "hermes-agent"


HERMES_ROOT = Path(os.environ.get("HERMES_ROOT") or _default_hermes_root())
sys.path.insert(0, str(HERMES_ROOT))

from tools.x_search_tool import check_x_search_requirements, x_search_tool  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Hermes x_search directly.")
    parser.add_argument("query", help="Search query for X.")
    parser.add_argument("--handle", action="append", default=[], help="Only include this X handle. Repeatable.")
    parser.add_argument("--exclude", action="append", default=[], help="Exclude this X handle. Repeatable.")
    parser.add_argument("--from-date", default="", help="Start date in YYYY-MM-DD.")
    parser.add_argument("--to-date", default="", help="End date in YYYY-MM-DD.")
    parser.add_argument("--images", action="store_true", help="Ask xAI to understand images.")
    parser.add_argument("--videos", action="store_true", help="Ask xAI to understand videos.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON.")
    args = parser.parse_args()

    if not check_x_search_requirements():
        print(
            json.dumps(
                {"success": False, "error": "xAI OAuth/API credentials are not available."},
                ensure_ascii=False,
            )
        )
        return 1

    raw = x_search_tool(
        query=args.query,
        allowed_x_handles=args.handle or None,
        excluded_x_handles=args.exclude or None,
        from_date=args.from_date,
        to_date=args.to_date,
        enable_image_understanding=args.images,
        enable_video_understanding=args.videos,
    )
    if args.pretty:
        try:
            print(json.dumps(json.loads(raw), ensure_ascii=False, indent=2))
        except Exception:
            print(raw)
    else:
        print(raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
