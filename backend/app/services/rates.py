"""Официальные курсы ЦБ РФ для подсказки «≈ … ₽». Не участвуют ни в каких итогах."""

import logging
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import httpx

log = logging.getLogger("invoice_keeper.rates")

CBR_XML = "https://www.cbr.ru/scripts/XML_daily.asp"
CBR_JSON = "https://www.cbr-xml-daily.ru/daily_json.js"
CODES = ("USD", "EUR")
FRESH_SECONDS = 3600
RETRY_SECONDS = 300
TIMEOUT = 5.0


@dataclass(frozen=True)
class Rates:
    on: date
    values: dict[str, Decimal]


_lock = threading.Lock()
_cached: Rates | None = None
_checked = 0.0
_ok = False


def _from_xml(body: bytes) -> Rates:
    root = ET.fromstring(body)
    on = datetime.strptime(root.attrib["Date"], "%d.%m.%Y").date()
    values = {}
    for item in root.iter("Valute"):
        code = item.findtext("CharCode")
        if code in CODES:
            value = Decimal(item.findtext("Value", "").replace(",", "."))
            values[code] = value / Decimal(item.findtext("Nominal", "1"))
    return Rates(on=on, values=values)


def _from_json(data: dict) -> Rates:
    on = datetime.fromisoformat(data["Date"]).date()
    values = {}
    for code in CODES:
        item = data["Valute"][code]
        values[code] = Decimal(str(item["Value"])) / Decimal(str(item["Nominal"]))
    return Rates(on=on, values=values)


def fetch() -> Rates | None:
    headers = {"User-Agent": "rekeeper/1.0"}
    try:
        response = httpx.get(CBR_XML, timeout=TIMEOUT, headers=headers)
        response.raise_for_status()
        rates = _from_xml(response.content)
        if set(rates.values) == set(CODES):
            return rates
    except (httpx.HTTPError, ET.ParseError, KeyError, ValueError, InvalidOperation) as exc:
        log.warning("cbr xml unavailable: %s", type(exc).__name__)
    try:
        response = httpx.get(CBR_JSON, timeout=TIMEOUT, headers=headers)
        response.raise_for_status()
        return _from_json(response.json())
    except (httpx.HTTPError, KeyError, TypeError, ValueError, InvalidOperation) as exc:
        log.warning("cbr json unavailable: %s", type(exc).__name__)
    return None


def current() -> Rates | None:
    """Курсы из памяти; раз в час обновляются, после неудачи — повтор через 5 минут.

    Если ЦБ недоступен, остаётся последний полученный курс со своей датой.
    """
    global _cached, _checked, _ok
    with _lock:
        age = time.monotonic() - _checked
        if _checked and age < (FRESH_SECONDS if _ok else RETRY_SECONDS):
            return _cached
        fresh = fetch()
        _checked = time.monotonic()
        _ok = fresh is not None
        if fresh is not None:
            _cached = fresh
        return _cached


def forget() -> None:
    global _cached, _checked, _ok
    with _lock:
        _cached, _checked, _ok = None, 0.0, False
