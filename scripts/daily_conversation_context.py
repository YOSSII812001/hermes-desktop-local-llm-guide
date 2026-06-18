"""Build the script output fed into the mentor check-in prompt.

Place this file under %LOCALAPPDATA%/hermes/scripts/ (HERMES_HOME/scripts).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import locale
import os
import random
import re
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from checkin_common import (  # noqa: E402
    atomic_write_json,
    emotion_sample,
    load_current_focus,
    load_json,
    moment_seed,
    mood_today,
)
import ensure_llm  # noqa: E402


MAX_MESSAGES = 10
MAX_MESSAGE_CHARS = 900
MAX_TOTAL_CHARS = 6500
JITTER_MAX_SECONDS = 420

WEEKDAY_JA = ["月", "火", "水", "木", "金", "土", "日"]
WEEKDAY_HINTS = {
    0: "週の立ち上がり。気負わせず、小さく始められる雰囲気が合います。",
    1: "週のリズムに乗ってきた頃。淡々と寄り添う調子が合います。",
    2: "週の折り返し。疲れが見え始める頃なので、軽さを保ってください。",
    3: "週末が見えてくる頃。積み残しをそっと確認するのに向きます。",
    4: "週末前。区切りをつける手伝いと、休みへの橋渡しが合います。",
    5: "休日。仕事の話題は控えめに、回復を優先する声かけが合います。",
    6: "休日の終わり。明日へ軽く備える程度で、急かさないでください。",
}

# Each style is tagged with the emotional registers it sits well with, so the
# opening can be chosen to match the inner state (see render_opening_hint).
OPENING_STYLES = [
    {"style": "今日の出来事や状況への、さりげない観察から入る", "registers": ["calm", "crisp"]},
    {"style": "ねぎらいのひとことから入る", "registers": ["warm"]},
    {"style": "前回の話の続きに、さらりと触れるところから入る", "registers": ["warm", "calm"]},
    {"style": "季節や時間帯の感覚に、ごく短く触れてから本題に入る", "registers": ["wistful", "calm"]},
    {"style": "結論や提案を先に置いてから、理由を短く添える", "registers": ["crisp"]},
    {"style": "問いかけではなく、そっと隣に置くような報告調で入る", "registers": ["calm", "crisp"]},
    {"style": "ふと心に浮かんだ気づきを、一言そえてから入る", "registers": ["wistful", "warm"]},
    {"style": "今日の小さな良かったことに、軽く目を向けてから入る", "registers": ["bright", "warm"]},
    {"style": "光や空気の感じを短く描いてから、本題へ移る", "registers": ["wistful", "bright"]},
    {"style": "相手の頑張りを静かに認める一文から入る", "registers": ["warm", "calm"]},
    {"style": "問いかけずに、こちらの所感を先に置いてから続ける", "registers": ["crisp", "calm"]},
    {"style": "ひと呼吸おくような、ゆったりした入り方にする", "registers": ["calm", "wistful"]},
]

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


def redact_sensitive(text: str) -> str:
    redacted = text or ""
    for pattern, replacement in SENSITIVE_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def local_day_bounds() -> tuple[float, float, str]:
    now = dt.datetime.now().astimezone()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + dt.timedelta(days=1)
    return start.timestamp(), end.timestamp(), now.strftime("%Y-%m-%d")


def shorten(text: str, limit: int = MAX_MESSAGE_CHARS) -> str:
    text = redact_sensitive(text)
    text = " ".join((text or "").replace("\r", " ").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def read_memory_fallback(hermes_home: Path) -> str:
    memory_path = hermes_home / "memories" / "MEMORY.md"
    if not memory_path.exists():
        return ""
    try:
        return shorten(memory_path.read_text(encoding="utf-8", errors="replace"), 1800)
    except OSError:
        return ""


def load_recent_messages(db_path: Path, start_ts: float, end_ts: float) -> list[sqlite3.Row]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            select
                m.id,
                m.role,
                m.content,
                m.timestamp,
                s.id as session_id,
                s.source,
                s.title
            from messages m
            join sessions s on s.id = m.session_id
            where m.timestamp >= ?
              and m.timestamp < ?
              and coalesce(m.active, 1) != 0
              and coalesce(s.source, '') != 'cron'
              and m.role = 'user'
            order by m.timestamp asc, m.id asc
            """,
            (start_ts, end_ts),
        ).fetchall()
    finally:
        conn.close()

    cleaned: list[sqlite3.Row] = []
    for row in rows:
        content = row["content"] or ""
        if not content.strip():
            continue
        cleaned.append(row)
    return cleaned[-MAX_MESSAGES:]


