"""
Cross-pair analysis: computes the best route from UYU to BRL.

Two possible routes:
  - Directa:   UYU → BRL  (use UYU-BRL rate directly)
  - Indirecta: UYU → USD → BRL  (sell UYU for USD, then sell USD for BRL)

Formula:
  direct_rate   = UYU-BRL bid  (BRL per 1 UYU)
  indirect_rate = UYU-USD bid * USD-BRL bid
                = (USD per 1 UYU) * (BRL per 1 USD)
                = BRL per 1 UYU via the intermediate step

A higher value means more BRL per peso uruguayo, i.e., a better deal.
"""

from rates.models import CurrencyPair, ExchangeRate


def _latest_rate(pair_code: str) -> float | None:
    """Return the most recent bid rate for the given pair code, or None."""
    try:
        pair = CurrencyPair.objects.get(code=pair_code, active=True)
    except CurrencyPair.DoesNotExist:
        return None
    entry = ExchangeRate.objects.filter(pair=pair).order_by("-date").first()
    return entry.rate if entry else None


def compute_cross_pair() -> dict | None:
    """
    Compute the best UYU→BRL conversion route using the latest stored rates.
    Returns a dict with both routes and the recommended one, or None if any
    of the three required rates is missing.
    """
    uyu_brl = _latest_rate("UYU-BRL")
    uyu_usd = _latest_rate("UYU-USD")
    usd_brl = _latest_rate("USD-BRL")

    if None in (uyu_brl, uyu_usd, usd_brl):
        return None

    direct_rate   = uyu_brl
    indirect_rate = uyu_usd * usd_brl

    if direct_rate >= indirect_rate:
        best_route = "directa"
        advantage_pct = (direct_rate - indirect_rate) / indirect_rate * 100
    else:
        best_route = "indirecta"
        advantage_pct = (indirect_rate - direct_rate) / direct_rate * 100

    return {
        "direct_rate":    round(direct_rate, 6),
        "indirect_rate":  round(indirect_rate, 6),
        "best_route":     best_route,
        "advantage_pct":  round(advantage_pct, 4),
        "uyu_brl":        round(uyu_brl, 6),
        "uyu_usd":        round(uyu_usd, 6),
        "usd_brl":        round(usd_brl, 6),
    }
