"""Tests for rates/services/oer_fetcher.py."""
import datetime
from unittest.mock import MagicMock, patch

import pytest
import requests

from rates.services.oer_fetcher import OERError, compute_cross_rates, fetch_and_store
from tests.factories import CurrencyPairFactory, ExchangeRateFactory

pytestmark = pytest.mark.django_db  # all tests need DB access


@pytest.fixture(autouse=True)
def _oer_app_id(settings):
    """Provide a fake OER app ID so all tests pass the _app_id() guard."""
    settings.OPENEXCHANGERATES_APP_ID = "test-key-123"


# ── helpers ───────────────────────────────────────────────────────────────────

def _oer_response(rates: dict, timestamp: int = 1700000000, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.ok = status < 400
    resp.json.return_value = {"timestamp": timestamp, "base": "USD", "rates": rates}
    resp.text = str(rates)[:200]
    return resp


_SAMPLE_RATES = {"BRL": 5.78, "UYU": 42.5}
_SAMPLE_TS = 1700000000  # 2023-11-14 22:13:20 UTC


# ── compute_cross_rates ───────────────────────────────────────────────────────

class TestComputeCrossRates:
    def test_usd_brl_is_direct(self):
        result = compute_cross_rates({"BRL": 5.78, "UYU": 42.5})
        assert result["USD-BRL"] == pytest.approx(5.78, abs=1e-4)

    def test_uyu_usd_is_inverted(self):
        result = compute_cross_rates({"BRL": 5.78, "UYU": 42.5})
        assert result["UYU-USD"] == pytest.approx(1 / 42.5, abs=1e-6)

    def test_uyu_brl_is_cross(self):
        result = compute_cross_rates({"BRL": 5.78, "UYU": 42.5})
        assert result["UYU-BRL"] == pytest.approx(5.78 / 42.5, abs=1e-6)

    def test_returns_all_three_pairs(self):
        result = compute_cross_rates({"BRL": 5.0, "UYU": 40.0})
        assert set(result.keys()) == {"USD-BRL", "UYU-USD", "UYU-BRL"}


# ── fetch_and_store (latest, days=1) ─────────────────────────────────────────

class TestFetchAndStoreLatest:
    def setup_method(self):
        self.usd_brl = CurrencyPairFactory(code="USD-BRL", api_code="USD-BRL")
        self.uyu_usd = CurrencyPairFactory(code="UYU-USD", api_code="UYU-USD")
        self.uyu_brl = CurrencyPairFactory(code="UYU-BRL", api_code="UYU-BRL")

    def test_creates_rates_for_all_three_pairs(self):
        from rates.models import ExchangeRate

        with patch("rates.services.oer_fetcher.requests.get",
                   return_value=_oer_response(_SAMPLE_RATES)):
            created, updated = fetch_and_store(days=1)

        assert created == 3
        assert updated == 0
        assert ExchangeRate.objects.count() == 3

    def test_upserts_on_second_call(self):
        with patch("rates.services.oer_fetcher.requests.get",
                   return_value=_oer_response(_SAMPLE_RATES)):
            fetch_and_store(days=1)
            created, updated = fetch_and_store(days=1)

        assert created == 0
        assert updated == 3

    def test_stored_rates_match_cross_calculation(self):
        from rates.models import ExchangeRate

        with patch("rates.services.oer_fetcher.requests.get",
                   return_value=_oer_response(_SAMPLE_RATES)):
            fetch_and_store(days=1)

        rate_usd_brl = ExchangeRate.objects.get(pair=self.usd_brl).rate
        rate_uyu_usd = ExchangeRate.objects.get(pair=self.uyu_usd).rate
        rate_uyu_brl = ExchangeRate.objects.get(pair=self.uyu_brl).rate

        assert rate_usd_brl == pytest.approx(5.78, abs=1e-4)
        assert rate_uyu_usd == pytest.approx(1 / 42.5, abs=1e-6)
        assert rate_uyu_brl == pytest.approx(5.78 / 42.5, abs=1e-6)

    def test_high_and_low_stored_as_none(self):
        from rates.models import ExchangeRate

        with patch("rates.services.oer_fetcher.requests.get",
                   return_value=_oer_response(_SAMPLE_RATES)):
            fetch_and_store(days=1)

        for rate in ExchangeRate.objects.all():
            assert rate.high is None
            assert rate.low is None

    def test_raises_on_missing_app_id(self, settings):
        settings.OPENEXCHANGERATES_APP_ID = ""
        with pytest.raises(OERError, match="APP_ID"):
            fetch_and_store(days=1)

    def test_raises_on_network_error(self):
        with patch("rates.services.oer_fetcher.requests.get",
                   side_effect=requests.RequestException("timeout")):
            with pytest.raises(OERError, match="Network error"):
                fetch_and_store(days=1)

    def test_raises_on_non_ok_response(self):
        with patch("rates.services.oer_fetcher.requests.get",
                   return_value=_oer_response({}, status=500)):
            with pytest.raises(OERError, match="HTTP 500"):
                fetch_and_store(days=1)

    def test_skips_inactive_pairs(self):
        from rates.models import ExchangeRate

        self.uyu_brl.active = False
        self.uyu_brl.save()

        with patch("rates.services.oer_fetcher.requests.get",
                   return_value=_oer_response(_SAMPLE_RATES)):
            created, _ = fetch_and_store(days=1)

        assert created == 2
        assert ExchangeRate.objects.count() == 2


# ── fetch_and_store (historical, days > 1) ───────────────────────────────────

class TestFetchAndStoreHistorical:
    def setup_method(self):
        CurrencyPairFactory(code="USD-BRL", api_code="USD-BRL")
        CurrencyPairFactory(code="UYU-USD", api_code="UYU-USD")
        CurrencyPairFactory(code="UYU-BRL", api_code="UYU-BRL")

    def test_falls_back_to_latest_on_403(self):
        """Free-plan users get a 403 on historical — we fall back to latest."""
        from rates.models import ExchangeRate

        forbidden = _oer_response({}, status=403)
        latest_ok = _oer_response(_SAMPLE_RATES, timestamp=_SAMPLE_TS)

        with patch("rates.services.oer_fetcher.requests.get",
                   side_effect=[forbidden, latest_ok]):
            created, updated = fetch_and_store(days=3)

        assert created + updated == 3
        assert ExchangeRate.objects.count() == 3

    def test_historical_stores_rates_per_date(self):
        from rates.models import ExchangeRate

        # Two weekday calls succeed
        hist1 = _oer_response({"BRL": 5.5, "UYU": 40.0})
        hist2 = _oer_response({"BRL": 5.6, "UYU": 41.0})

        import datetime as dt

        today = dt.date.today()
        # We need exactly 2 weekdays in last 2 days — patch date.today instead
        with patch("rates.services.oer_fetcher.requests.get", side_effect=[hist1, hist2]):
            with patch("rates.services.oer_fetcher.date") as mock_date:
                # Force "today" to be a Wednesday so both offset-1 and offset-0 are weekdays
                mock_date.today.return_value = dt.date(2024, 6, 5)  # Wednesday
                mock_date.side_effect = lambda *a, **kw: dt.date(*a, **kw)
                fetch_and_store(days=2)

        assert ExchangeRate.objects.count() == 6  # 3 pairs × 2 dates

    def test_skips_malformed_day_and_continues(self):
        """An error on one day should not abort the whole run."""
        from rates.models import ExchangeRate

        bad = MagicMock()
        bad.ok = False
        bad.status_code = 500
        bad.text = "server error"

        good = _oer_response(_SAMPLE_RATES)

        import datetime as dt

        with patch("rates.services.oer_fetcher.requests.get", side_effect=[bad, good]):
            with patch("rates.services.oer_fetcher.date") as mock_date:
                mock_date.today.return_value = dt.date(2024, 6, 5)
                mock_date.side_effect = lambda *a, **kw: dt.date(*a, **kw)
                created, updated = fetch_and_store(days=2)

        # Only the second (successful) day's 3 pairs stored
        assert ExchangeRate.objects.count() == 3
