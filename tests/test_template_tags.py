"""Tests for rates/templatetags/rates_extras.py."""
import pytest
from rates.templatetags.rates_extras import confidence_label, momentum_label, signal_label


class TestSignalLabel:
    def test_strong_buy(self):
        assert signal_label("STRONG BUY") == "COMPRA FUERTE"

    def test_moderate_buy(self):
        assert signal_label("MODERATE BUY") == "COMPRA MODERADA"

    def test_neutral(self):
        assert signal_label("NEUTRAL") == "NEUTRAL"

    def test_do_not_buy(self):
        assert signal_label("DO NOT BUY") == "NO COMPRAR"

    def test_unknown_returns_original(self):
        assert signal_label("UNKNOWN") == "UNKNOWN"

    def test_empty_string(self):
        assert signal_label("") == ""


class TestConfidenceLabel:
    def test_high(self):
        assert confidence_label("HIGH") == "ALTA"

    def test_medium(self):
        assert confidence_label("MEDIUM") == "MEDIA"

    def test_low(self):
        assert confidence_label("LOW") == "BAJA"

    def test_unknown_returns_original(self):
        assert confidence_label("VERY HIGH") == "VERY HIGH"


class TestMomentumLabel:
    def test_up(self):
        assert momentum_label("up") == "al alza ↑"

    def test_down(self):
        assert momentum_label("down") == "a la baja ↓"

    def test_neutral(self):
        assert momentum_label("neutral") == "neutral →"

    def test_unknown_returns_original(self):
        assert momentum_label("sideways") == "sideways"
