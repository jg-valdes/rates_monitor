import logging

import requests

from rates.translations import SIGNAL_LABELS

logger = logging.getLogger(__name__)


def check_and_send(indicators: dict, decision: dict, config) -> list[str]:
    """
    Evalúa condiciones de alerta y envía notificaciones via webhook.
    Retorna la lista de mensajes de alerta disparados.
    """
    triggered = []
    signal_es = SIGNAL_LABELS.get(decision["signal"], decision["signal"])

    if config.alert_on_strong_buy and decision["signal"] == "STRONG BUY":
        triggered.append(
            f"Señal {signal_es}: cotización {indicators['current_rate']:.4f}, "
            f"desviación {indicators['deviation']:+.2f}%"
        )

    if (
        config.alert_on_deviation_above is not None
        and indicators["deviation"] > config.alert_on_deviation_above
    ):
        triggered.append(
            f"Desviación {indicators['deviation']:+.2f}% superó el umbral "
            f"configurado de {config.alert_on_deviation_above:+.2f}%"
        )

    if (
        config.alert_on_rate_above is not None
        and indicators["current_rate"] > config.alert_on_rate_above
    ):
        triggered.append(
            f"Cotización {indicators['current_rate']:.4f} superó el umbral "
            f"configurado de {config.alert_on_rate_above:.4f}"
        )

    for message in triggered:
        logger.warning(f"ALERTA: {message}")
        if config.alert_webhook_url:
            _send_webhook(config.alert_webhook_url, message, indicators, decision)

    return triggered


def _send_webhook(url: str, message: str, indicators: dict, decision: dict) -> None:
    payload = {
        "text": message,
        "signal": decision["signal"],
        "signal_es": SIGNAL_LABELS.get(decision["signal"], decision["signal"]),
        "rate": indicators["current_rate"],
        "deviation": indicators["deviation"],
        "confidence": decision["confidence"],
        "suggested_usd": decision["suggested_amount"],
    }
    try:
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()
        logger.info(f"Alerta enviada al webhook: {url}")
    except requests.RequestException as exc:
        logger.error(f"Error al enviar webhook ({url}): {exc}")
