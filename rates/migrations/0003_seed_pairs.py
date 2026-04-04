"""
Data migration:
1. Create the three currency pairs (USD-BRL, UYU-USD, UYU-BRL).
2. Assign all existing ExchangeRate rows to the USD-BRL pair.
3. Create a PairConfig for USD-BRL copying values from the UserConfig singleton.
4. Create default PairConfigs for UYU-USD and UYU-BRL.
"""

from django.db import migrations

PAIRS = [
    {"code": "USD-BRL", "name": "Dólar / Real", "api_code": "USD-BRL"},
    {"code": "UYU-USD", "name": "Peso Uruguayo / Dólar", "api_code": "UYU-USD"},
    {"code": "UYU-BRL", "name": "Peso Uruguayo / Real", "api_code": "UYU-BRL"},
]


def forwards(apps, schema_editor):
    CurrencyPair = apps.get_model("rates", "CurrencyPair")
    ExchangeRate = apps.get_model("rates", "ExchangeRate")
    PairConfig = apps.get_model("rates", "PairConfig")
    UserConfig = apps.get_model("rates", "UserConfig")

    # Create pairs
    pairs = {}
    for data in PAIRS:
        pair = CurrencyPair.objects.create(**data, active=True)
        pairs[data["code"]] = pair

    usd_brl = pairs["USD-BRL"]

    # Assign all existing rates to USD-BRL
    ExchangeRate.objects.filter(pair__isnull=True).update(pair=usd_brl)

    # Copy UserConfig singleton → PairConfig for USD-BRL
    try:
        uc = UserConfig.objects.get(pk=1)
        PairConfig.objects.create(
            pair=usd_brl,
            monthly_budget=uc.monthly_usd_budget,
            threshold_strong_buy=uc.threshold_strong_buy,
            threshold_moderate_buy=uc.threshold_moderate_buy,
            threshold_do_not_buy=uc.threshold_do_not_buy,
            alert_webhook_url=uc.alert_webhook_url,
            alert_on_strong_buy=uc.alert_on_strong_buy,
            alert_on_deviation_above=uc.alert_on_deviation_above,
            alert_on_rate_above=uc.alert_on_rate_above,
        )
    except UserConfig.DoesNotExist:
        PairConfig.objects.create(pair=usd_brl)

    # Default configs for the other two pairs
    PairConfig.objects.create(pair=pairs["UYU-USD"])
    PairConfig.objects.create(pair=pairs["UYU-BRL"])


def backwards(apps, schema_editor):
    CurrencyPair = apps.get_model("rates", "CurrencyPair")
    ExchangeRate = apps.get_model("rates", "ExchangeRate")
    ExchangeRate.objects.update(pair=None)
    CurrencyPair.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("rates", "0002_currency_pair_pair_config"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
