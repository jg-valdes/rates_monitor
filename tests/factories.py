import datetime

import factory
from factory.django import DjangoModelFactory

from rates.models import CurrencyPair, ExchangeRate, PairConfig, Purchase


class CurrencyPairFactory(DjangoModelFactory):
    class Meta:
        model = CurrencyPair
        django_get_or_create = ("code",)

    code = factory.Sequence(lambda n: f"T{n:02d}-BRL")
    name = factory.LazyAttribute(lambda o: f"Test {o.code}")
    api_code = factory.LazyAttribute(lambda o: o.code)
    active = True


class ExchangeRateFactory(DjangoModelFactory):
    class Meta:
        model = ExchangeRate

    pair = factory.SubFactory(CurrencyPairFactory)
    date = factory.Sequence(lambda n: datetime.date(2024, 1, 1) + datetime.timedelta(days=n))
    rate = 5.0
    high = None
    low = None


class PairConfigFactory(DjangoModelFactory):
    class Meta:
        model = PairConfig
        django_get_or_create = ("pair",)

    pair = factory.SubFactory(CurrencyPairFactory)
    monthly_budget = 1000.0
    threshold_strong_buy = 3.0
    threshold_moderate_buy = 1.5
    threshold_do_not_buy = -1.0
    alert_on_strong_buy = True
    alert_on_deviation_above = None
    alert_on_rate_above = None


class PurchaseFactory(DjangoModelFactory):
    class Meta:
        model = Purchase

    pair = factory.SubFactory(CurrencyPairFactory)
    date = datetime.date(2024, 6, 1)
    amount_spent = 100.0
    amount_received = 500.0
    note = ""
