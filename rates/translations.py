"""
Spanish display labels for internal English domain constants.
Domain constants (STRONG BUY, HIGH, etc.) are always kept in English to
avoid breaking Python comparisons or requiring database migrations.
"""

SIGNAL_LABELS: dict[str, str] = {
    "STRONG BUY": "COMPRA FUERTE",
    "MODERATE BUY": "COMPRA MODERADA",
    "NEUTRAL": "NEUTRAL",
    "DO NOT BUY": "NO COMPRAR",
}

CONFIDENCE_LABELS: dict[str, str] = {
    "HIGH": "ALTA",
    "MEDIUM": "MEDIA",
    "LOW": "BAJA",
}

MOMENTUM_LABELS: dict[str, str] = {
    "up": "al alza ↑",
    "down": "a la baja ↓",
    "neutral": "neutral →",
}