def render_context(rows: list[sqlite3.Row], day_label: str, hermes_home: Path) -> str:
    if not rows:
        fallback = read_memory_fallback(hermes_home)
        lines = [
            f"# 今日の会話文脈 ({day_label})",
            "",
            "今日の通常会話はまだ見つかりませんでした。",
            "この場合は恒久メモを軽く参照し、テンプレートをそのまま写さず自然に声をかけてください。",
        ]
        if fallback:
            lines.extend(["", "## 恒久メモの抜粋", fallback])
        return "\n".join(lines)

    lines = [
        f"# 今日の会話文脈 ({day_label})",
        "",
        "以下は、Cron以外の通常会話から抽出したユーザー発話です。",
        "今日のチェックインでは、この文脈から具体的な話題を1つだけ拾ってください。",
        "テンプレート文をそのまま使わず、相手の一日に合わせて短く自然に書いてください。",
        "",
        "## 直近メッセージ",
    ]

    for row in rows:
        ts = dt.datetime.fromtimestamp(float(row["timestamp"])).strftime("%H:%M")
        source = row["source"] or "unknown"
        content = shorten(row["content"] or "")
        lines.append(f"- {ts} [{source}] ユーザー: {content}")

    rendered = "\n".join(lines)
    if len(rendered) > MAX_TOTAL_CHARS:
        rendered = rendered[: MAX_TOTAL_CHARS - 1].rstrip() + "..."
    return rendered


def render_weekday_section(now: dt.datetime) -> str:
    weekday = now.weekday()
    label = WEEKDAY_JA[weekday]
    hour = now.hour
    if hour < 12:
        time_label = "朝"
    elif hour < 18:
        time_label = "夕方前"
    else:
        time_label = "夜"
    hint = WEEKDAY_HINTS.get(weekday, "")
    return "\n".join(
        [
            "## いまの時間と曜日",
            f"- {label}曜日の{time_label}です。{hint}",
        ]
    )


def render_opening_hint(emotion: dict | None = None, now: dt.datetime | None = None) -> str:
    candidates = OPENING_STYLES
    if emotion is not None:
        register = emotion.get("register")
        affine = [s for s in OPENING_STYLES if register in s.get("registers", [])]
        if affine:
            candidates = affine
    if now is not None:
        # +1 so the opening draw is decorrelated from the emotion draw, while
        # still varying per day and per check-in hour (see moment_seed).
        chosen = random.Random(moment_seed(now) + 1).choice(candidates)
    else:
        chosen = random.choice(candidates)
    style = chosen["style"]
    return "\n".join(
        [
            "## 書き出しスタイルのヒント",
            f"- 今回は「{style}」書き出しにしてください。前回までと同じ書き出しは避け、ここ数日と違う入り方にしてください。",
        ]
    )


