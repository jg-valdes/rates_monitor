import calendar
import datetime
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def month_start(value: datetime.date) -> datetime.date:
    return value.replace(day=1)


def add_months(value: datetime.date, months: int) -> datetime.date:
    month_index = value.year * 12 + value.month - 1 + months
    year, zero_based_month = divmod(month_index, 12)
    month = zero_based_month + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return datetime.date(year, month, day)


def schedule_dates(first_due_date: datetime.date, count: int, interval_months: int) -> list:
    return [add_months(first_due_date, index * interval_months) for index in range(count)]


def adjusted_amount(base_amount: Decimal, current_cub: Decimal, base_cub: Decimal) -> Decimal:
    if base_cub <= 0:
        raise ValueError("El CUB base debe ser mayor que cero.")
    return (base_amount * current_cub / base_cub).quantize(CENT, rounding=ROUND_HALF_UP)


def active_payment_total(transactions) -> Decimal:
    return sum((item.amount for item in transactions if item.voided_at is None), Decimal("0.00"))


def calculate_obligation(obligation, plan, exact_cub=None, latest_cub=None) -> dict:
    base_cub_value = getattr(obligation, "calculation_base_cub_value", None) or plan.base_cub_value
    if obligation.final_amount_override is not None:
        expected = obligation.final_amount_override
        source = "MANUAL_OVERRIDE"
        exact = True
        cub = obligation.locked_cub
    elif obligation.adjusted_amount is not None:
        expected = obligation.adjusted_amount
        source = "CUB" if obligation.applies_cub else "FIXED"
        exact = True
        cub = obligation.locked_cub
    elif not obligation.applies_cub:
        expected = obligation.base_amount
        source = "FIXED"
        exact = True
        cub = None
    elif exact_cub is not None:
        expected = adjusted_amount(obligation.base_amount, exact_cub.value, base_cub_value)
        source = "CUB"
        exact = True
        cub = exact_cub
    elif latest_cub is not None:
        expected = adjusted_amount(obligation.base_amount, latest_cub.value, base_cub_value)
        source = "PROVISIONAL"
        exact = False
        cub = latest_cub
    else:
        expected = None
        source = "CUB_PENDING"
        exact = False
        cub = None
    return {"expected": expected, "source": source, "exact": exact, "cub": cub}


def payment_status(
    obligation, paid: Decimal, expected: Decimal | None, today: datetime.date
) -> str:
    if obligation.settled_at is not None:
        return "PAID"
    if paid > 0:
        if expected is not None and paid >= expected:
            return "PAID"
        return "PARTIAL"
    if expected is None:
        return "CUB_PENDING"
    if obligation.due_date < today:
        return "OVERDUE"
    if obligation.due_date == today:
        return "DUE"
    return "UPCOMING"
