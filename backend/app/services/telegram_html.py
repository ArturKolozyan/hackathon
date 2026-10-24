"""Сообщения бота в HTML parse_mode. Один шаблон на карточки, сводки и ответы бота.

Всё, что пришло от людей (названия, имена, чаты), проходит через esc().
Telegram понимает только b, i, u, s, code, pre, a, blockquote: списки — строками с «•».
"""

from __future__ import annotations

from html import escape
from typing import Iterable

BULLET = "•"


def esc(value: object) -> str:
    return escape(str(value), quote=False)


def bold(value: object) -> str:
    return f"<b>{esc(value)}</b>"


def field(label: str, value: object, *, strong: bool = False) -> str:
    shown = bold(value) if strong else esc(value)
    return f"{esc(label)}: {shown}"


def bullet(html: str) -> str:
    return f"{BULLET} {html}"


def compose(icon: str, title: str, *blocks: Iterable[str] | str | None) -> str:
    """Иконка и жирный заголовок, дальше блоки через пустую строку. Строки блоков — уже HTML."""
    parts = [f"{icon} {bold(title)}"]
    for block in blocks:
        if block is None:
            continue
        lines = [block] if isinstance(block, str) else [line for line in block if line]
        if lines:
            parts.append("")
            parts.extend(lines)
    return "\n".join(parts)


def notice(icon: str, title: str, text: str | None = None) -> str:
    """Короткий ответ бота: заголовок и одна-две фразы обычным текстом."""
    return compose(icon, title, esc(text) if text else None)
