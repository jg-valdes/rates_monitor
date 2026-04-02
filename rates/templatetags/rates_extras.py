from django import template

from rates.translations import CONFIDENCE_LABELS, MOMENTUM_LABELS, SIGNAL_LABELS

register = template.Library()


@register.filter
def signal_label(value: str) -> str:
    """Traduce un código de señal interno a su etiqueta en español."""
    return SIGNAL_LABELS.get(value, value)


@register.filter
def confidence_label(value: str) -> str:
    """Traduce un nivel de confianza interno a su etiqueta en español."""
    return CONFIDENCE_LABELS.get(value, value)


@register.filter
def momentum_label(value: str) -> str:
    """Traduce un valor de tendencia interno a su etiqueta en español."""
    return MOMENTUM_LABELS.get(value, value)
