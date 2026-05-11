from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("rates", "0006_remove_alert_webhook_url"),
    ]

    operations = [
        migrations.AddField(
            model_name="exchangerate",
            name="is_synthetic",
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name="SourceQuotaUsage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source", models.CharField(max_length=40)),
                ("year", models.PositiveSmallIntegerField()),
                ("month", models.PositiveSmallIntegerField()),
                ("request_count", models.PositiveIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Uso de Cuota por Fuente",
                "verbose_name_plural": "Uso de Cuota por Fuente",
                "unique_together": {("source", "year", "month")},
            },
        ),
    ]
