"""
Mapeos de etiquetas en español para valores internos en inglés.
Los constantes de dominio (STRONG BUY, HIGH, etc.) se mantienen en inglés
para no romper comparaciones en Python ni migraciones de base de datos.
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
