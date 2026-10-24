import re

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def email_value(value: str) -> str:
    cleaned = value.strip().lower()
    if not _EMAIL.fullmatch(cleaned):
        raise ValueError("Укажите почту")
    return cleaned


def name_value(value: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError("Укажите имя")
    return cleaned


def code_value(value: str) -> str:
    cleaned = value.strip()
    if len(cleaned) != 6 or not cleaned.isdigit():
        raise ValueError("Код — 6 цифр")
    return cleaned
