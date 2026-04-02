import logging

import requests

logger = logging.getLogger(__name__)


def check_and_send(indicators: dict, decision: dict, config) -> list[str]:
    """
    Evaluate alert conditions and send notifications via webhook.
    Returns list of triggered alert messages (useful for management command output).
    """
    triggered = []

    if config.alert_on_strong_buy and decision["signal"] == "STRONG BUY":
        triggered.append(
            f"STRONG BUY signal! Rate: {indicators['current_rate']:.4f}, "
            f"Deviation: {indicators['deviation']:+.2f}%"
        )

    if (
        config.alert_on_deviation_above is not None
        and indicators["deviation"] > config.alert_on_deviation_above
    ):
        triggered.append(
            f"Deviation {indicators['deviation']:+.2f}% exceeded threshold "
            f"{config.alert_on_deviation_above:+.2f}%"
        )

    if (
        config.alert_on_rate_above is not None
        and indicators["current_rate"] > config.alert_on_rate_above
    ):
        triggered.append(
            f"Rate {indicators['current_rate']:.4f} exceeded threshold "
            f"{config.alert_on_rate_above:.4f}"
        )

    for message in triggered:
        logger.warning(f"ALERT: {message}")
        if config.alert_webhook_url:
            _send_webhook(config.alert_webhook_url, message, indicators, decision)

    return triggered


def _send_webhook(url: str, message: str, indicators: dict, decision: dict) -> None:
    payload = {
        "text": message,
        "signal": decision["signal"],
        "rate": indicators["current_rate"],
        "deviation": indicators["deviation"],
        "confidence": decision["confidence"],
        "suggested_usd": decision["suggested_amount"],
    }
    try:
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()
        logger.info(f"Webhook sent: {url}")
    except requests.RequestException as exc:
        logger.error(f"Webhook failed ({url}): {exc}")
