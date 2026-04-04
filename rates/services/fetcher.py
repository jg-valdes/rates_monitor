import logging
import os
from datetime import datetime, timezone

import requests

from rates.models import ExchangeRate

logger = logging.getLogger(__name__)

API_URL = "https://economia.awesomeapi.com.br/json/daily/{pair}/{days}"
_API_KEY = os.environ.get("AWESOMEAPI_KEY", "")


def fetch_and_store(pair, days: int = 90) -> tuple[int, int]:
    """
    Fetch last `days` days of rates for `pair` from awesomeapi and upsert into DB.
    `pair` must be a CurrencyPair instance.
    Returns (created_count, updated_count).

    Set AWESOMEAPI_KEY in the environment to authenticate requests and get a
    higher rate limit from the AwesomeAPI.
    """
    url = API_URL.format(pair=pair.api_code, days=days)
    headers = {"x-api-key": _API_KEY} if _API_KEY else {}
    logger.info(f"Fetching {days} days of {pair.code} from {url}")

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        logger.error(f"API request failed for {pair.code}: {exc}")
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
            logger.warning(f"Skipping malformed record for {pair.code}: {exc}")
            continue

        _, was_created = ExchangeRate.objects.update_or_create(
            pair=pair,
            date=rate_date,
            defaults={"rate": rate, "high": high, "low": low},
        )
        if was_created:
            created += 1
        else:
            updated += 1

    logger.info(f"{pair.code}: {created} created, {updated} updated")
    return created, updated
