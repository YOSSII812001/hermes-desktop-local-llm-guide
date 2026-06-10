"""Shared helpers for the human-like check-in pipeline.

Place this file under %LOCALAPPDATA%/hermes/scripts/ (HERMES_HOME/scripts).

Used by daily_conversation_context.py, daily_digest.py, ensure_llm.py and
gemma_cron_reaper.py. Existing scripts (autonomous_trigger_evaluator.py)
keep their own copies on purpose; do not refactor them to import this.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

MAX_SNIPPET_CHARS = 180

SENSITIVE_PATTERNS = [
    (re.compile(r"ntn_[A-Za-z0-9]+"), "[REDACTED_NOTION_TOKEN]"),
    (re.compile(r"sk-[A-Za-z0-9_-]{20,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{20,}"), "[REDACTED_TOKEN]"),
    (
        re.compile(
            r"(?i)\b(api[_-]?key|token|secret|password|access[_-]?token|アクセストークン)\s*[:=：]\s*\S+"
        ),
        r"\1: [REDACTED]",
    ),
]

OPEN_LOOP_TERMS = [
    "確認して",
    "調べて",
    "読める",
    "接続",
    "導入",
    "改善",
    "直して",
    "やって",
    "依頼",
    "あとで",
    "明日",
    "続き",
    "next",
    "todo",
]

STUCK_TERMS = [
    "error",
    "failed",
    "failure",
    "timeout",
    "タイムアウト",
    "失敗",
    "エラー",
    "動かない",
    "無反応",
    "詰ま",
    "できない",
    "落ち",
]

PROGRESS_TERMS = [
    "pass",
    "success",
    "ok",
    "完了",
    "成功",
    "通った",
    "作成",
    "追加",
    "修正",
    "接続でき",
    "進ん",
]

TIRED_TERMS = ["疲れた", "眠い", "しんどい", "休む", "寝る", "低エネルギー"]

TOPIC_HINTS = [
    ("ビジネスモデル設計", ["ビジネスモデル", "マネタイズ", "導入支援", "伴走", "料金", "信頼を売る", "事業設計", "収益"]),
    ("Notion MCP", ["notion", "notion mcp"]),
    ("Codex pipeline", ["agent-pipeline", "codexmcp", "codex pipeline"]),
    ("Hermes autonomy", ["hermes", "cron", "自律", "発火"]),
    ("Discord", ["discord", "dm"]),
    ("GitHub", ["github", "gh ", "githubcli"]),
    ("Obsidian", ["obsidian", "vault"]),
    ("local LLM", ["gemma", "llama-server", "q8", "q4", "llm"]),
]


def redact_sensitive(text: str) -> str:
    redacted = text or ""
    for pattern, replacement in SENSITIVE_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def compact(text: str, limit: int = MAX_SNIPPET_CHARS) -> str:
    value = " ".join(redact_sensitive(text).replace("\r", " ").split())
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "..."


def term_hits(text: str, terms: list[str]) -> int:
    lowered = text.lower()
    return sum(1 for term in terms if term.lower() in lowered)


def detect_topic(text: str) -> str:
    lowered = text.lower()
    best_topic = "今日の作業"
    best_score = 0
    for topic, hints in TOPIC_HINTS:
        score = sum(1 for hint in hints if hint.lower() in lowered)
        if score > best_score:
            best_topic = topic
            best_score = score
    return best_topic


def hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or Path(os.environ["LOCALAPPDATA"]) / "hermes")


def day_bounds(day: dt.date) -> tuple[float, float]:
    start = dt.datetime.combine(day, dt.time.min).astimezone()
    end = start + dt.timedelta(days=1)
    return start.timestamp(), end.timestamp()


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp_name, str(path))
    except OSError:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_name, str(path))
    except OSError:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def load_day_messages(
    db_path: Path,
    start_ts: float,
    end_ts: float,
    roles: tuple[str, ...] = ("user", "assistant"),
) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    placeholders = ",".join("?" for _ in roles)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            f"""
            select
                m.role,
                m.content,
                m.timestamp,
                s.source
            from messages m
            join sessions s on s.id = m.session_id
            where m.timestamp >= ?
              and m.timestamp < ?
              and coalesce(m.active, 1) != 0
              and coalesce(s.source, '') != 'cron'
              and m.role in ({placeholders})
            order by m.timestamp asc, m.id asc
            """,
            (start_ts, end_ts, *roles),
        ).fetchall()
    finally:
        conn.close()

    messages: list[dict[str, Any]] = []
    for row in rows:
        content = row["content"] or ""
        if not content.strip():
            continue
        messages.append(
            {
                "role": row["role"],
                "source": row["source"] or "unknown",
                "timestamp": float(row["timestamp"]),
                "raw": content,
            }
        )
    return messages
