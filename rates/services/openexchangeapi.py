"""
OpenExchangeAPI Python SDK
Minimal, idiomatic Python client for https://openexchangeapi.com
- All endpoints supported
- API key is optional
- Returns Python dataclasses for all responses
- Fully documented with docstrings
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

import requests

BASE_URL = "https://api.openexchangeapi.com"


class OpenExchangeApiError(Exception):
    """Exception for OpenExchangeAPI errors."""

    pass


@dataclass
class GetLatestRatesResponse:
    """Response for /v1/latest endpoint (standard precision rates)."""

    base: str
    date: str
    timestamp: int
    rates: Dict[str, float]


@dataclass
class GetLatestPreciseRatesResponse:
    """Response for /v1/latest-precise endpoint (high precision rates as strings)."""

    base: str
    date: str
    timestamp: int
    rates: Dict[str, str]

    def rates_decimal(self) -> Dict[str, float]:
        """Returns rates as floats (parsed from strings)."""
        return {k: float(v) for k, v in self.rates.items()}


@dataclass
class GetHistoricalRatesResponse:
    """Response for /v1/historical/{date} endpoint (standard precision)."""

    base: str
    date: str
    timestamp: int
    rates: Dict[str, float]


@dataclass
class GetHistoricalPreciseRatesResponse:
    """Response for /v1/historical-precise/{date} endpoint (high precision rates as strings)."""

    base: str
    date: str
    timestamp: int
    rates: Dict[str, str]

    def rates_decimal(self) -> Dict[str, float]:
        """Returns rates as floats (parsed from strings)."""
        return {k: float(v) for k, v in self.rates.items()}


@dataclass
class ConvertCurrencyResponse:
    """Response for /v1/convert endpoint (standard precision)."""

    from_: str = field(metadata={"data_key": "from"})
    to: str
    amount: float
    rate: float
    result: float


@dataclass
class ConvertCurrencyPreciseResponse:
    """Response for /v1/convert-precise endpoint (high precision as strings)."""

    from_: str = field(metadata={"data_key": "from"})
    to: str
    amount: str
    rate: str
    result: str

    def amount_decimal(self) -> float:
        """Amount as float (parsed from string)."""
        return float(self.amount)

    def rate_decimal(self) -> float:
        """Rate as float (parsed from string)."""
        return float(self.rate)

    def result_decimal(self) -> float:
        """Result as float (parsed from string)."""
        return float(self.result)


@dataclass
class Currency:
    """Currency object returned by /v1/currencies and /v1/currencies/{code}."""

    code: str
    name: str
    type: str
    digits: int
    symbol: str
    iso_num: int
    meta: Optional[Dict[str, Any]] = None


@dataclass
class GetCurrencyResponse:
    """Response for /v1/currencies/{code} endpoint."""

    currency: Currency


class OpenExchangeApi:
    """
    Minimal OpenExchangeAPI client for Python.
    All methods map to OpenExchangeAPI endpoints and return dataclasses.
    API key is optional for public endpoints.
    """

    def __init__(self, api_key: Optional[str] = None, base_url: str = BASE_URL):
        """
        :param api_key: Your OpenExchangeAPI key (optional)
        :param base_url: API base URL (default: https://api.openexchangeapi.com)
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        """Internal GET helper."""
        url = self.base_url + path
        params = params or {}
        if self.api_key:
            params["app_id"] = self.api_key
        resp = requests.get(url, params=params)
        if not resp.ok:
            raise OpenExchangeApiError(resp.text)
        return resp.json()

    def get_latest(self, base: Optional[str] = None) -> GetLatestRatesResponse:
        """Get latest exchange rates."""
        data = self._get("/v1/latest", {"base": base} if base else None)
        return GetLatestRatesResponse(**data)

    def get_latest_precise(self, base: Optional[str] = None) -> GetLatestPreciseRatesResponse:
        """Get latest exchange rates (high precision)."""
        data = self._get("/v1/latest-precise", {"base": base} if base else None)
        return GetLatestPreciseRatesResponse(**data)

    def get_historical(self, date: str, base: Optional[str] = None) -> GetHistoricalRatesResponse:
        """Get historical exchange rates for a specific date."""
        if not date:
            raise ValueError("date is required")
        data = self._get(f"/v1/historical/{date}", {"base": base} if base else None)
        return GetHistoricalRatesResponse(**data)

    def get_historical_precise(
        self, date: str, base: Optional[str] = None
    ) -> GetHistoricalPreciseRatesResponse:
        """Get historical exchange rates (high precision) for a specific date."""
        if not date:
            raise ValueError("date is required")
        data = self._get(f"/v1/historical-precise/{date}", {"base": base} if base else None)
        return GetHistoricalPreciseRatesResponse(**data)

    def convert(self, from_: str, to: str, amount: float) -> ConvertCurrencyResponse:
        """Convert currency (standard precision)."""
        if not from_ or not to or amount is None:
            raise ValueError("from, to, and amount are required")
        data = self._get("/v1/convert", {"from": from_, "to": to, "amount": amount})
        data["from_"] = data.pop("from")
        return ConvertCurrencyResponse(**data)

    def convert_precise(
        self, from_: str, to: str, amount: Union[float, str]
    ) -> ConvertCurrencyPreciseResponse:
        """Convert currency (high precision)."""
        if not from_ or not to or amount is None:
            raise ValueError("from, to, and amount are required")
        data = self._get("/v1/convert-precise", {"from": from_, "to": to, "amount": amount})
        data["from_"] = data.pop("from")
        return ConvertCurrencyPreciseResponse(**data)

    def list_currencies(self, type_: Optional[str] = None) -> List[Currency]:
        """List all supported currencies."""
        data = self._get("/v1/currencies", {"type": type_} if type_ else None)
        return [Currency(**c) for c in data]

    def get_currency(self, code: str) -> GetCurrencyResponse:
        """Get currency by code."""
        if not code:
            raise ValueError("code is required")
        data = self._get(f"/v1/currencies/{code}")
        return GetCurrencyResponse(currency=Currency(**data["currency"]))
