from django import template

from rates.translations import CONFIDENCE_LABELS, MOMENTUM_LABELS, SIGNAL_LABELS

register = template.Library()


@register.filter
def signal_label(value: str) -> str:
    """Translate an internal signal code to its Spanish display label."""
    return SIGNAL_LABELS.get(value, value)


@register.filter
def confidence_label(value: str) -> str:
    """Translate an internal confidence level to its Spanish display label."""
    return CONFIDENCE_LABELS.get(value, value)


@register.filter
def momentum_label(value: str) -> str:
    """Translate an internal momentum value to its Spanish display label."""
    return MOMENTUM_LABELS.get(value, value)