def render_followup_section(hermes_home: Path, now: dt.datetime) -> str:
    """Diary excerpts plus at most one open-loop follow-up candidate.

    Picking a candidate stamps last_followed_on=today, so a second check-in
    on the same day naturally gets no candidate (one follow-up per day).
    """
    today = now.date()
    lines: list[str] = []

    diary_dir = hermes_home / "memories" / "diary"
    for offset in (1, 2):
        diary_path = diary_dir / f"{(today - dt.timedelta(days=offset)).isoformat()}.md"
        if not diary_path.exists():
            continue
        try:
            text = diary_path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        excerpt = " / ".join(
            line.lstrip("- ").strip()
            for line in text.splitlines()
            if line.startswith("- ")
        )[:300]
        if excerpt:
            day_word = "昨日" if offset == 1 else "一昨日"
            lines.append(f"- {day_word}: {excerpt}")

    loops_path = hermes_home / "cron" / "open_loops.json"
    loops_data = load_json(loops_path, default=None)
    if loops_data and isinstance(loops_data.get("loops"), list):
        loops = loops_data["loops"]
        today_label = today.isoformat()
        floor_label = (today - dt.timedelta(days=7)).isoformat()
        candidate = None
        for loop in loops:
            if (
                loop.get("status") == "open"
                and int(loop.get("follow_count", 0)) < 3
                and str(loop.get("last_followed_on") or "") != today_label
                and floor_label <= str(loop.get("last_mentioned") or "") < today_label
            ):
                candidate = loop
                break
        if candidate is not None:
            lines.append(
                f"- 続きの候補: {candidate['topic']} — {candidate['summary']}"
                f"（{candidate['last_mentioned']} に話題に出ました）"
            )
            candidate["follow_count"] = int(candidate.get("follow_count", 0)) + 1
            candidate["last_followed_on"] = today_label
            try:
                atomic_write_json(loops_path, loops_data)
            except OSError:
                pass

    if not lines:
        return ""
    return "\n".join(
        [
            "## 先日からの続き",
            *lines,
            "- 自然に馴染む場合だけ、この続きをひとこと気にかけてください。合わなければ触れなくて構いません。",
        ]
    )


def render_mood_section(hermes_home: Path, now: dt.datetime) -> str:
    mood = load_json(hermes_home / "cron" / "mood_state.json", default=None)
    if not mood or not isinstance(mood.get("days"), dict):
        return ""
    days = mood["days"]
    today = now.date()
    recent = []
    for offset in range(3):
        entry = days.get((today - dt.timedelta(days=offset)).isoformat())
        if isinstance(entry, dict):
            recent.append(entry)
    if not recent:
        return ""

    tired_days = sum(1 for entry in recent if int(entry.get("tired", 0)) > 0)
    yesterday = days.get((today - dt.timedelta(days=1)).isoformat()) or {}
    y_progress = int(yesterday.get("progress", 0))
    y_stuck = int(yesterday.get("stuck", 0))

    if tired_days >= 2:
        note = "ここ数日、疲労のサインが続いています。提案は1つだけ、低エネルギーで済むものにしてください。"
    elif y_progress > y_stuck and y_progress > 0:
        note = "昨日は前進が多い一日でした。軽い確認だけで十分です。"
    elif y_stuck > y_progress and y_stuck > 0:
        note = "昨日は詰まりが多めでした。急かさず、小さく区切る提案が合います。"
    else:
        return ""
    return "\n".join(["## 最近の調子", f"- {note}"])


def render_inner_state_section(hermes_home: Path, now: dt.datetime, emotion: dict | None) -> str:
    """Pillar 5: Hermes's current inner weather, as a tone hint for the LLM.

    Numbers are never exposed. With HERMES_INNER_EXPRESSION=expressive (default)
    the LLM may state the inner state in one refined sentence; with =implicit it
    only colours tone/vocabulary. HERMES_INNER_STATE=off disables the section.
    """
    if os.environ.get("HERMES_INNER_STATE", "on").strip().lower() == "off":
        return ""
    mood = mood_today(hermes_home, now)
    if emotion is None:
        emotion = emotion_sample(mood, now)
    register_word = (emotion.get("register_words") or ["落ち着いた"])[0]
    focus = load_current_focus(hermes_home, now)

    lines = ["## いまの内面"]
    lines.append(f"- 今日の気分はおおむね「{mood['label']}」。{register_word}トーンが馴染みます。")
    if (
        focus
        and focus.get("current_focus")
        and focus["current_focus"] != "今日の作業"
        and int(focus.get("depth", 0)) >= 3
    ):
        lines.append(f"- いま意識は「{focus['current_focus']}」に向いています。深追いせず、そっと触れる程度に。")
    elif focus and focus.get("lingering_loop"):
        lines.append(f"- 心の隅に「{focus['lingering_loop']}」が残っています。重くならない範囲で。")

    expression = os.environ.get("HERMES_INNER_EXPRESSION", "expressive").strip().lower()
    if expression == "implicit":
        lines.append(
            "- 内面は言葉にせず、トーン・語彙・距離感にだけにじませてください。"
            "数値・仕組み・セクション名には触れないこと。"
        )
    else:
        lines.append(
            "- この内面を、上品な敬語で一文だけ自然に述べてかまいません。"
            "芝居がからず、装飾過多や自己卑下は避け、数値・仕組み・セクション名には触れないこと。"
        )
    return "\n".join(lines)


