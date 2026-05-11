from unittest.mock import MagicMock, patch

import pytest
import requests

from rates.services.oer_fetcher import OERError
from rates.services.oer_usage import fetch_usage_summary

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _oer_app_id(settings):
    settings.OPENEXCHANGERATES_APP_ID = "test-key-123"


def _usage_response(status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.ok = status < 400
    resp.text = "error"
    resp.json.return_value = {
        "status": status,
        "data": {
            "app_id": "test-key-123",
            "status": "active",
            "plan": {
                "name": "Enterprise",
                "quota": "100,000 requests/month",
                "update_frequency": "30-minute",
                "features": {
                    "base": True,
                    "symbols": True,
                    "experimental": True,
                    "time-series": True,
                    "convert": False,
                },
            },
            "usage": {
                "requests": 54524,
                "requests_quota": 100000,
                "requests_remaining": 45476,
                "days_elapsed": 16,
                "days_remaining": 14,
                "daily_average": 2842,
            },
        },
    }
    return resp


class TestFetchUsageSummary:
    def test_normalizes_usage_payload(self):
        with patch("rates.services.oer_usage.requests.get", return_value=_usage_response()):
            result = fetch_usage_summary()

        assert result["plan_name"] == "Enterprise"
        assert result["requests_used"] == 54524
        assert result["requests_quota"] == 100000
        assert result["requests_remaining"] == 45476
        assert result["usage_pct"] == pytest.approx(54.52)
        assert result["features"]["convert"] is False

    def test_raises_on_missing_app_id(self, settings):
        settings.OPENEXCHANGERATES_APP_ID = ""
        with pytest.raises(OERError, match="APP_ID"):
            fetch_usage_summary()

    def test_raises_on_network_error(self):
        with patch(
            "rates.services.oer_usage.requests.get",
            side_effect=requests.RequestException("timeout"),
        ):
            with pytest.raises(OERError, match="Network error"):
                fetch_usage_summary()

    def test_raises_on_http_error(self):
        with patch(
            "rates.services.oer_usage.requests.get",
            return_value=_usage_response(status=500),
        ):
            with pytest.raises(OERError, match="HTTP 500"):
                fetch_usage_summary()
