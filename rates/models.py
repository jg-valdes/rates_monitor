from django.db import models


class CurrencyPair(models.Model):
    code = models.CharField(max_length=10, unique=True)  # "USD-BRL"
    name = models.CharField(max_length=60)  # "Dólar / Real"
    api_code = models.CharField(max_length=10)  # AwesomeAPI pair code
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "Par Cambiario"
        verbose_name_plural = "Pares Cambiarios"

    def __str__(self):
        return f"{self.code} — {self.name}"

    @property
    def slug(self):
        return self.code.lower()

    @property
    def base_currency(self):
        """Currency being sold/spent (left side of the pair code)."""
        return self.code.split("-")[0]

    @property
    def quote_currency(self):
        """Currency being bought/received (right side of the pair code)."""
        return self.code.split("-")[1]


class ExchangeRate(models.Model):
    pair = models.ForeignKey(CurrencyPair, on_delete=models.CASCADE, related_name="rates")
    date = models.DateField()
    rate = models.FloatField()
    high = models.FloatField(null=True, blank=True)
    low = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date"]
        unique_together = [["pair", "date"]]

    def __str__(self):
        return f"{self.pair.code} {self.date}: {self.rate:.4f}"


class Purchase(models.Model):
    """Records an actual conversion executed by the user for a given pair."""

    pair = models.ForeignKey(CurrencyPair, on_delete=models.CASCADE, related_name="purchases")
    date = models.DateField()
    amount_spent = models.FloatField()  # in pair's base currency
    amount_received = models.FloatField()  # in pair's quote currency
    note = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "Compra"
        verbose_name_plural = "Compras"

    def __str__(self):
        return f"{self.pair.code} {self.date}: {self.amount_spent} → {self.amount_received}"

    @property
    def effective_rate(self):
        if not self.amount_spent:
            return 0.0
        return round(self.amount_received / self.amount_spent, 6)


class PairConfig(models.Model):
    """Per-pair configuration (thresholds, budget, alerts)."""

    pair = models.OneToOneField(CurrencyPair, on_delete=models.CASCADE, related_name="config")
    monthly_budget = models.FloatField(default=1000.0)
    threshold_strong_buy = models.FloatField(default=3.0)
    threshold_moderate_buy = models.FloatField(default=1.5)
    threshold_do_not_buy = models.FloatField(default=-1.0)
    alert_on_strong_buy = models.BooleanField(default=True)
    alert_on_deviation_above = models.FloatField(null=True, blank=True)
    alert_on_rate_above = models.FloatField(null=True, blank=True)

    class Meta:
        verbose_name = "Configuración de Par"
        verbose_name_plural = "Configuraciones de Par"

    def __str__(self):
        return f"Config: {self.pair.code}"
