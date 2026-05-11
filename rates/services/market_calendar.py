from datetime import date, timedelta
from typing import Iterable

from rates.models import CurrencyPair, ExchangeRate


def is_weekend(target_date: date) -> bool:
    return target_date.weekday() >= 5


def mirror_missing_weekend_rates(
    pairs: Iterable[CurrencyPair],
    through_date: date | None = None,
) -> tuple[int, int]:
    """Create synthetic Saturday/Sunday rows by mirroring the latest known rate."""
    through_date = through_date or date.today()
    created = updated = 0

    for pair in pairs:
        latest = (
            ExchangeRate.objects.filter(pair=pair, date__lte=through_date).order_by("-date").first()
        )
        if not latest:
            continue

        cursor = latest.date + timedelta(days=1)
        while cursor <= through_date:
            if cursor.weekday() < 5:
                break

            _, was_created = ExchangeRate.objects.update_or_create(
                pair=pair,
                date=cursor,
                defaults={
                    "rate": latest.rate,
                    "high": latest.high,
                    "low": latest.low,
                    "is_synthetic": True,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1
            cursor += timedelta(days=1)

    return created, updated
