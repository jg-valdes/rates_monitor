import datetime

import pytest

from rates.models import ExchangeRate
from rates.services.market_calendar import mirror_missing_weekend_rates
from tests.factories import CurrencyPairFactory, ExchangeRateFactory


@pytest.mark.django_db
class TestMirrorMissingWeekendRates:
    def test_creates_saturday_and_sunday_from_friday(self):
        pair = CurrencyPairFactory(code="USD-BRL")
        ExchangeRateFactory(pair=pair, date=datetime.date(2024, 6, 7), rate=5.25)  # Friday

        created, updated = mirror_missing_weekend_rates(
            [pair], through_date=datetime.date(2024, 6, 9)
        )

        assert created == 2
        assert updated == 0
        saturday = ExchangeRate.objects.get(pair=pair, date=datetime.date(2024, 6, 8))
        sunday = ExchangeRate.objects.get(pair=pair, date=datetime.date(2024, 6, 9))
        assert saturday.rate == pytest.approx(5.25)
        assert sunday.rate == pytest.approx(5.25)
        assert saturday.is_synthetic is True
        assert sunday.is_synthetic is True

    def test_does_not_fill_when_a_weekday_gap_exists(self):
        pair = CurrencyPairFactory(code="USD-BRL")
        ExchangeRateFactory(pair=pair, date=datetime.date(2024, 6, 6), rate=5.10)  # Thursday

        created, updated = mirror_missing_weekend_rates(
            [pair], through_date=datetime.date(2024, 6, 9)
        )

        assert created == 0
        assert updated == 0
        assert not ExchangeRate.objects.filter(pair=pair, date=datetime.date(2024, 6, 8)).exists()
