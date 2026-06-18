"""Shared helpers for the human-like check-in pipeline.

Place this file under %LOCALAPPDATA%/hermes/scripts/ (HERMES_HOME/scripts).

Used by daily_conversation_context.py, daily_digest.py, ensure_llm.py and
gemma_cron_reaper.py. Existing scripts (autonomous_trigger_evaluator.py)
keep their own copies on purpose; do not refactor them to import this.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import random
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


# --- Pillar 5: inner state (biorhythm / mood / emotion / focus) -------------
#
# Everything here is deterministic and rule-based so it works while the local
# LLM is down. The LLM only colours its output with these hints; it does not
# compute them. Only emotion_sample() uses randomness, and that is a *seeded*
# local RNG (never the global one) so the same day+hour reproduces.

BIORHYTHM_CYCLES = {"physical": 23.0, "emotional": 28.0, "intellectual": 33.0}
DEFAULT_BIORHYTHM_EPOCH = dt.date(2026, 6, 4)

EMOTION_REGISTERS = {
    "warm": ["ねぎらいの", "やわらかな"],
    "calm": ["静かな", "凪いだ"],
    "crisp": ["端正で淡々とした", "きびきびした"],
    "wistful": ["少し物思わしげな", "しっとりとした"],
    "bright": ["晴れやかな", "軽やかな"],
}


def biorhythm_epoch() -> dt.date:
    """Reference 'birth' date for the biorhythm waves. env override allowed."""
    raw = os.environ.get("HERMES_BIORHYTHM_EPOCH")
    if raw:
        try:
            return dt.date.fromisoformat(raw.strip())
        except ValueError:
            pass
    return DEFAULT_BIORHYTHM_EPOCH


def circadian_factor(now: dt.datetime) -> float:
    """Time-of-day alertness wave in -1..+1. Peak ~15:00, trough ~03:00."""
    hour = now.hour + now.minute / 60.0
    return math.sin((hour - 9.0) / 24.0 * 2 * math.pi)


def biorhythm_vector(now: dt.datetime) -> dict[str, Any]:
    """Deterministic daily-varying baseline. No randomness."""
    day_index = (now.date() - biorhythm_epoch()).days
    vector: dict[str, Any] = {
        name: math.sin(2 * math.pi * day_index / period)
        for name, period in BIORHYTHM_CYCLES.items()
    }
    vector["circadian"] = circadian_factor(now)
    vector["day_index"] = day_index
    return vector


def moment_seed(now: dt.datetime) -> int:
    """Seed that changes per day AND per hour, so the three same-day
    check-ins (11/17/21) do not collapse to the same draw."""
    day_index = (now.date() - biorhythm_epoch()).days
    return day_index * 37 + now.hour


def _recent_mood_signal(hermes_home: Path, now: dt.datetime) -> tuple[int, int, int]:
    """(fatigue_days, progress_sum, stuck_sum) over the last 3 days."""
    mood = load_json(hermes_home / "cron" / "mood_state.json", default={})
    days = mood.get("days") if isinstance(mood, dict) else {}
    if not isinstance(days, dict):
        days = {}
    today = now.date()
    fatigue = progress = stuck = 0
    for offset in range(3):
        entry = days.get((today - dt.timedelta(days=offset)).isoformat())
        if isinstance(entry, dict):
            if int(entry.get("tired", 0)) > 0:
                fatigue += 1
            progress += int(entry.get("progress", 0))
            stuck += int(entry.get("stuck", 0))
    return fatigue, progress, stuck


def _mood_label(valence: float, energy: float) -> str:
    if valence >= 0.15 and energy >= 0.15:
        return "晴れやかで弾むよう"
    if valence >= 0.15 and energy <= -0.15:
        return "おだやかで満ち足りた"
    if valence >= 0.15:
        return "やわらかく前向き"
    if valence <= -0.15 and energy >= 0.15:
        return "少し気が急くよう"
    if valence <= -0.15 and energy <= -0.15:
        return "静かに重め"
    if valence <= -0.15:
        return "ほんのり翳りがち"
    return "凪いだ"


def mood_today(hermes_home: Path, now: dt.datetime) -> dict[str, Any]:
    """Blend the emotional biorhythm wave with the recent mood_state trend."""
    bio = biorhythm_vector(now)
    fatigue, progress, stuck = _recent_mood_signal(hermes_home, now)
    fatigue_flag = 1.0 if fatigue >= 2 else (0.4 if fatigue == 1 else 0.0)
    ps_norm = max(-1.0, min(1.0, (progress - stuck) / 6.0))
    valence = 0.5 * bio["emotional"] + 0.3 * ps_norm - 0.4 * fatigue_flag
    energy = 0.5 * bio["physical"] + 0.5 * bio["circadian"] - 0.3 * fatigue_flag
    valence = max(-1.0, min(1.0, valence))
    energy = max(-1.0, min(1.0, energy))
    drivers: list[str] = []
    if fatigue >= 2:
        drivers.append("fatigue_trend")
    if progress - stuck > 0:
        drivers.append("progress")
    elif progress - stuck < 0:
        drivers.append("stuck")
    return {
        "label": _mood_label(valence, energy),
        "valence": round(valence, 3),
        "energy": round(energy, 3),
        "drivers": drivers,
    }


def emotion_sample(mood: dict[str, Any], now: dt.datetime) -> dict[str, Any]:
    """Pick an emotional register, weighted by mood, with a *seeded* RNG.

    Seed defaults to moment_seed(now) (day+hour) so it reproduces within a
    minute and shifts across days/check-ins. HERMES_EMOTION_SEED pins it.
    """
    valence = float(mood.get("valence", 0.0))
    energy = float(mood.get("energy", 0.0))
    weights = {
        "warm": 1.0 + max(0.0, -valence) * 0.5,
        "calm": 1.0 + max(0.0, -energy) * 0.6,
        "crisp": 1.0 + max(0.0, energy) * 0.7,
        "wistful": 1.0 + max(0.0, -valence) * 0.4 + max(0.0, -energy) * 0.3,
        "bright": 1.0 + max(0.0, valence) * 0.8 + max(0.0, energy) * 0.4,
    }
    seed_env = os.environ.get("HERMES_EMOTION_SEED")
    if seed_env and seed_env.lstrip("-").isdigit():
        seed = int(seed_env)
    else:
        seed = moment_seed(now)
    rng = random.Random(seed)
    registers = list(weights.keys())
    pick = rng.choices(registers, weights=[weights[r] for r in registers], k=1)[0]
    intensity = min(1.0, abs(valence) * 0.6 + (energy + 1) / 2 * 0.4)
    return {
        "register": pick,
        "register_words": EMOTION_REGISTERS[pick],
        "intensity": round(intensity, 3),
    }


def load_current_focus(hermes_home: Path, now: dt.datetime) -> dict[str, Any] | None:
    """Read focus_state.json (written by the heartbeat). Stale (>180min) -> None."""
    data = load_json(hermes_home / "cron" / "focus_state.json", default=None)
    if not isinstance(data, dict):
        return None
    updated = data.get("updated_at")
    if updated:
        try:
            stamp = dt.datetime.fromisoformat(updated)
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=now.tzinfo)
            if (now - stamp).total_seconds() / 60 > 180:
                return None
        except ValueError:
            pass
    return {
        "current_focus": data.get("current_focus"),
        "depth": int(data.get("depth", 0) or 0),
        "focus_since": data.get("focus_since"),
        "lingering_loop": data.get("lingering_loop"),
    }
