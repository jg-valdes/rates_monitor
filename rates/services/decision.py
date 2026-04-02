"""
Decision engine: translates indicators into actionable signals.
"""

STRONG_BUY = "STRONG BUY"
MODERATE_BUY = "MODERATE BUY"
NEUTRAL = "NEUTRAL"
DO_NOT_BUY = "DO NOT BUY"

SIGNAL_MULTIPLIERS = {
    STRONG_BUY: 1.5,
    MODERATE_BUY: 1.0,
    NEUTRAL: 0.5,
    DO_NOT_BUY: 0.2,
}

SIGNAL_CSS = {
    STRONG_BUY: "emerald",
    MODERATE_BUY: "green",
    NEUTRAL: "amber",
    DO_NOT_BUY: "red",
}


def get_signal(deviation: float, config) -> str:
    if deviation > config.threshold_strong_buy:
        return STRONG_BUY
    if deviation > config.threshold_moderate_buy:
        return MODERATE_BUY
    if deviation >= config.threshold_do_not_buy:
        return NEUTRAL
    return DO_NOT_BUY


def get_confidence(signal: str, momentum: str) -> str:
    if signal == STRONG_BUY:
        return "HIGH" if momentum == "up" else "MEDIUM"
    if signal == MODERATE_BUY:
        return "MEDIUM" if momentum != "down" else "LOW"
    return "LOW"


def build_decision(indicators: dict, config) -> dict:
    """
    Produce a complete decision dict from precomputed indicators and user config.
    """
    signal = get_signal(indicators["deviation"], config)
    confidence = get_confidence(signal, indicators["momentum"])
    multiplier = SIGNAL_MULTIPLIERS[signal]
    suggested_amount = round(config.monthly_usd_budget * multiplier, 2)

    return {
        "signal": signal,
        "confidence": confidence,
        "suggested_amount": suggested_amount,
        "allocation_pct": int(multiplier * 100),
        "color": SIGNAL_CSS[signal],
    }
