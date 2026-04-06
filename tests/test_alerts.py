"""Tests for rates/services/alerts.py."""
from unittest.mock import MagicMock, patch

import pytest
import requests

from rates.services.alerts import _build_message, _send_telegram, check_and_send, send_test_alert


# ── Helpers ───────────────────────────────────────────────────────────────────

def _indicators(rate=5.5, deviation=3.5, momentum="up", ma30=5.3, ma90=5.0):
    return {
        "current_rate": rate,
        "deviation": deviation,
        "momentum": momentum,
        "ma30": ma30,
        "ma90": ma90,
    }


def _decision(signal="STRONG BUY", confidence="HIGH", suggested=1500.0, allocation=150):
    return {
        "signal": signal,
        "confidence": confidence,
        "suggested_amount": suggested,
        "allocation_pct": allocation,
    }


def _config(
    alert_on_strong_buy=False,
    alert_on_deviation_above=None,
    alert_on_rate_above=None,
):
    cfg = MagicMock()
    cfg.alert_on_strong_buy = alert_on_strong_buy
    cfg.alert_on_deviation_above = alert_on_deviation_above
    cfg.alert_on_rate_above = alert_on_rate_above
    return cfg


# ── _build_message ────────────────────────────────────────────────────────────

class TestBuildMessage:
    def test_contains_pair_name(self):
        msg = _build_message(_indicators(), _decision(), "USD-BRL")
        assert "USD-BRL" in msg

    def test_contains_rate(self):
        msg = _build_message(_indicators(rate=5.1234), _decision(), "X")
        assert "5.1234" in msg

    def test_contains_ma30_and_ma90(self):
        msg = _build_message(_indicators(ma30=5.3, ma90=5.0), _decision(), "X")
        assert "5.3000" in msg
        assert "5.0000" in msg

    def test_contains_suggested_amount(self):
        msg = _build_message(_indicators(), _decision(suggested=1500.0), "X")
        assert "1500" in msg

    def test_positive_deviation_uses_down_emoji(self):
        # positive deviation = rate above MA = cheaper to buy → 📉
        msg = _build_message(_indicators(deviation=3.5), _decision(), "X")
        assert "📉" in msg

    def test_negative_deviation_uses_up_emoji(self):
        msg = _build_message(_indicators(deviation=-2.0), _decision(), "X")
        assert "📈" in msg

    def test_strong_buy_emoji(self):
        msg = _build_message(_indicators(), _decision(signal="STRONG BUY"), "X")
        assert "🚀" in msg

    def test_do_not_buy_emoji(self):
        msg = _build_message(_indicators(), _decision(signal="DO NOT BUY"), "X")
        assert "🛑" in msg


# ── _send_telegram ────────────────────────────────────────────────────────────

class TestSendTelegram:
    def test_returns_false_when_no_token(self, settings):
        settings.TELEGRAM_BOT_TOKEN = ""
        settings.TELEGRAM_CHAT_ID = "123"
        assert _send_telegram("hello") is False

    def test_returns_false_when_no_chat_id(self, settings):
        settings.TELEGRAM_BOT_TOKEN = "tok"
        settings.TELEGRAM_CHAT_ID = ""
        assert _send_telegram("hello") is False

    def test_posts_to_telegram(self, settings):
        settings.TELEGRAM_BOT_TOKEN = "mytoken"
        settings.TELEGRAM_CHAT_ID = "999"
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        with patch("rates.services.alerts.requests.post", return_value=mock_resp) as mock_post:
            result = _send_telegram("hello")
        assert result is True
        url = mock_post.call_args[0][0]
        assert "mytoken" in url
        payload = mock_post.call_args[1]["json"]
        assert payload["chat_id"] == "999"
        assert payload["text"] == "hello"

    def test_raises_on_network_error(self, settings):
        settings.TELEGRAM_BOT_TOKEN = "tok"
        settings.TELEGRAM_CHAT_ID = "999"
        with patch("rates.services.alerts.requests.post", side_effect=requests.RequestException("timeout")):
            with pytest.raises(requests.RequestException):
                _send_telegram("hello")

    def test_raises_on_http_error(self, settings):
        settings.TELEGRAM_BOT_TOKEN = "tok"
        settings.TELEGRAM_CHAT_ID = "999"
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("401")
        with patch("rates.services.alerts.requests.post", return_value=mock_resp):
            with pytest.raises(requests.HTTPError):
                _send_telegram("hello")


