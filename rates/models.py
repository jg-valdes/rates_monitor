from django.db import models


class ExchangeRate(models.Model):
    date = models.DateField(unique=True)
    rate = models.FloatField()
    high = models.FloatField(null=True, blank=True)
    low = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date"]

    def __str__(self):
        return f"{self.date}: {self.rate:.4f}"


class UserConfig(models.Model):
    """Singleton configuration record (always pk=1)."""

    monthly_usd_budget = models.FloatField(default=1000.0)
    threshold_strong_buy = models.FloatField(default=3.0)
    threshold_moderate_buy = models.FloatField(default=1.5)
    threshold_do_not_buy = models.FloatField(default=-1.0)
    alert_webhook_url = models.URLField(blank=True, default="")
    alert_on_strong_buy = models.BooleanField(default=True)
    alert_on_deviation_above = models.FloatField(null=True, blank=True)
    alert_on_rate_above = models.FloatField(null=True, blank=True)

    class Meta:
        verbose_name = "Configuración"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "User Configuration"
