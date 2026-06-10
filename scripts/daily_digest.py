"""Write a rule-based daily digest of today's conversations.

Place this file under %LOCALAPPDATA%/hermes/scripts/ (HERMES_HOME/scripts).

Runs as a no_agent cron job in the evening. Reads state.db (read-only),
summarises the day without any LLM call (so it works even when llama-server
is down), and updates two artifacts:

- memories/diary/YYYY-MM-DD.md   : human-readable digest, secrets redacted
- cron/open_loops.json           : cross-day unresolved-topic tracker that
                                   daily_conversation_context.py uses to ask
                                   "how did that thing from the other day go?"

Open loop lifecycle: open -> closed. A loop closes when progress words show
up for its topic, or after it has been followed up 3 times with no new
mention (do not nag).

Manual use:
    python daily_digest.py --dry-run            # preview, no writes
    python daily_digest.py --date 2026-06-09    # backfill a specific day
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from checkin_common import (  # noqa: E402
    OPEN_LOOP_TERMS,
    PROGRESS_TERMS,
    STUCK_TERMS,
    TIRED_TERMS,
    atomic_write_json,
    atomic_write_text,
    compact,
    day_bounds,
    detect_topic,
    hermes_home,
    load_day_messages,
    load_json,
    term_hits,
)

WEEKDAY_JA = ["月", "火", "水", "木", "金", "土", "日"]
MAX_HIGHLIGHTS = 5
LOOP_RETENTION_DAYS = 14
MAX_FOLLOWUPS = 3


def build_digest(messages: list[dict[str, Any]], day: dt.date) -> dict[str, Any]:
    user_messages = [m for m in messages if m["role"] == "user"]
    assistant_messages = [m for m in messages if m["role"] == "assistant"]
    joined_user = "\n".join(str(m["raw"]) for m in user_messages)

    topic_counts: dict[str, int] = {}
    for message in user_messages:
        topic = detect_topic(str(message["raw"]))
        if topic != "今日の作業":
            topic_counts[topic] = topic_counts.get(topic, 0) + 1
    topics = [t for t, _count in sorted(topic_counts.items(), key=lambda kv: -kv[1])][:4]

    highlights = []
    for message in user_messages[-MAX_HIGHLIGHTS:]:
        stamp = dt.datetime.fromtimestamp(message["timestamp"]).strftime("%H:%M")
        highlights.append(f"- {stamp} ユーザー: {compact(str(message['raw']), 160)}")

    span = ""
    if messages:
        first = dt.datetime.fromtimestamp(messages[0]["timestamp"]).strftime("%H:%M")
        last = dt.datetime.fromtimestamp(messages[-1]["timestamp"]).strftime("%H:%M")
        span = f"{first}〜{last}"

    return {
        "day": day.isoformat(),
        "weekday": WEEKDAY_JA[day.weekday()],
        "user_count": len(user_messages),
        "assistant_count": len(assistant_messages),
        "span": span,
        "topics": topics,
        "progress": term_hits(joined_user, PROGRESS_TERMS),
        "stuck": term_hits(joined_user, STUCK_TERMS),
        "tired": term_hits(joined_user, TIRED_TERMS),
        "highlights": highlights,
    }


def render_diary(digest: dict[str, Any], open_loops: list[dict[str, Any]]) -> str:
    lines = [
        f"# 日次ダイジェスト {digest['day']} ({digest['weekday']})",
        "",
        f"- 発話: ユーザー {digest['user_count']} 件 / アシスタント {digest['assistant_count']} 件"
        + (f"（{digest['span']}）" if digest["span"] else ""),
        f"- 主な話題: {', '.join(digest['topics']) if digest['topics'] else 'とくになし'}",
        f"- 調子サイン: 前進 {digest['progress']} / 詰まり {digest['stuck']} / 疲労 {digest['tired']}",
    ]
    if digest["highlights"]:
        lines.extend(["", "## 印象に残った発話", *digest["highlights"]])
    todays_open = [
        loop for loop in open_loops
        if loop.get("status") == "open" and loop.get("last_mentioned") == digest["day"]
    ]
    if todays_open:
        lines.extend(["", "## 今日ひらいた・続いている話"])
        for loop in todays_open:
            lines.append(f"- {loop['topic']}: {loop['summary']}")
    lines.append("")
    return "\n".join(lines)


def update_open_loops(
    loops: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    day: dt.date,
) -> list[dict[str, Any]]:
    day_label = day.isoformat()
    user_messages = [m for m in messages if m["role"] == "user"]

    # Collect today's open-loop candidates and progress mentions per topic.
    candidates: dict[str, str] = {}
    progressed: set[str] = set()
    for message in user_messages:
        raw = str(message["raw"])
        topic = detect_topic(raw)
        if term_hits(raw, OPEN_LOOP_TERMS) > 0:
            candidates[topic] = compact(raw, 120)
        if term_hits(raw, PROGRESS_TERMS) > 0:
            progressed.add(topic)

    by_topic = {loop["topic"]: loop for loop in loops}

    for topic, summary in candidates.items():
        loop = by_topic.get(topic)
        if loop is not None and loop.get("status") == "open":
            loop["last_mentioned"] = day_label
            loop["summary"] = summary
        else:
            by_topic[topic] = {
                "id": f"{day_label}-{topic}",
                "topic": topic,
                "summary": summary,
                "first_seen": day_label,
                "last_mentioned": day_label,
                "status": "open",
                "follow_count": 0,
                "last_followed_on": None,
            }

    for topic in progressed:
        loop = by_topic.get(topic)
        if loop is not None and loop.get("status") == "open":
            loop["status"] = "closed"
            loop["closed_on"] = day_label
            loop["closed_reason"] = "progress"

    # Stop nagging: 3 follow-ups without a fresh mention closes the loop.
    for loop in by_topic.values():
        if (
            loop.get("status") == "open"
            and int(loop.get("follow_count", 0)) >= MAX_FOLLOWUPS
            and str(loop.get("last_followed_on") or "") > str(loop.get("last_mentioned") or "")
        ):
            loop["status"] = "closed"
            loop["closed_on"] = day_label
            loop["closed_reason"] = "no_response"

    # Prune stale closed loops.
    cutoff = (day - dt.timedelta(days=LOOP_RETENTION_DAYS)).isoformat()
    kept = [
        loop for loop in by_topic.values()
        if loop.get("status") == "open" or str(loop.get("closed_on") or loop.get("last_mentioned") or "") >= cutoff
    ]
    kept.sort(key=lambda loop: str(loop.get("last_mentioned") or ""), reverse=True)
    return kept


def main() -> int:
    # scheduler.py reads stdout as UTF-8; keep it UTF-8 (cp932 caused mojibake before).
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Write the daily conversation digest.")
    parser.add_argument("--dry-run", action="store_true", help="Print the digest instead of writing files.")
    parser.add_argument("--date", help="Target day as YYYY-MM-DD (default: today).")
    args = parser.parse_args()

    try:
        day = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
        hermes = hermes_home()
        start_ts, end_ts = day_bounds(day)
        messages = load_day_messages(hermes / "state.db", start_ts, end_ts)

        loops_path = hermes / "cron" / "open_loops.json"
        loops_data = load_json(loops_path, default={"loops": []}) or {"loops": []}
        loops = update_open_loops(list(loops_data.get("loops", [])), messages, day)

        digest = build_digest(messages, day)
        diary_text = render_diary(digest, loops)
        diary_path = hermes / "memories" / "diary" / f"{day.isoformat()}.md"

        if args.dry_run:
            print(diary_text)
            print("## open_loops.json (preview)")
            import json as _json
            print(_json.dumps({"loops": loops}, ensure_ascii=False, indent=2))
            return 0

        atomic_write_text(diary_path, diary_text)
        atomic_write_json(loops_path, {"loops": loops, "updated_at": dt.datetime.now().astimezone().isoformat()})
        # Silent on success: empty stdout means no Discord delivery.
    except Exception:
        # Housekeeping must never page the user. Errors land in cron output logs.
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
