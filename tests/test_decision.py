"""Tests for rates/services/decision.py — pure functions, no DB needed."""
from unittest.mock import MagicMock

import pytest

from rates.services.decision import (
    DO_NOT_BUY,
    MODERATE_BUY,
    NEUTRAL,
    STRONG_BUY,
    build_decision,
    get_confidence,
    get_signal,
)


def _config(strong=3.0, moderate=1.5, do_not_buy=-1.0, budget=1000.0):
    cfg = MagicMock()
    cfg.threshold_strong_buy = strong
    cfg.threshold_moderate_buy = moderate
    cfg.threshold_do_not_buy = do_not_buy
    cfg.monthly_budget = budget
    return cfg


class TestGetSignal:
    def test_strong_buy(self):
        assert get_signal(3.5, _config()) == STRONG_BUY

    def test_strong_buy_at_boundary(self):
        # deviation == threshold_strong_buy is NOT > so it falls to MODERATE_BUY
        assert get_signal(3.0, _config()) == MODERATE_BUY

    def test_moderate_buy(self):
        assert get_signal(2.0, _config()) == MODERATE_BUY

    def test_moderate_buy_at_boundary(self):
        # deviation == threshold_moderate_buy is NOT > so it falls to NEUTRAL
        assert get_signal(1.5, _config()) == NEUTRAL

    def test_neutral(self):
        assert get_signal(0.0, _config()) == NEUTRAL

    def test_neutral_at_lower_boundary(self):
        # deviation == threshold_do_not_buy → NEUTRAL (>= check)
        assert get_signal(-1.0, _config()) == NEUTRAL

    def test_do_not_buy(self):
        assert get_signal(-2.0, _config()) == DO_NOT_BUY


class TestGetConfidence:
    def test_strong_buy_up_is_high(self):
        assert get_confidence(STRONG_BUY, "up") == "HIGH"

    def test_strong_buy_neutral_is_medium(self):
        assert get_confidence(STRONG_BUY, "neutral") == "MEDIUM"

    def test_strong_buy_down_is_medium(self):
        assert get_confidence(STRONG_BUY, "down") == "MEDIUM"

    def test_moderate_buy_up_is_medium(self):
        assert get_confidence(MODERATE_BUY, "up") == "MEDIUM"

    def test_moderate_buy_neutral_is_medium(self):
        assert get_confidence(MODERATE_BUY, "neutral") == "MEDIUM"

    def test_moderate_buy_down_is_low(self):
        assert get_confidence(MODERATE_BUY, "down") == "LOW"

    def test_neutral_is_low(self):
        assert get_confidence(NEUTRAL, "up") == "LOW"

    def test_do_not_buy_is_low(self):
        assert get_confidence(DO_NOT_BUY, "up") == "LOW"


class TestBuildDecision:
    def _indicators(self, deviation, momentum="neutral"):
        return {"deviation": deviation, "momentum": momentum}

    def test_strong_buy_allocation(self):
        result = build_decision(self._indicators(4.0), _config(budget=1000.0))
        assert result["signal"] == STRONG_BUY
        assert result["suggested_amount"] == pytest.approx(1500.0)
        assert result["allocation_pct"] == 150

    def test_moderate_buy_allocation(self):
        result = build_decision(self._indicators(2.0), _config(budget=1000.0))
        assert result["signal"] == MODERATE_BUY
        assert result["suggested_amount"] == pytest.approx(1000.0)
        assert result["allocation_pct"] == 100

    def test_neutral_allocation(self):
        result = build_decision(self._indicators(0.0), _config(budget=1000.0))
        assert result["signal"] == NEUTRAL
        assert result["suggested_amount"] == pytest.approx(500.0)
        assert result["allocation_pct"] == 50

    def test_do_not_buy_allocation(self):
        result = build_decision(self._indicators(-2.0), _config(budget=1000.0))
        assert result["signal"] == DO_NOT_BUY
        assert result["suggested_amount"] == pytest.approx(200.0)
        assert result["allocation_pct"] == 20

    def test_color_is_set(self):
        result = build_decision(self._indicators(4.0), _config())
        assert result["color"] == "emerald"

    def test_confidence_propagates(self):
        result = build_decision(self._indicators(4.0, momentum="up"), _config())
        assert result["confidence"] == "HIGH"

    def test_custom_budget_scales_amount(self):
        result = build_decision(self._indicators(4.0), _config(budget=500.0))
        assert result["suggested_amount"] == pytest.approx(750.0)
