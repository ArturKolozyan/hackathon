"""Сообщения бота в HTML parse_mode. Один шаблон на карточки, сводки и ответы.

Всё, что пришло от людей (названия, имена, чаты), проходит через esc().
Telegram понимает только b, i, u, s, code, pre, a, blockquote: списки — строками с «•».
"""

from __future__ import annotations

import re
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


_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])")
_CODE_RE = re.compile(r"`([^`]+)`")
_LINK_RE = re.compile(r'\[([^\]]+)\]\((https?://[^)\s"<>]+)\)')


def _inline(text: str) -> str:
    html = esc(text)
    html = _CODE_RE.sub(lambda m: f"<code>{m.group(1)}</code>", html)
    html = _LINK_RE.sub(lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', html)
    html = _BOLD_RE.sub(lambda m: f"<b>{m.group(1)}</b>", html)
    html = _ITALIC_RE.sub(lambda m: f"<i>{m.group(1)}</i>", html)
    return html


def _cells(row: str) -> list[str]:
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


_GROUP_HEADS = {"Просрочено", "Скоро", "Впереди", "Оплачено", "Прочее"}
_ITEM_RE = re.compile(r"^\*\*(.+?)\*\*\s+—\s+(.+)$")
_META_RE = re.compile(r"^до\s+.+,\s+ответственный:\s+.+$")


def markdown_to_html(markdown: str) -> str:
    """Ответ ассистента (markdown для веба) → HTML Telegram.

    Заголовки — жирной строкой, списки — «•», таблица — строками «первая колонка: остальные».
    """
    out: list[str] = []
    lines = markdown.replace("\r\n", "\n").split("\n")
    index = 0
    while index < len(lines):
        line = lines[index].rstrip()
        stripped = line.strip()
        if stripped.startswith("|") and index + 1 < len(lines) and re.fullmatch(r"\|?[\s:\-|]+\|?", lines[index + 1].strip() or "x"):
            head = _cells(stripped)
            index += 2
            while index < len(lines) and lines[index].strip().startswith("|"):
                cells = _cells(lines[index])
                first = _inline(cells[0]) if cells else ""
                rest = []
                for pos, cell in enumerate(cells[1:], start=1):
                    if not cell or cell == "—":
                        continue
                    label = head[pos] if pos < len(head) else ""
                    rest.append(f"{_inline(label)}: {_inline(cell)}" if label else _inline(cell))
                out.append(bullet(f"<b>{first}</b>" + (f" — {'; '.join(rest)}" if rest else "")))
                index += 1
            continue
        item = _ITEM_RE.match(stripped)
        if item and index + 1 < len(lines) and _META_RE.match(lines[index + 1].strip()):
            # Строка платежа из answers.item_md: название и сумма, под ними срок и ответственный.
            out.append(bullet(f"<b>{esc(item.group(1))}</b> — {_inline(item.group(2))}"))
            out.append(f"    <i>{esc(lines[index + 1].strip())}</i>")
            index += 2
            continue
        heading = re.match(r"^#{1,6}\s+(.*)$", stripped)
        if stripped in _GROUP_HEADS:
            out.append(f"<b>{esc(stripped)}</b>")
        elif heading:
            out.append(f"<b>{_inline(heading.group(1).strip('* '))}</b>")
        elif re.match(r"^[-*+]\s+", stripped):
            out.append(bullet(_inline(re.sub(r"^[-*+]\s+", "", stripped))))
        elif re.match(r"^\d+[.)]\s+", stripped):
            number, rest = re.match(r"^(\d+)[.)]\s+(.*)$", stripped).groups()
            out.append(f"{number}. {_inline(rest)}")
        elif re.fullmatch(r"-{3,}|\*{3,}", stripped):
            out.append("")
        else:
            out.append(_inline(line))
        index += 1
    text = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
