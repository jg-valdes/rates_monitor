"""
Fetches exchange rate data from AwesomeAPI (https://economia.awesomeapi.com.br).

Rate-limit notes
----------------
AwesomeAPI is free and requires no API key, but rate limits are reached quickly
if requests are made too frequently. The module handles this with:
  - Up to 3 retries with exponential backoff (2 s → 4 s) on HTTP 429.
  - A per-pair inter-request delay when fetching multiple pairs: add a
    time.sleep() between calls in the caller (see management/commands/fetch_rates.py).

Endpoint used
-------------
GET /json/daily/{pair_code}/{qty}
  Returns the last `qty` recorded daily rates, newest-first.
  Each record includes: bid, high, low, ask, create_date, timestamp.
"""

import logging
import time
from datetime import date

import requests

from rates.models import ExchangeRate

BASE_URL = "https://economia.awesomeapi.com.br"
_MAX_RETRIES = 3

logger = logging.getLogger(__name__)


class AwesomeApiError(Exception):
    pass


def _fetch_daily(pair_code: str, qty: int) -> list[dict]:
    """
    Return the last `qty` daily records for `pair_code` from AwesomeAPI.

    Retries up to _MAX_RETRIES times with exponential backoff on HTTP 429.
    Raises AwesomeApiError on unrecoverable errors.
    """
    url = f"{BASE_URL}/json/daily/{pair_code}/{qty}"

    for attempt in range(_MAX_RETRIES):
        if attempt:
            wait = 2**attempt  # 2 s, then 4 s
            logger.warning(
                "AwesomeAPI rate limit hit for %s — retrying in %d s (attempt %d/%d)",
                pair_code, wait, attempt + 1, _MAX_RETRIES,
            )
            time.sleep(wait)

        try:
            resp = requests.get(url, timeout=10)
        except requests.RequestException as exc:
            raise AwesomeApiError(f"Network error fetching {pair_code}: {exc}") from exc

        if resp.status_code == 429:
            continue  # handled above with backoff

        if not resp.ok:
            raise AwesomeApiError(
                f"HTTP {resp.status_code} fetching {pair_code}: {resp.text[:200]}"
            )

        return resp.json()

    raise AwesomeApiError(
        f"Rate limit exceeded for {pair_code} after {_MAX_RETRIES} attempts"
    )


def fetch_and_store(pair, days: int = 90) -> tuple[int, int]:
    """
    Fetch the last `days` daily rates for `pair` from AwesomeAPI and upsert
    them into ExchangeRate. Returns (created_count, updated_count).

    `days` is passed directly as the record count to the API. AwesomeAPI skips
    weekends and holidays, so the actual date span will be slightly longer than
    `days` calendar days.

    The pair's `api_code` field is used as the pair identifier in the URL
    (e.g. "USD-BRL").
    """
    records = _fetch_daily(pair.api_code, days)
    created = updated = 0

    for rec in records:
        try:
            if rec.get("create_date"):
                rate_date = date.fromisoformat(rec["create_date"][:10])
            else:
                rate_date = date.fromtimestamp(int(rec["timestamp"]))
            rate_value = round(float(rec["bid"]), 4)
            high = float(rec["high"]) if rec.get("high") else None
            low = float(rec["low"]) if rec.get("low") else None
        except (KeyError, ValueError) as exc:
            logger.warning("Skipping malformed record for %s: raw record: %s; Error: %s", pair.code, rec, exc)
            continue

        _, was_created = ExchangeRate.objects.update_or_create(
            pair=pair,
            date=rate_date,
            defaults={"rate": rate_value, "high": high, "low": low},
        )
        if was_created:
            created += 1
        else:
            updated += 1

    logger.info("%s: %d created, %d updated", pair.code, created, updated)
    return created, updated
