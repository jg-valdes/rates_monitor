"""
Pure functions for computing exchange rate indicators.
All functions accept lists of floats ordered oldest → newest.
"""
from statistics import mean


def compute_ma(values: list[float], window: int) -> float | None:
    """Moving average over the last `window` values. None if insufficient data."""
    if not values:
        return None
    return round(mean(values[-window:]), 4)


def compute_deviation(rate: float, ma90: float) -> float:
    """Deviation of current rate from MA90, as a percentage."""
    if ma90 == 0:
        return 0.0
    return round((rate - ma90) / ma90 * 100, 4)


def compute_momentum(values: list[float]) -> str:
    """
    Determine price momentum from the last 3 values.
    Returns 'up', 'down', or 'neutral'.
    """
    if len(values) < 3:
        return "neutral"
    a, b, c = values[-3], values[-2], values[-1]
    if a < b < c:
        return "up"
    if a > b > c:
        return "down"
    return "neutral"


def compute_volatility(values: list[float], window: int = 14) -> float:
    """Average absolute daily change over the last `window` days."""
    if len(values) < 2:
        return 0.0
    recent = values[-(window + 1):]
    changes = [abs(recent[i] - recent[i - 1]) for i in range(1, len(recent))]
    return round(mean(changes), 4) if changes else 0.0


def compute_rolling_ma(values: list[float], window: int) -> list[float | None]:
    """Compute rolling moving average for chart rendering."""
    result = []
    for i in range(len(values)):
        if i < window - 1:
            result.append(None)
        else:
            result.append(round(mean(values[i - window + 1 : i + 1]), 4))
    return result


def compute_all(rates_list) -> dict | None:
    """
    Compute all indicators for the most recent rate.
    rates_list: list of ExchangeRate model instances ordered by date asc.
    Returns a dict with all indicators, or None if no data.
    """
    if not rates_list:
        return None

    values = [r.rate for r in rates_list]
    current = values[-1]

    ma30 = compute_ma(values, 30)
    ma90 = compute_ma(values, 90)
    deviation = compute_deviation(current, ma90) if ma90 else 0.0
    momentum = compute_momentum(values)
    volatility = compute_volatility(values)

    return {
        "current_rate": round(current, 4),
        "current_date": rates_list[-1].date,
        "ma30": ma30,
        "ma90": ma90,
        "deviation": deviation,
        "momentum": momentum,
        "volatility": volatility,
        "data_points": len(values),
    }
