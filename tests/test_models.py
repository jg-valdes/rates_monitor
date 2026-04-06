import datetime

import pytest

from tests.factories import CurrencyPairFactory, ExchangeRateFactory, PairConfigFactory, PurchaseFactory


@pytest.mark.django_db
class TestCurrencyPair:
    def test_str(self):
        pair = CurrencyPairFactory(code="USD-BRL", name="Dólar / Real")
        assert str(pair) == "USD-BRL — Dólar / Real"

    def test_slug(self):
        pair = CurrencyPairFactory(code="USD-BRL")
        assert pair.slug == "usd-brl"

    def test_base_currency(self):
        pair = CurrencyPairFactory(code="USD-BRL")
        assert pair.base_currency == "USD"

    def test_quote_currency(self):
        pair = CurrencyPairFactory(code="USD-BRL")
        assert pair.quote_currency == "BRL"


@pytest.mark.django_db
class TestExchangeRate:
    def test_str(self):
        pair = CurrencyPairFactory(code="USD-BRL")
        rate = ExchangeRateFactory(pair=pair, date=datetime.date(2024, 3, 1), rate=5.1234)
        assert str(rate) == "USD-BRL 2024-03-01: 5.1234"

    def test_unique_constraint(self):
        from django.db import IntegrityError

        pair = CurrencyPairFactory(code="UC-TST")
        ExchangeRateFactory(pair=pair, date=datetime.date(2024, 1, 1), rate=5.0)
        with pytest.raises(IntegrityError):
            ExchangeRateFactory(pair=pair, date=datetime.date(2024, 1, 1), rate=5.1)


@pytest.mark.django_db
class TestPurchase:
    def test_effective_rate(self):
        p = PurchaseFactory(amount_spent=100.0, amount_received=550.0)
        assert p.effective_rate == pytest.approx(5.5, rel=1e-4)

    def test_effective_rate_zero_spent(self):
        p = PurchaseFactory(amount_spent=0.0, amount_received=500.0)
        assert p.effective_rate == 0.0

    def test_str(self):
        pair = CurrencyPairFactory(code="USD-BRL")
        p = PurchaseFactory(
            pair=pair,
            date=datetime.date(2024, 6, 1),
            amount_spent=100.0,
            amount_received=500.0,
        )
        assert "USD-BRL" in str(p)
        assert "2024-06-01" in str(p)


@pytest.mark.django_db
class TestPairConfig:
    def test_str(self):
        pair = CurrencyPairFactory(code="USD-BRL")
        cfg = PairConfigFactory(pair=pair)
        assert str(cfg) == "Config: USD-BRL"

    def test_defaults(self):
        cfg = PairConfigFactory()
        assert cfg.monthly_budget == 1000.0
        assert cfg.threshold_strong_buy == 3.0
        assert cfg.threshold_moderate_buy == 1.5
        assert cfg.threshold_do_not_buy == -1.0
        assert cfg.alert_on_strong_buy is True
        assert cfg.alert_on_deviation_above is None
        assert cfg.alert_on_rate_above is None
