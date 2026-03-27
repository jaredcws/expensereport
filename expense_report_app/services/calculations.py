from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def to_decimal(value: str | int | float | None) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def round_currency(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def calculate_mileage_reimbursement(miles: str | float, mileage_rate: str | float) -> float:
    total = to_decimal(miles) * to_decimal(mileage_rate)
    return round_currency(total)


def calculate_mileage_subtotal(items: list[dict], mileage_rate: str | float) -> float:
    subtotal = Decimal("0")
    rate = to_decimal(mileage_rate)
    for item in items:
        subtotal += to_decimal(item.get("number_of_miles", 0)) * rate
    return round_currency(subtotal)


def calculate_misc_subtotal(items: list[dict]) -> float:
    subtotal = Decimal("0")
    for item in items:
        subtotal += to_decimal(item.get("amount", 0))
    return round_currency(subtotal)


def calculate_period_total(mileage_subtotal: float, misc_subtotal: float) -> float:
    total = to_decimal(mileage_subtotal) + to_decimal(misc_subtotal)
    return round_currency(total)
