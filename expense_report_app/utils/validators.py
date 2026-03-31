from __future__ import annotations

from decimal import Decimal, InvalidOperation


def is_number(value: str) -> bool:
    try:
        Decimal(str(value))
        return True
    except (InvalidOperation, ValueError):
        return False


def validate_report_inputs(employee_name: str, date_from: str, date_to: str, mileage_rate: str) -> list[str]:
    errors: list[str] = []
    if not employee_name.strip():
        errors.append("Employee Name is required.")
    if not date_from.strip():
        errors.append("Date From is required.")
    if not date_to.strip():
        errors.append("Date To is required.")
    if not is_number(mileage_rate):
        errors.append("Mileage Rate must be numeric.")
    return errors
