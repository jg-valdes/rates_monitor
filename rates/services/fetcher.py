import logging
from datetime import datetime, timezone

import requests

from rates.models import ExchangeRate

logger = logging.getLogger(__name__)

API_URL = "https://economia.awesomeapi.com.br/json/daily/USD-BRL/{days}"


def fetch_and_store(days: int = 90) -> tuple[int, int]:
    """
    Fetch last `days` days of USD/BRL rates from awesomeapi and upsert into DB.
    Returns (created_count, updated_count).
    """
    url = API_URL.format(days=days)
    logger.info(f"Fetching {days} days from {url}")

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        logger.error(f"API request failed: {exc}")
        raise

    created = updated = 0
    for item in data:
        try:
            ts = int(item["timestamp"])
            rate_date = datetime.fromtimestamp(ts, tz=timezone.utc).date()
            rate = float(item["bid"])
            high = float(item["high"]) if item.get("high") else None
            low = float(item["low"]) if item.get("low") else None
        except (KeyError, ValueError) as exc:
            logger.warning(f"Skipping malformed record: {exc}")
            continue

        _, was_created = ExchangeRate.objects.update_or_create(
            date=rate_date,
            defaults={"rate": rate, "high": high, "low": low},
        )
        if was_created:
            created += 1
        else:
            updated += 1

    logger.info(f"Done: {created} created, {updated} updated")
    return created, updated
