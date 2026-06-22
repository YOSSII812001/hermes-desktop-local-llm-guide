#!/usr/bin/env python3
"""Evaluate whether a Hermes autonomous heartbeat should notify Discord.

This public sample is intentionally conservative:

- Internal autonomy bookkeeping stays silent.
- Useful safety alerts can still notify.
- Generic "heartbeat" wording is not blocked, because external heartbeat
  alerts may be legitimate.

The script is designed for Hermes no_agent cron jobs.  Print a short message
when Discord should receive it.  Print {"wakeAgent": false} when the job should
be considered successful but silent.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any


APPDATA = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes"
STATE_DB = APPDATA / "state.db"
STATE_FILE = APPDATA / "cron" / "autonomy_state.json"

DEFAULT_MAX_MESSAGES = 24
MAX_MESSAGE_CHARS = 800
MINUTES_BETWEEN_NOTIFICATIONS = 90

INTERNAL_ONLY_TOPICS = {
    "Hermes autonomy",
}

INTERNAL_NOTE_MARKERS = (
    "Hermes自律会話",
    "直近heartbeat",
)

SECRET_LABEL_RE = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"(token|api[_ -]?key|secret|password|credential|client[_ -]?secret)"
    r"\s*[:=]",
    re.IGNORECASE,
)

SECRET_VALUE_RE = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"(?P<label>token|api[_ -]?key|secret|password|credential|client[_ -]?secret)"
    r"\s*[:=]\s*"
    r"(?P<value>[^\s,;]+)?",
    re.IGNORECASE,
)

TOKEN_LIKE_RE = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"(sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,}|"
    r"xox[baprs]-[A-Za-z0-9-]{12,}|[A-Za-z0-9_-]{24,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{20,})"
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def silent_payload(reason: str) -> dict[str, Any]:
    return {
        "wakeAgent": False,
        "ok": True,
        "status": "silent",
        "reason": reason,
    }


def read_state(path: Path = STATE_FILE) -> dict[str, Any]:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {}


def write_state(state: dict[str, Any], path: Path = STATE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def parse_ts(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def minutes_since(value: Any) -> float | None:
    parsed = parse_ts(value)
    if parsed is None:
        return None
    return (dt.datetime.now(dt.timezone.utc) - parsed).total_seconds() / 60


def load_recent_messages(db_path: Path = STATE_DB, limit: int = DEFAULT_MAX_MESSAGES) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []

    query_candidates = [
        (
            "SELECT role, content, created_at FROM messages "
            "ORDER BY created_at DESC LIMIT ?"
        ),
        (
            "SELECT sender AS role, content, timestamp AS created_at FROM messages "
            "ORDER BY timestamp DESC LIMIT ?"
        ),
        (
            "SELECT role, text AS content, ts AS created_at FROM messages "
            "ORDER BY ts DESC LIMIT ?"
        ),
    ]

    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(readonly_sqlite_uri(db_path), uri=True)
        conn.row_factory = sqlite3.Row
        for query in query_candidates:
            try:
                rows = conn.execute(query, (limit,)).fetchall()
                return [
                    {
                        "role": str(row["role"] or ""),
                        "content": str(row["content"] or ""),
                        "created_at": str(row["created_at"] or ""),
                    }
                    for row in reversed(rows)
                ]
            except sqlite3.Error:
                continue
    except sqlite3.Error:
        return []
    finally:
        if conn is not None:
            conn.close()

    return []


def readonly_sqlite_uri(db_path: Path) -> str:
    return db_path.resolve().as_uri() + "?mode=ro"


def redact_text(text: str) -> str:
    text = SECRET_VALUE_RE.sub(lambda match: f"{match.group('label')}: [REDACTED]", text)
    text = TOKEN_LIKE_RE.sub("[REDACTED_TOKEN]", text)
    return text


def detect_sensitive_hits(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    for message in messages:
        content = str(message.get("content") or "")
        if SECRET_LABEL_RE.search(content) or TOKEN_LIKE_RE.search(content):
            hits.append(
                {
                    "role": str(message.get("role") or "unknown"),
                    "created_at": str(message.get("created_at") or ""),
                    "sample": redact_text(content[:MAX_MESSAGE_CHARS]),
                }
            )
    return hits


def infer_topic(messages: list[dict[str, Any]], sensitive_hits: list[dict[str, str]]) -> str:
    if sensitive_hits:
        return "safety"

    joined = "\n".join(str(m.get("content") or "") for m in messages[-8:])
    if any(marker in joined for marker in INTERNAL_NOTE_MARKERS):
        return "Hermes autonomy"
    if "heartbeat" in joined.lower() and ("Discord" in joined or "通知" in joined):
        return "notification operations"
    if "Codex" in joined or "GitHub" in joined:
        return "engineering operations"
    return "general"


def render_safety_message(hits: list[dict[str, str]]) -> str:
    return "\n".join(
        [
            "Hermes安全通知",
            "",
            "秘密情報らしい文字列を含む会話を検知しました。",
            "Discordには本文サンプルを出しません。",
            "必要なら該当メッセージをローカルで確認してください。",
            "",
            f"検出数: {len(hits)}",
        ]
    )


def has_actionable_signal(messages: list[dict[str, Any]]) -> bool:
    recent = "\n".join(str(m.get("content") or "") for m in messages[-6:])
    action_words = (
        "エラー",
        "失敗",
        "落ちた",
        "届かない",
        "止まった",
        "壊れた",
        "Connection error",
        "failed",
        "timeout",
    )
    return any(word in recent for word in action_words)


def build_status_note(topic: str, messages: list[dict[str, Any]]) -> str:
    if topic == "notification operations":
        return "\n".join(
            [
                "Hermes通知運用メモ",
                "",
                "Discord通知まわりで確認が必要そうな兆候があります。",
                "直近ログとcron outputを1回だけ確認してください。",
            ]
        )

    last_user = next(
        (
            str(m.get("content") or "").strip()
            for m in reversed(messages)
            if str(m.get("role") or "").lower() in {"user", "human"}
            and str(m.get("content") or "").strip()
        ),
        "",
    )
    if last_user:
        last_user = redact_text(last_user[:160])

    return "\n".join(
        [
            "Hermes自律チェック",
            "",
            "対応が必要そうな会話を検知しました。",
            f"topic: {topic}",
            f"hint: {last_user}" if last_user else "hint: 直近ログを確認してください。",
        ]
    )


def should_suppress(topic: str, note: str, state: dict[str, Any], *, force: bool = False) -> tuple[bool, str]:
    if force:
        return False, "forced"

    if topic in INTERNAL_ONLY_TOPICS:
        return True, "internal-only-topic"

    if any(marker in note for marker in INTERNAL_NOTE_MARKERS):
        return True, "internal-note-marker"

    elapsed = minutes_since(state.get("last_notified_at"))
    if elapsed is not None and elapsed < MINUTES_BETWEEN_NOTIFICATIONS:
        if state.get("last_topic") == topic:
            return True, "cooldown-same-topic"

    if state.get("last_note_hash") == note_hash(note):
        return True, "duplicate-note"

    return False, "notify"


def note_hash(note: str) -> str:
    return hashlib.sha256(note.encode("utf-8")).hexdigest()


def evaluate(
    *,
    messages: list[dict[str, Any]] | None = None,
    state: dict[str, Any] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    messages = messages if messages is not None else load_recent_messages()
    state = state if state is not None else read_state()

    if not messages:
        return silent_payload("no-recent-messages")

    sensitive_hits = detect_sensitive_hits(messages)
    topic = infer_topic(messages, sensitive_hits)

    if sensitive_hits:
        note = render_safety_message(sensitive_hits)
    elif has_actionable_signal(messages):
        note = build_status_note(topic, messages)
    else:
        return silent_payload("no-actionable-signal") | {
            "topic": topic,
        }

    suppress, reason = should_suppress(topic, note, state, force=force)
    if suppress:
        return silent_payload(reason) | {
            "topic": topic,
        }

    return {
        "wakeAgent": True,
        "ok": True,
        "status": "notify",
        "reason": reason,
        "topic": topic,
        "markdown": note,
    }


def update_state_after(result: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    updated = dict(state)
    updated["last_run_at"] = utc_now()
    updated["last_status"] = result.get("status")
    updated["last_reason"] = result.get("reason")

    if result.get("wakeAgent") and result.get("markdown"):
        updated["last_notified_at"] = utc_now()
        updated["last_topic"] = result.get("topic")
        updated["last_note_hash"] = note_hash(str(result.get("markdown")))

    return updated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="print the full decision JSON")
    parser.add_argument("--debug-report", action="store_true", help="include debug JSON on stderr")
    parser.add_argument("--force", action="store_true", help="ignore cooldown checks")
    parser.add_argument("--no-state-write", action="store_true", help="do not update runtime state")
    args = parser.parse_args(argv)

    state = read_state()
    result = evaluate(state=state, force=args.force)

    if not args.no_state_write:
        write_state(update_state_after(result, state))

    if args.debug_report:
        print(json.dumps(result, ensure_ascii=False, indent=2), file=sys.stderr)

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    elif result.get("wakeAgent") and result.get("markdown"):
        print(result["markdown"])
    else:
        print(json.dumps(silent_payload(str(result.get("reason") or "silent")), ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
