"""
Schema migration: add CurrencyPair, PairConfig, add nullable pair FK to
ExchangeRate, drop the per-field unique constraint on ExchangeRate.date
(will be replaced by unique_together in 0004 after the data migration).
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("rates", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CurrencyPair",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=10, unique=True)),
                ("name", models.CharField(max_length=60)),
                ("api_code", models.CharField(max_length=10)),
                ("active", models.BooleanField(default=True)),
            ],
            options={
                "verbose_name": "Par Cambiario",
                "verbose_name_plural": "Pares Cambiarios",
                "ordering": ["code"],
            },
        ),
        # Remove unique constraint from ExchangeRate.date so we can later
        # enforce unique_together(pair, date) instead.
        migrations.AlterField(
            model_name="exchangerate",
            name="date",
            field=models.DateField(),
        ),
        # Add nullable pair FK — data migration (0003) will populate it.
        migrations.AddField(
            model_name="exchangerate",
            name="pair",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="rates",
                to="rates.currencypair",
            ),
        ),
        migrations.CreateModel(
            name="PairConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("pair", models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="config",
                    to="rates.currencypair",
                )),
                ("monthly_budget", models.FloatField(default=1000.0)),
                ("threshold_strong_buy", models.FloatField(default=3.0)),
                ("threshold_moderate_buy", models.FloatField(default=1.5)),
                ("threshold_do_not_buy", models.FloatField(default=-1.0)),
                ("alert_webhook_url", models.URLField(blank=True, default="")),
                ("alert_on_strong_buy", models.BooleanField(default=True)),
                ("alert_on_deviation_above", models.FloatField(blank=True, null=True)),
                ("alert_on_rate_above", models.FloatField(blank=True, null=True)),
            ],
            options={
                "verbose_name": "Configuración de Par",
                "verbose_name_plural": "Configuraciones de Par",
            },
        ),
    ]
