from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.schemas.summary import CurrencyTotals, SummaryOut
from app.services.occurrences import list_views

CURRENCIES = ("RUB", "USD", "EUR")


def build_summary(db: Session) -> SummaryOut:
    today, items = list_views(db, view="all")
    counts = {"overdue": 0, "due_soon": 0, "upcoming": 0, "paid": 0}
    totals = {currency: {key: Decimal("0.00") for key in counts} for currency in CURRENCIES}
    seen: set[str] = set()
    for item in items:
        counts[item.status] += 1
        seen.add(item.currency)
        totals[item.currency][item.status] += Decimal(item.amount)
    rows: list[CurrencyTotals] = []
    for currency in CURRENCIES:
        if currency not in seen:
            continue
        sums = totals[currency]
        open_amount = sums["overdue"] + sums["due_soon"] + sums["upcoming"]
        rows.append(
            CurrencyTotals(
                currency=currency,
                overdue_amount=sums["overdue"],
                due_soon_amount=sums["due_soon"],
                upcoming_amount=sums["upcoming"],
                paid_amount=sums["paid"],
                open_amount=open_amount,
            )
        )
    settings = get_settings()
    return SummaryOut(
        timezone=settings.timezone,
        today=today,
        soon_days=settings.soon_days,
        counts=counts,
        by_currency=rows,
    )
