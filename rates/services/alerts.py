import logging

import requests
from django.conf import settings

from rates.translations import CONFIDENCE_LABELS, MOMENTUM_LABELS, SIGNAL_LABELS

logger = logging.getLogger(__name__)

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

_SIGNAL_EMOJI = {
    "STRONG BUY":   "🚀",
    "MODERATE BUY": "📈",
    "NEUTRAL":      "📊",
    "DO NOT BUY":   "🛑",
}
_CONFIDENCE_EMOJI = {
    "HIGH":   "🟢",
    "MEDIUM": "🟡",
    "LOW":    "🔴",
}
_MOMENTUM_EMOJI = {
    "up":      "↗️",
    "down":    "↘️",
    "neutral": "➡️",
}


def _send_telegram(message: str) -> bool:
    """
    Send `message` via the Telegram Bot API.
    Returns True on success, False when credentials are not configured.
    Raises requests.RequestException on network/API errors.
    """
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return False
    resp = requests.post(
        _TELEGRAM_API.format(token=token),
        json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
        timeout=5,
    )
    resp.raise_for_status()
    return True


def _build_message(indicators: dict, decision: dict, pair_name: str) -> str:
    signal = decision["signal"]
    confidence = decision["confidence"]
    momentum = indicators.get("momentum", "neutral")

    signal_emoji = _SIGNAL_EMOJI.get(signal, "🔔")
    confidence_emoji = _CONFIDENCE_EMOJI.get(confidence, "")
    momentum_emoji = _MOMENTUM_EMOJI.get(momentum, "➡️")

    signal_es = SIGNAL_LABELS.get(signal, signal)
    confidence_es = CONFIDENCE_LABELS.get(confidence, confidence)
    momentum_es = MOMENTUM_LABELS.get(momentum, momentum)

    deviation = indicators["deviation"]
    deviation_emoji = "📉" if deviation > 0 else "📈"  # positive deviation = rate above MA = cheaper to buy now

    return (
        f"{signal_emoji} *{pair_name}* — {signal_es}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💰 Cotización: `{indicators['current_rate']:.4f}`\n"
        f"{deviation_emoji} Desviación vs MA90: `{deviation:+.2f}%`\n"
        f"📊 MA30: `{indicators['ma30']:.4f}` · MA90: `{indicators['ma90']:.4f}`\n"
        f"{momentum_emoji} Tendencia: {momentum_es}\n"
        f"🎯 Confianza: {confidence_emoji} {confidence_es}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💵 Sugerido: `${decision['suggested_amount']:.0f}` "
        f"({decision['allocation_pct']}% del presupuesto)"
    )


def check_and_send(indicators: dict, decision: dict, config, pair_name: str = "") -> list[str]:
    """
    Evaluate alert conditions and send Telegram notifications when triggered.
    Returns the list of triggered alert messages.
    """
    triggered = []
    signal_es = SIGNAL_LABELS.get(decision["signal"], decision["signal"])
    prefix = f"[{pair_name}] " if pair_name else ""

    if config.alert_on_strong_buy and decision["signal"] == "STRONG BUY":
        triggered.append(
            f"{prefix}Señal {signal_es}: cotización {indicators['current_rate']:.4f}, "
            f"desviación {indicators['deviation']:+.2f}%"
        )

    if (
        config.alert_on_deviation_above is not None
        and indicators["deviation"] > config.alert_on_deviation_above
    ):
        triggered.append(
            f"{prefix}Desviación {indicators['deviation']:+.2f}% superó el umbral "
            f"configurado de {config.alert_on_deviation_above:+.2f}%"
        )

    if (
        config.alert_on_rate_above is not None
        and indicators["current_rate"] > config.alert_on_rate_above
    ):
        triggered.append(
            f"{prefix}Cotización {indicators['current_rate']:.4f} superó el umbral "
            f"configurado de {config.alert_on_rate_above:.4f}"
        )

    for message in triggered:
        logger.warning("ALERT: %s", message)
        try:
            _send_telegram(_build_message(indicators, decision, pair_name))
        except requests.RequestException as exc:
            logger.error("Error sending Telegram alert for %s: %s", pair_name, exc)

    return triggered


def send_test_alert(indicators: dict, decision: dict, config, pair_name: str) -> bool:
    """
    Send a real-data alert using current indicators and decision.
    The message format is identical to production alerts so the user sees
    exactly what future notifications look like.
    Returns True on success, False when Telegram is not configured.
    Raises requests.RequestException on network/API errors.
    """
    message = _build_message(indicators, decision, pair_name)
    return _send_telegram(message)
