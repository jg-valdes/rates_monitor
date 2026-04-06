"""Tests for rates/services/cross_pair.py."""
import datetime

import pytest

from rates.services.cross_pair import compute_cross_pair
from tests.factories import CurrencyPairFactory, ExchangeRateFactory


def _create_pair_with_rate(code, rate):
    pair = CurrencyPairFactory(code=code, name=code, api_code=code)
    ExchangeRateFactory(pair=pair, date=datetime.date(2024, 6, 1), rate=rate)
    return pair


@pytest.mark.django_db
class TestComputeCrossPair:
    def test_returns_none_when_no_data(self):
        assert compute_cross_pair() is None

    def test_returns_none_when_missing_one_pair(self):
        _create_pair_with_rate("UYU-BRL", 0.2)
        _create_pair_with_rate("UYU-USD", 0.04)
        # USD-BRL missing
        assert compute_cross_pair() is None

    def test_returns_none_when_pair_inactive(self):
        # The seed migration creates UYU-BRL as active; deactivate it directly.
        from rates.models import CurrencyPair

        pair = CurrencyPair.objects.get(code="UYU-BRL")
        pair.active = False
        pair.save()
        ExchangeRateFactory(pair=pair, date=datetime.date(2024, 6, 1), rate=0.2)
        _create_pair_with_rate("UYU-USD", 0.04)
        _create_pair_with_rate("USD-BRL", 5.5)
        assert compute_cross_pair() is None

    def test_direct_route_wins(self):
        # direct = UYU-BRL = 0.25
        # indirect = UYU-USD * USD-BRL = 0.04 * 5.5 = 0.22
        _create_pair_with_rate("UYU-BRL", 0.25)
        _create_pair_with_rate("UYU-USD", 0.04)
        _create_pair_with_rate("USD-BRL", 5.5)
        result = compute_cross_pair()
        assert result is not None
        assert result["best_route"] == "direct"
        assert result["direct_rate"] == pytest.approx(0.25, rel=1e-4)
        assert result["indirect_rate"] == pytest.approx(0.22, rel=1e-4)
        assert result["advantage_pct"] > 0

    def test_indirect_route_wins(self):
        # direct = UYU-BRL = 0.20
        # indirect = 0.04 * 5.5 = 0.22
        _create_pair_with_rate("UYU-BRL", 0.20)
        _create_pair_with_rate("UYU-USD", 0.04)
        _create_pair_with_rate("USD-BRL", 5.5)
        result = compute_cross_pair()
        assert result is not None
        assert result["best_route"] == "indirect"
        assert result["advantage_pct"] > 0

    def test_result_keys_present(self):
        _create_pair_with_rate("UYU-BRL", 0.22)
        _create_pair_with_rate("UYU-USD", 0.04)
        _create_pair_with_rate("USD-BRL", 5.5)
        result = compute_cross_pair()
        for key in ("direct_rate", "indirect_rate", "best_route", "advantage_pct", "uyu_brl", "uyu_usd", "usd_brl"):
            assert key in result

    def test_uses_most_recent_rate(self):
        pair = CurrencyPairFactory(code="UYU-BRL")
        ExchangeRateFactory(pair=pair, date=datetime.date(2024, 1, 1), rate=0.10)
        ExchangeRateFactory(pair=pair, date=datetime.date(2024, 6, 1), rate=0.25)
        _create_pair_with_rate("UYU-USD", 0.04)
        _create_pair_with_rate("USD-BRL", 5.5)
        result = compute_cross_pair()
        assert result["uyu_brl"] == pytest.approx(0.25, rel=1e-4)
