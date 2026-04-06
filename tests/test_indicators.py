"""Tests for rates/services/indicators.py — pure functions, no DB needed."""
import datetime
from unittest.mock import MagicMock

import pytest

from rates.services.indicators import (
    compute_all,
    compute_deviation,
    compute_ma,
    compute_momentum,
    compute_rolling_ma,
    compute_volatility,
)


class TestComputeMa:
    def test_empty_list(self):
        assert compute_ma([], 30) is None

    def test_fewer_than_window(self):
        # Uses all available values when fewer than window
        result = compute_ma([1.0, 2.0, 3.0], 30)
        assert result == pytest.approx(2.0, rel=1e-4)

    def test_exact_window(self):
        values = [float(i) for i in range(1, 31)]
        assert compute_ma(values, 30) == pytest.approx(15.5, rel=1e-4)

    def test_uses_last_n_values(self):
        # First 70 values are 1.0, last 30 are 10.0 → MA30 = 10.0
        values = [1.0] * 70 + [10.0] * 30
        assert compute_ma(values, 30) == pytest.approx(10.0, rel=1e-4)

    def test_returns_rounded(self):
        result = compute_ma([1.111111, 2.222222, 3.333333], 3)
        assert result == round(sum([1.111111, 2.222222, 3.333333]) / 3, 4)


class TestComputeDeviation:
    def test_positive_deviation(self):
        # rate above MA90 → positive → cheaper to buy
        assert compute_deviation(5.83, 5.50) == pytest.approx(6.0, rel=1e-2)

    def test_negative_deviation(self):
        assert compute_deviation(5.0, 5.50) == pytest.approx(-9.0909, rel=1e-2)

    def test_zero_deviation(self):
        assert compute_deviation(5.0, 5.0) == pytest.approx(0.0)

    def test_zero_ma90_returns_zero(self):
        assert compute_deviation(5.0, 0) == 0.0


class TestComputeMomentum:
    def test_upward(self):
        assert compute_momentum([1.0, 2.0, 3.0]) == "up"

    def test_downward(self):
        assert compute_momentum([3.0, 2.0, 1.0]) == "down"

    def test_neutral_flat(self):
        assert compute_momentum([5.0, 5.0, 5.0]) == "neutral"

    def test_neutral_zigzag(self):
        assert compute_momentum([1.0, 3.0, 2.0]) == "neutral"

    def test_fewer_than_3_values(self):
        assert compute_momentum([1.0, 2.0]) == "neutral"

    def test_empty(self):
        assert compute_momentum([]) == "neutral"

    def test_uses_last_3(self):
        # First values going down, last 3 going up
        assert compute_momentum([5.0, 4.0, 3.0, 1.0, 2.0, 3.0]) == "up"


class TestComputeVolatility:
    def test_empty(self):
        assert compute_volatility([]) == 0.0

    def test_single_value(self):
        assert compute_volatility([5.0]) == 0.0

    def test_constant(self):
        assert compute_volatility([5.0] * 20) == 0.0

    def test_known_volatility(self):
        # Changes: 1.0 every day for 14 days
        values = [float(i) for i in range(15)]
        assert compute_volatility(values) == pytest.approx(1.0, rel=1e-4)

    def test_uses_last_window_plus_one(self):
        # Large early swings should be excluded when window=5
        values = [0.0, 100.0, 0.0, 100.0] + [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
        result = compute_volatility(values, window=5)
        assert result == pytest.approx(1.0, rel=1e-4)


class TestComputeRollingMa:
    def test_leading_nones(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = compute_rolling_ma(values, 3)
        assert result[0] is None
        assert result[1] is None

    def test_first_valid_value(self):
        values = [1.0, 2.0, 3.0, 4.0]
        result = compute_rolling_ma(values, 3)
        assert result[2] == pytest.approx(2.0, rel=1e-4)

    def test_length_matches_input(self):
        values = list(range(10))
        result = compute_rolling_ma(values, 3)
        assert len(result) == 10

    def test_window_1_equals_values(self):
        values = [1.5, 2.5, 3.5]
        result = compute_rolling_ma(values, 1)
        assert result == [pytest.approx(v, rel=1e-4) for v in values]


class TestComputeAll:
    def _make_rate(self, value, offset_days=0):
        mock = MagicMock()
        mock.rate = value
        mock.date = datetime.date(2024, 1, 1) + datetime.timedelta(days=offset_days)
        return mock

    def test_empty_returns_none(self):
        assert compute_all([]) is None

    def test_returns_dict_with_expected_keys(self):
        rates = [self._make_rate(5.0 + i * 0.01, i) for i in range(90)]
        result = compute_all(rates)
        assert result is not None
        for key in ("current_rate", "current_date", "ma30", "ma90", "deviation", "momentum", "volatility", "data_points"):
            assert key in result

    def test_current_rate_is_last(self):
        rates = [self._make_rate(float(i), i) for i in range(1, 6)]
        result = compute_all(rates)
        assert result["current_rate"] == 5.0

    def test_data_points_count(self):
        rates = [self._make_rate(5.0, i) for i in range(30)]
        result = compute_all(rates)
        assert result["data_points"] == 30

    def test_single_rate(self):
        rates = [self._make_rate(5.0, 0)]
        result = compute_all(rates)
        assert result is not None
        assert result["current_rate"] == 5.0
        assert result["momentum"] == "neutral"