# ── check_and_send ────────────────────────────────────────────────────────────

class TestCheckAndSend:
    def _send_patch(self, ok=True):
        return patch("rates.services.alerts._send_telegram", return_value=ok)

    def test_no_triggers_returns_empty(self):
        with self._send_patch():
            result = check_and_send(_indicators(), _decision(), _config(), "USD-BRL")
        assert result == []

    def test_strong_buy_trigger(self):
        cfg = _config(alert_on_strong_buy=True)
        with self._send_patch() as mock_send:
            result = check_and_send(_indicators(), _decision(signal="STRONG BUY"), cfg, "USD-BRL")
        assert len(result) == 1
        assert mock_send.called

    def test_no_strong_buy_trigger_on_other_signal(self):
        cfg = _config(alert_on_strong_buy=True)
        with self._send_patch() as mock_send:
            result = check_and_send(_indicators(), _decision(signal="NEUTRAL"), cfg, "USD-BRL")
        assert result == []
        assert not mock_send.called

    def test_deviation_threshold_trigger(self):
        cfg = _config(alert_on_deviation_above=2.0)
        with self._send_patch():
            result = check_and_send(_indicators(deviation=3.5), _decision(), cfg, "USD-BRL")
        assert len(result) == 1
        assert "Desviación" in result[0]

    def test_deviation_threshold_not_triggered_below(self):
        cfg = _config(alert_on_deviation_above=5.0)
        with self._send_patch():
            result = check_and_send(_indicators(deviation=3.5), _decision(), cfg, "USD-BRL")
        assert result == []

    def test_rate_threshold_trigger(self):
        cfg = _config(alert_on_rate_above=5.0)
        with self._send_patch():
            result = check_and_send(_indicators(rate=5.5), _decision(), cfg, "USD-BRL")
        assert len(result) == 1
        assert "Cotización" in result[0]

    def test_rate_threshold_none_skipped(self):
        cfg = _config(alert_on_rate_above=None)
        with self._send_patch():
            result = check_and_send(_indicators(rate=99.0), _decision(), cfg, "USD-BRL")
        assert result == []

    def test_multiple_triggers_sends_multiple_messages(self):
        cfg = _config(alert_on_strong_buy=True, alert_on_deviation_above=2.0, alert_on_rate_above=5.0)
        with self._send_patch() as mock_send:
            result = check_and_send(_indicators(rate=5.5, deviation=3.5), _decision(signal="STRONG BUY"), cfg, "X")
        assert len(result) == 3
        assert mock_send.call_count == 3

    def test_telegram_error_is_logged_not_raised(self):
        cfg = _config(alert_on_strong_buy=True)
        with patch("rates.services.alerts._send_telegram", side_effect=requests.RequestException("timeout")):
            # Should not raise
            result = check_and_send(_indicators(), _decision(signal="STRONG BUY"), cfg, "X")
        assert len(result) == 1  # message was triggered

    def test_pair_name_prefix_in_message(self):
        cfg = _config(alert_on_strong_buy=True)
        with self._send_patch():
            result = check_and_send(_indicators(), _decision(signal="STRONG BUY"), cfg, "USD-BRL")
        assert "[USD-BRL]" in result[0]


# ── send_test_alert ───────────────────────────────────────────────────────────

class TestSendTestAlert:
    def test_returns_result_of_send_telegram(self, settings):
        settings.TELEGRAM_BOT_TOKEN = "tok"
        settings.TELEGRAM_CHAT_ID = "999"
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        with patch("rates.services.alerts.requests.post", return_value=mock_resp):
            result = send_test_alert(_indicators(), _decision(), _config(), "USD-BRL")
        assert result is True

    def test_returns_false_when_not_configured(self, settings):
        settings.TELEGRAM_BOT_TOKEN = ""
        settings.TELEGRAM_CHAT_ID = ""
        result = send_test_alert(_indicators(), _decision(), _config(), "USD-BRL")
        assert result is False
