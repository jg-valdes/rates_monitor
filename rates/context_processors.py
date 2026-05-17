from django.conf import settings

from rates.models import CurrencyPair


def active_pairs(request):
    """Inject all active pairs into every template context for nav rendering."""
    source = getattr(settings, "EXCHANGE_RATE_SOURCE", "awesomeapi")
    footer_source = {
        "awesomeapi": {
            "provider": "economia.awesomeapi.com.br",
            "update_note": "Se actualiza cada hora",
        },
        "openexchangerates": {
            "provider": "openexchangerates.org",
            "update_note": "Se actualiza según el plan y la cuota configurada",
        },
    }.get(
        source,
        {
            "provider": source,
            "update_note": "Se actualiza según la configuración activa",
        },
    )
    return {
        "all_pairs": CurrencyPair.objects.filter(active=True),
        "footer_rate_source": footer_source,
    }
