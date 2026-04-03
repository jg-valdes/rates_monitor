"""
Schema migration:
- Make ExchangeRate.pair non-nullable (all rows now have a pair after 0003).
- Add unique_together(pair, date) constraint.
- Delete the UserConfig model (superseded by PairConfig).
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("rates", "0003_seed_pairs"),
    ]

    operations = [
        # Make pair non-nullable
        migrations.AlterField(
            model_name="exchangerate",
            name="pair",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="rates",
                to="rates.currencypair",
            ),
        ),
        # Enforce unique pair+date
        migrations.AlterUniqueTogether(
            name="exchangerate",
            unique_together={("pair", "date")},
        ),
        # Drop legacy singleton config table
        migrations.DeleteModel(
            name="UserConfig",
        ),
    ]
