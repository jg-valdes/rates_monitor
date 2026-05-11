import calendar
import math
from datetime import date

from django.conf import settings
from django.utils import timezone

from rates.models import SourceQuotaUsage

OER_SOURCE = "openexchangerates"


def _usage_row(target_date: date | None = None) -> SourceQuotaUsage:
    target_date = target_date or timezone.localdate()
    usage, _ = SourceQuotaUsage.objects.get_or_create(
        source=OER_SOURCE,
        year=target_date.year,
        month=target_date.month,
    )
    return usage


def get_quota_status(target_date: date | None = None) -> dict:
    target_date = target_date or timezone.localdate()
    usage = _usage_row(target_date)
    monthly_quota = max(0, int(getattr(settings, "OER_MONTHLY_REQUEST_QUOTA", 1000)))
    target_ratio = float(getattr(settings, "OER_TARGET_USAGE_RATIO", 0.95))
    target_quota = max(0, math.floor(monthly_quota * target_ratio))
    remaining_target = max(0, target_quota - usage.request_count)
    days_in_month = calendar.monthrange(target_date.year, target_date.month)[1]
    days_remaining = max(1, days_in_month - target_date.day + 1)
    suggested_daily_budget = math.ceil(remaining_target / days_remaining) if remaining_target else 0

    return {
        "used": usage.request_count,
        "monthly_quota": monthly_quota,
        "target_ratio": target_ratio,
        "target_quota": target_quota,
        "remaining_target": remaining_target,
        "days_remaining": days_remaining,
        "suggested_daily_budget": suggested_daily_budget,
        "last_request_at": usage.updated_at if usage.request_count else None,
    }


def can_make_request(
    requests_needed: int = 1,
    *,
    ignore_interval: bool = False,
) -> tuple[bool, str | None]:
    status = get_quota_status()
    if status["used"] + requests_needed > status["target_quota"]:
        return (
            False,
            (
                "Local OER quota guard reached the monthly cap "
                f"({status['used']}/{status['target_quota']} tracked requests)"
            ),
        )

    if not ignore_interval and status["last_request_at"]:
        min_interval = int(getattr(settings, "OER_MIN_REQUEST_INTERVAL_MINUTES", 240))
        elapsed = timezone.now() - status["last_request_at"]
        if elapsed.total_seconds() < min_interval * 60:
            return (
                False,
                f"Waiting for the {min_interval}-minute OER cooldown before the next request",
            )

    return True, None


def record_request(count: int = 1, target_date: date | None = None) -> SourceQuotaUsage:
    usage = _usage_row(target_date)
    usage.request_count += count
    usage.save(update_fields=["request_count", "updated_at"])
    return usage


def estimate_historical_requests(days: int, target_date: date | None = None) -> int:
    target_date = target_date or timezone.localdate()
    total = 0
    for offset in range(days - 1, -1, -1):
        day = target_date.fromordinal(target_date.toordinal() - offset)
        if day.weekday() < 5:
            total += 1
    return total
