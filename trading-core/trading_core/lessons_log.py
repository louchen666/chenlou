"""lessons_log.py — append-only lessons log shared by both bots.

Stored as markdown at ~/trading-core/lessons.md so both bots write to the
same file. Each entry is timestamped and tagged with bot name + tags.

Memory rule (per user): 每次空跑必出 ≥1 条教训；新计划前必读最近 20 条。
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

LESSONS_PATH = Path(os.path.expanduser("~/trading-core/lessons.md"))


_HEADER = "# Trading Lessons Log\n\n按时间倒序，最新在最上。每次空跑/实盘必出 ≥1 条。\n\n---\n\n"


def _ensure_file() -> None:
    needs_header = (
        not LESSONS_PATH.exists()
        or "---\n\n" not in LESSONS_PATH.read_text()
    )
    if needs_header:
        LESSONS_PATH.write_text(_HEADER)


def append(bot: str, lesson: str, tags: list[str] | None = None,
           context: str | None = None) -> None:
    """Append a lesson entry.

    bot: 'stock' or 'crypto'
    lesson: the lesson text (one or more paragraphs)
    tags: optional list, e.g. ['regime', 'overfitting']
    context: optional — trade ids, dates, params at time of lesson
    """
    _ensure_file()
    ts = datetime.utcnow().isoformat(timespec="seconds")
    tag_str = " ".join(f"#{t}" for t in (tags or []))
    parts = [f"## [{ts}] [{bot}] {tag_str}".rstrip(), "", lesson.strip()]
    if context:
        parts += ["", f"_Context:_ {context.strip()}"]
    parts += ["", "---", ""]
    block = "\n".join(parts) + "\n"
    # Prepend (newest on top after the header)
    text = LESSONS_PATH.read_text()
    header_end = text.index("---\n\n") + len("---\n\n")
    new_text = text[:header_end] + block + text[header_end:]
    LESSONS_PATH.write_text(new_text)


def read_recent(n: int = 20, bot: str | None = None) -> list[str]:
    """Read most recent n lessons, optionally filtered to one bot.

    Returns list of lesson blocks (each is a multi-line string).
    """
    _ensure_file()
    text = LESSONS_PATH.read_text()
    # Split by '## [' marker preserving markers
    parts = text.split("\n## [")
    if len(parts) <= 1:
        return []
    # parts[0] is the header; parts[1:] are entries (without leading "## [")
    entries = ["## [" + p for p in parts[1:]]
    if bot:
        entries = [e for e in entries if f"] [{bot}]" in e.split("\n", 1)[0]]
    return entries[:n]


def must_read_before_new_plan(bot: str | None = None) -> str:
    """Return formatted block of last 20 lessons. Print before any new plan."""
    entries = read_recent(20, bot)
    if not entries:
        return "_No lessons logged yet._"
    return "\n".join(entries)
