import logging

import requests

from rates.translations import SIGNAL_LABELS

logger = logging.getLogger(__name__)


def check_and_send(indicators: dict, decision: dict, config, pair_name: str = "") -> list[str]:
    """
    Evaluate alert conditions and send notifications via webhook.
    Returns the list of triggered alert messages.
    """
    triggered = []
    signal_es = SIGNAL_LABELS.get(decision["signal"], decision["signal"])
    prefix = f"[{pair_name}] " if pair_name else ""

    if config.alert_on_strong_buy and decision["signal"] == "STRONG BUY":
        triggered.append(
            f"{prefix}Signal {signal_es}: rate {indicators['current_rate']:.4f}, "
            f"deviation {indicators['deviation']:+.2f}%"
        )

    if (
        config.alert_on_deviation_above is not None
        and indicators["deviation"] > config.alert_on_deviation_above
    ):
        triggered.append(
            f"{prefix}Deviation {indicators['deviation']:+.2f}% exceeded configured "
            f"threshold of {config.alert_on_deviation_above:+.2f}%"
        )

    if (
        config.alert_on_rate_above is not None
        and indicators["current_rate"] > config.alert_on_rate_above
    ):
        triggered.append(
            f"{prefix}Rate {indicators['current_rate']:.4f} exceeded configured "
            f"threshold of {config.alert_on_rate_above:.4f}"
        )

    for message in triggered:
        logger.warning(f"ALERT: {message}")
        if config.alert_webhook_url:
            _send_webhook(config.alert_webhook_url, message, indicators, decision, pair_name)

    return triggered


def _send_webhook(url: str, message: str, indicators: dict, decision: dict, pair_name: str) -> None:
    payload = {
        "text": message,
        "pair": pair_name,
        "signal": decision["signal"],
        "signal_es": SIGNAL_LABELS.get(decision["signal"], decision["signal"]),
        "rate": indicators["current_rate"],
        "deviation": indicators["deviation"],
        "confidence": decision["confidence"],
        "suggested_amount": decision["suggested_amount"],
    }
    try:
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()
        logger.info(f"Alert sent to webhook: {url}")
    except requests.RequestException as exc:
        logger.error(f"Error sending webhook ({url}): {exc}")
