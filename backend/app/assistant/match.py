"""Поиск шаблона и человека по разговорному названию. Без записи в базу."""

from __future__ import annotations

import re

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Membership, RecurringPayment, User

_SUFFIXES = (
    "ами",
    "ями",
    "ого",
    "ему",
    "ому",
    "ыми",
    "ими",
    "ами",
    "ов",
    "ев",
    "ая",
    "яя",
    "ое",
    "ее",
    "ые",
    "ие",
    "ой",
    "ий",
    "ый",
    "ую",
    "юю",
    "ом",
    "ем",
    "ам",
    "ям",
    "ах",
    "ях",
    "а",
    "я",
    "у",
    "ю",
    "е",
    "ы",
    "и",
    "о",
)


def fold(text: str) -> str:
    return text.casefold().replace("ё", "е")


def stem(word: str) -> str:
    token = fold(word)
    for suffix in _SUFFIXES:
        if len(token) > len(suffix) + 3 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def tokens(text: str) -> list[str]:
    return re.findall(r"[0-9a-zа-я]+", fold(text))


def similar(query: str, title: str) -> bool:
    query_tokens = [stem(token) for token in tokens(query) if len(token) >= 3]
    title_tokens = [stem(token) for token in tokens(title)]
    if not query_tokens or not title_tokens:
        return False
    folded_query = fold(query).strip()
    folded_title = fold(title).strip()
    if folded_query and (folded_query == folded_title or folded_query in folded_title):
        return True
    return all(any(item == other or item.startswith(other) or other.startswith(item) for other in title_tokens) for item in query_tokens)


def active_users(db: Session, team_id: uuid.UUID) -> list[User]:
    stmt = (
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.team_id == team_id, User.is_active.is_(True))
        .order_by(User.full_name)
    )
    return list(db.scalars(stmt).all())


def match_users(db: Session, query: str, team_id: uuid.UUID) -> list[User]:
    needle = query.strip()
    if not needle or needle == "__self__":
        return []
    people = active_users(db, team_id)
    exact = [user for user in people if fold(user.full_name) == fold(needle)]
    if exact:
        return exact
    partial = [user for user in people if similar(needle, user.full_name)]
    if partial:
        return partial
    # Одно слово: совпадение с любым словом имени («Иван» → «Иван Петров»).
    query_tokens = [stem(token) for token in tokens(needle) if len(token) >= 3]
    if len(query_tokens) != 1:
        return []
    found: list[User] = []
    for user in people:
        name_tokens = [stem(token) for token in tokens(user.full_name)]
        if any(query_tokens[0] == item or query_tokens[0].startswith(item) or item.startswith(query_tokens[0]) for item in name_tokens):
            found.append(user)
    return found


def list_active(db: Session, team_id: uuid.UUID) -> list[RecurringPayment]:
    stmt = (
        select(RecurringPayment)
        .options(joinedload(RecurringPayment.responsible))
        .where(RecurringPayment.team_id == team_id, RecurringPayment.is_archived.is_(False))
        .order_by(RecurringPayment.title)
    )
    return list(db.scalars(stmt).unique().all())


def match_templates(
    db: Session, query: str, team_id: uuid.UUID, *, include_archived: bool = False
) -> list[RecurringPayment]:
    stmt = (
        select(RecurringPayment)
        .options(joinedload(RecurringPayment.responsible))
        .where(RecurringPayment.team_id == team_id)
        .order_by(RecurringPayment.title)
    )
    if not include_archived:
        stmt = stmt.where(RecurringPayment.is_archived.is_(False))
    rows = list(db.scalars(stmt).unique().all())
    needle = fold(query).strip()
    exact = [row for row in rows if fold(row.title) == needle]
    if exact:
        return exact
    return [row for row in rows if similar(query, row.title)]


def people_payload(db: Session, team_id: uuid.UUID) -> list[dict[str, str]]:
    return [{"id": str(user.id), "full_name": user.full_name} for user in active_users(db, team_id)]
