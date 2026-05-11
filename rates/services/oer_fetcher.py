"""
Fetches exchange rate data from Open Exchange Rates (https://openexchangerates.org).

OER uses USD as the fixed base currency. To populate USD-BRL, UYU-USD, and
UYU-BRL pairs, we fetch BRL and UYU rates (both relative to USD) and compute:

  USD-BRL:   rates["BRL"]                  (BRL per 1 USD — direct)
  UYU-USD:   1 / rates["UYU"]              (USD per 1 UYU — inverted)
  UYU-BRL:   rates["BRL"] / rates["UYU"]  (BRL per 1 UYU — cross via USD)

Requires OPENEXCHANGERATES_APP_ID in settings (or env var).

Historical endpoint requires a paid OER plan.  When the free tier is detected
(HTTP 403 on historical), the fetcher silently falls back to latest-only mode.
"""

import logging
from datetime import date, timedelta

import requests
from django.conf import settings

from rates.models import CurrencyPair, ExchangeRate
from rates.services.market_calendar import is_weekend, mirror_missing_weekend_rates
from rates.services.oer_quota import can_make_request, estimate_historical_requests, record_request

BASE_URL = "https://openexchangerates.org/api"
_SYMBOLS = "BRL,UYU"

logger = logging.getLogger(__name__)


class OERError(Exception):
    pass


class OERQuotaExceeded(OERError):
    pass


def _app_id() -> str:
    app_id = getattr(settings, "OPENEXCHANGERATES_APP_ID", "")
    if not app_id:
        raise OERError("OPENEXCHANGERATES_APP_ID is not set")
    return app_id


def _get(url: str) -> dict:
    """Issue a GET request to OER and return parsed JSON. Raises OERError on failure."""
    try:
        resp = requests.get(url, params={"app_id": _app_id(), "symbols": _SYMBOLS}, timeout=10)
    except requests.RequestException as exc:
        raise OERError(f"Network error: {exc}") from exc
    record_request()
    if not resp.ok:
        if resp.status_code == 429:
            raise OERQuotaExceeded("Open Exchange Rates quota or rate limit was reached")
        raise OERError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    return resp.json()


def _fetch_latest() -> tuple[date, dict]:
    """Return (rate_date, rates_dict) for the most recent available rates."""
    data = _get(f"{BASE_URL}/latest.json")
    rate_date = date.fromtimestamp(data["timestamp"])
    return rate_date, data["rates"]


def _fetch_historical(target_date: date) -> dict:
    """Return rates_dict for *target_date*. Raises OERError on any failure."""
    data = _get(f"{BASE_URL}/historical/{target_date.isoformat()}.json")
    return data["rates"]


def compute_cross_rates(rates: dict) -> dict[str, float]:
    """
    Given an OER rates dict (USD as base), return cross rates for our three pairs.

    >>> compute_cross_rates({"BRL": 5.78, "UYU": 42.5})
    {'USD-BRL': 5.78, 'UYU-USD': 0.023529, 'UYU-BRL': 0.136}
    """
    brl_per_usd = float(rates["BRL"])
    uyu_per_usd = float(rates["UYU"])
    return {
        "USD-BRL": round(brl_per_usd, 4),
        "UYU-USD": round(1.0 / uyu_per_usd, 6),
        "UYU-BRL": round(brl_per_usd / uyu_per_usd, 6),
    }


def _upsert_rates(cross_rates: dict[str, float], rate_date: date) -> tuple[int, int]:
    created = updated = 0
    for pair_code, rate_value in cross_rates.items():
        try:
            pair = CurrencyPair.objects.get(code=pair_code, active=True)
        except CurrencyPair.DoesNotExist:
            logger.warning("OER: pair %s not found or inactive — skipping", pair_code)
            continue
        _, was_created = ExchangeRate.objects.update_or_create(
            pair=pair,
            date=rate_date,
            # OER doesn't provide intraday high/low in the free tier
            defaults={
                "rate": rate_value,
                "high": None,
                "low": None,
                "is_synthetic": False,
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1
    return created, updated


def fetch_and_store(days: int = 90, *, force: bool = False) -> tuple[int, int]:
    """
    Fetch OER rates and upsert cross rates for all three active pairs.

    - days == 1  → fetch latest rates only (always works, free tier).
    - days  > 1  → try to fetch historical rates for each business day in the
                   range.  On the first HTTP 403 (free-plan restriction) the
                   loop falls back to latest-only and returns early.

    Returns (total_created, total_updated).
    """
    total_created = total_updated = 0
    active_pairs = list(
        CurrencyPair.objects.filter(code__in=["USD-BRL", "UYU-USD", "UYU-BRL"], active=True)
    )
    today = date.today()
    synthetic_created, synthetic_updated = mirror_missing_weekend_rates(
        active_pairs, through_date=today
    )

    if is_weekend(today):
        logger.info("OER: weekend detected — skipped remote fetch and mirrored Friday values")
        return synthetic_created, synthetic_updated

    _app_id()

    if days > 1 and not getattr(settings, "OER_ALLOW_HISTORICAL", False):
        logger.info("OER: historical fetch disabled by policy — using latest only")
        days = 1

    requests_needed = 1 if days <= 1 else estimate_historical_requests(days, today)
    allowed, reason = can_make_request(requests_needed, ignore_interval=force)
    if not allowed:
        if days > 1:
            allowed_latest, _ = can_make_request(1, ignore_interval=force)
            if allowed_latest:
                logger.warning(
                    "OER: quota policy downgraded historical fetch to latest-only (%s)", reason
                )
                days = 1
            else:
                raise OERQuotaExceeded(reason)
        else:
            raise OERQuotaExceeded(reason)

    if days <= 1:
        rate_date, rates = _fetch_latest()
        cross = compute_cross_rates(rates)
        c, u = _upsert_rates(cross, rate_date)
        return c + synthetic_created, u + synthetic_updated

    for offset in range(days - 1, -1, -1):
        target = today - timedelta(days=offset)
        if target.weekday() >= 5:  # skip Sat/Sun — markets closed
            continue

        try:
            rates = _fetch_historical(target)
        except OERError as exc:
            msg = str(exc)
            if "HTTP 403" in msg:
                logger.warning(
                    "OER: historical endpoint requires a paid plan — falling back to latest only"
                )
                allowed_latest, latest_reason = can_make_request(1, ignore_interval=True)
                if not allowed_latest:
                    logger.warning(
                        "OER: latest fallback blocked by quota policy (%s)", latest_reason
                    )
                    return total_created + synthetic_created, total_updated + synthetic_updated
                rate_date, rates = _fetch_latest()
                cross = compute_cross_rates(rates)
                c, u = _upsert_rates(cross, rate_date)
                total_created += c
                total_updated += u
                return (
                    total_created + synthetic_created,
                    total_updated + synthetic_updated,
                )
            logger.warning("OER: skipping %s — %s", target, exc)
            continue

        cross = compute_cross_rates(rates)
        c, u = _upsert_rates(cross, target)
        total_created += c
        total_updated += u

    return total_created + synthetic_created, total_updated + synthetic_updated
