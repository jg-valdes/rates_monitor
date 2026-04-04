import logging
import os
from datetime import date, timedelta

from rates.models import ExchangeRate
from rates.services.openexchangeapi import OpenExchangeApi, OpenExchangeApiError

logger = logging.getLogger(__name__)

# Client is initialized once per process; reads the key from the environment.
_client = OpenExchangeApi(api_key=os.environ.get("OPEN_EXCHANGE_RATES_APP_ID") or None)

# Per-process cache: avoids redundant API calls when multiple pairs are
# fetched on the same date within the same management-command run.
_rate_cache: dict[str, dict[str, float]] = {}


def _rates_for_date(date_str: str) -> dict[str, float]:
    """Return the full USD-based rate dict for a given date, using cache when possible."""
    if date_str not in _rate_cache:
        response = _client.get_historical(date_str)
        _rate_cache[date_str] = response.rates
    return _rate_cache[date_str]


def fetch_and_store(pair, days: int = 90) -> tuple[int, int]:
    """
    Fetch the last `days` calendar days of rates for `pair` from Open Exchange Rates
    and upsert into the DB.  `pair` must be a CurrencyPair instance.
    Returns (created_count, updated_count).

    All rates are derived from USD-based cross-rates:
        pair_rate = rates[quote_currency] / rates[base_currency]

    API responses are cached per date within the same process run, so fetching
    multiple pairs together only makes one HTTP call per unique date.
    """
    base_curr = pair.base_currency
    quote_curr = pair.quote_currency
    today = date.today()
    created = updated = 0

    for i in range(days - 1, -1, -1):
        rate_date = today - timedelta(days=i)
        date_str = rate_date.isoformat()

        try:
            rates = _rates_for_date(date_str)
        except OpenExchangeApiError as exc:
            # Future dates or weekends may not have data yet — skip gracefully.
            logger.warning(f"Skipping {pair.code} on {date_str}: {exc}")
            continue
        except Exception as exc:
            logger.error(f"API request failed for {pair.code}: {exc}")
            raise

        usd_to_base = rates.get(base_curr)
        usd_to_quote = rates.get(quote_curr)
        if not usd_to_base or not usd_to_quote:
            logger.warning(f"Missing rate for {pair.code} on {date_str}, skipping")
            continue

        rate_value = round(usd_to_quote / usd_to_base, 4)

        _, was_created = ExchangeRate.objects.update_or_create(
            pair=pair,
            date=rate_date,
            defaults={"rate": rate_value, "high": None, "low": None},
        )
        if was_created:
            created += 1
        else:
            updated += 1

    logger.info(f"{pair.code}: {created} created, {updated} updated")
    return created, updated
