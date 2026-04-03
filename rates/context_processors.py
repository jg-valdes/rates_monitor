from rates.models import CurrencyPair


def active_pairs(request):
    """Inject all active pairs into every template context for nav rendering."""
    return {"all_pairs": CurrencyPair.objects.filter(active=True)}
