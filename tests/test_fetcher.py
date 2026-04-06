"""Tests for rates/services/fetcher.py."""
import datetime
from unittest.mock import MagicMock, patch

import pytest
import requests

from rates.services.fetcher import AwesomeApiError, _fetch_daily, fetch_and_store
from tests.factories import CurrencyPairFactory, ExchangeRateFactory


def _mock_response(data, status=200, ok=True):
    resp = MagicMock()
    resp.status_code = status
    resp.ok = ok
    resp.json.return_value = data
    resp.text = str(data)[:200]
    resp.raise_for_status = MagicMock()
    return resp


def _record(bid="5.1234", create_date="2024-06-01 12:00:00", timestamp=None, high="5.2", low="5.0"):
    rec = {"bid": bid, "high": high, "low": low}
    if create_date:
        rec["create_date"] = create_date
    if timestamp:
        rec["timestamp"] = timestamp
    return rec


# ── _fetch_daily ──────────────────────────────────────────────────────────────

class TestFetchDaily:
    def test_returns_json_on_success(self):
        data = [_record()]
        with patch("rates.services.fetcher.requests.get", return_value=_mock_response(data)):
            result = _fetch_daily("USD-BRL", 1)
        assert result == data

    def test_raises_on_non_ok(self):
        with patch("rates.services.fetcher.requests.get", return_value=_mock_response([], status=500, ok=False)):
            with pytest.raises(AwesomeApiError, match="HTTP 500"):
                _fetch_daily("USD-BRL", 1)

    def test_raises_on_network_error(self):
        with patch("rates.services.fetcher.requests.get", side_effect=requests.RequestException("timeout")):
            with pytest.raises(AwesomeApiError, match="Network error"):
                _fetch_daily("USD-BRL", 1)

    def test_retries_on_429_then_succeeds(self):
        rate_limit = _mock_response([], status=429, ok=False)
        rate_limit.ok = False
        success = _mock_response([_record()])
        with patch("rates.services.fetcher.requests.get", side_effect=[rate_limit, success]):
            with patch("rates.services.fetcher.time.sleep"):
                result = _fetch_daily("USD-BRL", 1)
        assert len(result) == 1

    def test_raises_after_max_retries_on_429(self):
        rate_limit = _mock_response([], status=429, ok=False)
        with patch("rates.services.fetcher.requests.get", return_value=rate_limit):
            with patch("rates.services.fetcher.time.sleep"):
                with pytest.raises(AwesomeApiError, match="Rate limit exceeded"):
                    _fetch_daily("USD-BRL", 1)


# ── fetch_and_store ───────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestFetchAndStore:
    def test_creates_new_rates(self):
        pair = CurrencyPairFactory(code="USD-BRL", api_code="USD-BRL")
        data = [_record(bid="5.1234", create_date="2024-06-01 12:00:00")]
        with patch("rates.services.fetcher._fetch_daily", return_value=data):
            created, updated = fetch_and_store(pair, days=1)
        assert created == 1
        assert updated == 0

    def test_updates_existing_rate(self):
        pair = CurrencyPairFactory(code="USD-BRL", api_code="USD-BRL")
        ExchangeRateFactory(pair=pair, date=datetime.date(2024, 6, 1), rate=5.0)
        data = [_record(bid="5.9999", create_date="2024-06-01 12:00:00")]
        with patch("rates.services.fetcher._fetch_daily", return_value=data):
            created, updated = fetch_and_store(pair, days=1)
        assert created == 0
        assert updated == 1

    def test_falls_back_to_timestamp_when_no_create_date(self):
        from rates.models import ExchangeRate

        pair = CurrencyPairFactory(code="USD-BRL", api_code="USD-BRL")
        # Use a known timestamp: 2024-01-15 UTC
        ts = str(int(datetime.datetime(2024, 1, 15, tzinfo=datetime.timezone.utc).timestamp()))
        data = [{"bid": "5.0", "high": "5.1", "low": "4.9", "timestamp": ts}]
        with patch("rates.services.fetcher._fetch_daily", return_value=data):
            created, _ = fetch_and_store(pair, days=1)
        assert created == 1
        assert ExchangeRate.objects.filter(pair=pair).count() == 1

    def test_skips_malformed_record(self):
        from rates.models import ExchangeRate

        pair = CurrencyPairFactory(code="USD-BRL", api_code="USD-BRL")
        data = [{"bid": "not-a-float", "create_date": "2024-06-01 12:00:00"}]
        with patch("rates.services.fetcher._fetch_daily", return_value=data):
            created, updated = fetch_and_store(pair, days=1)
        assert created == 0
        assert ExchangeRate.objects.filter(pair=pair).count() == 0

    def test_stores_high_and_low(self):
        from rates.models import ExchangeRate

        pair = CurrencyPairFactory(code="USD-BRL", api_code="USD-BRL")
        data = [_record(bid="5.0", high="5.3", low="4.8", create_date="2024-06-01 12:00:00")]
        with patch("rates.services.fetcher._fetch_daily", return_value=data):
            fetch_and_store(pair, days=1)
        rate = ExchangeRate.objects.get(pair=pair)
        assert rate.high == pytest.approx(5.3)
        assert rate.low == pytest.approx(4.8)

    def test_stores_none_for_missing_high_low(self):
        from rates.models import ExchangeRate

        pair = CurrencyPairFactory(code="USD-BRL", api_code="USD-BRL")
        data = [{"bid": "5.0", "high": "", "low": "", "create_date": "2024-06-01 12:00:00"}]
        with patch("rates.services.fetcher._fetch_daily", return_value=data):
            fetch_and_store(pair, days=1)
        rate = ExchangeRate.objects.get(pair=pair)
        assert rate.high is None
        assert rate.low is None

    def test_is_idempotent(self):
        from rates.models import ExchangeRate

        pair = CurrencyPairFactory(code="USD-BRL", api_code="USD-BRL")
        data = [_record(create_date="2024-06-01 12:00:00")]
        with patch("rates.services.fetcher._fetch_daily", return_value=data):
            fetch_and_store(pair, days=1)
            fetch_and_store(pair, days=1)
        assert ExchangeRate.objects.filter(pair=pair).count() == 1