def render_extra_sections(hermes_home: Path, now: dt.datetime) -> str:
    inner_on = os.environ.get("HERMES_INNER_STATE", "on").strip().lower() != "off"
    emotion: dict | None = None
    if inner_on:
        try:
            emotion = emotion_sample(mood_today(hermes_home, now), now)
        except Exception:
            emotion = None

    sections: list[str] = []
    for builder in (
        lambda: render_weekday_section(now),
        lambda: render_inner_state_section(hermes_home, now, emotion),
        lambda: render_opening_hint(emotion, now),
        lambda: render_followup_section(hermes_home, now),
        lambda: render_mood_section(hermes_home, now),
    ):
        try:
            section = builder()
        except Exception:
            continue
        if section:
            sections.append(section)
    return "\n\n".join(sections)


def log_skip(hermes_home: Path, reason: str) -> None:
    try:
        skips_path = hermes_home / "cron" / "checkin_skips.jsonl"
        skips_path.parent.mkdir(parents=True, exist_ok=True)
        with skips_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {"at": dt.datetime.now().astimezone().isoformat(), "reason": reason},
                    ensure_ascii=False,
                )
                + "\n"
            )
    except OSError:
        pass


def main() -> int:
    # scheduler.py captures this script's stdout with encoding="utf-8",
    # so force UTF-8 here. A prior "cp932 if nt" wrote Japanese as cp932 and
    # the UTF-8 reader turned it into mojibake (�). Keep this UTF-8.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Build the daily check-in context.")
    parser.add_argument("--no-jitter", action="store_true", help="Skip the random delivery delay (manual runs).")
    args = parser.parse_args()

    hermes_home = Path(os.environ.get("HERMES_HOME") or Path(os.environ["LOCALAPPDATA"]) / "hermes")

    # Human-like timing: do not fire at exactly hh:00. Cron passes no argv,
    # so manual runs disable this via --no-jitter or HERMES_CHECKIN_JITTER=0.
    jitter_max = JITTER_MAX_SECONDS
    try:
        jitter_max = int(os.environ.get("HERMES_CHECKIN_JITTER", jitter_max))
    except ValueError:
        pass
    if not args.no_jitter and jitter_max > 0:
        time.sleep(random.uniform(0, jitter_max))

    # The check-in needs the local LLM. If it cannot come up (GPU busy etc.),
    # skip this one quietly instead of paging an error to Discord.
    try:
        llm_ready = ensure_llm.ensure()
    except Exception:
        llm_ready = False
    if not llm_ready:
        log_skip(hermes_home, "llm_unavailable")
        print(json.dumps({"wakeAgent": False}, ensure_ascii=False))
        return 0

    db_path = hermes_home / "state.db"
    if not db_path.exists():
        print("# 今日の会話文脈\n\nstate.db が見つかりませんでした。汎用ではなく、恒久メモをもとに自然に声をかけてください。")
        return 0

    start_ts, end_ts, day_label = local_day_bounds()
    try:
        rows = load_recent_messages(db_path, start_ts, end_ts)
    except sqlite3.Error as exc:
        print(f"# 今日の会話文脈\n\nstate.db の読み取りに失敗しました: {exc}\n汎用テンプレートを避け、短く自然に声をかけてください。")
        return 0

    context = render_context(rows, day_label, hermes_home)
    extras = render_extra_sections(hermes_home, dt.datetime.now().astimezone())
    print(context + ("\n\n" + extras if extras else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
