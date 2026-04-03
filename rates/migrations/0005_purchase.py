from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("rates", "0004_finalize_exchange_rate"),
    ]

    operations = [
        migrations.CreateModel(
            name="Purchase",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("pair", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="purchases",
                    to="rates.currencypair",
                )),
                ("date", models.DateField()),
                ("amount_spent", models.FloatField()),
                ("amount_received", models.FloatField()),
                ("note", models.CharField(blank=True, default="", max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Compra",
                "verbose_name_plural": "Compras",
                "ordering": ["-date", "-created_at"],
            },
        ),
    ]
