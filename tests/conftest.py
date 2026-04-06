import datetime

import pytest
from django.core import signing
from django.test import Client

from tests.factories import (
    CurrencyPairFactory,
    ExchangeRateFactory,
    PairConfigFactory,
)


@pytest.fixture(autouse=True)
def disable_passcode(settings):
    """Ensure the passcode gate is off for all tests unless a test overrides it."""
    settings.ACCESS_PASSCODE = ""


@pytest.fixture
def client():
    """Django test client with no passcode (ACCESS_PASSCODE is empty in test settings)."""
    return Client()


@pytest.fixture
def pair(db):
    return CurrencyPairFactory(code="USD-BRL", name="Dólar / Real")


@pytest.fixture
def config(pair):
    return PairConfigFactory(pair=pair)


@pytest.fixture
def rates(pair):
    """90 exchange rates, ascending, with a slight upward trend."""
    base = datetime.date(2024, 1, 1)
    return [
        ExchangeRateFactory(pair=pair, date=base + datetime.timedelta(days=i), rate=5.0 + i * 0.01)
        for i in range(90)
    ]


@pytest.fixture
def auth_client(settings):
    """Client with a valid rm_access cookie (passcode enabled)."""
    settings.ACCESS_PASSCODE = "secret"
    c = Client()
    token = signing.dumps("ok")
    c.cookies["rm_access"] = token
    return c
