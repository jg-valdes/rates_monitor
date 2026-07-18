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
    is_synthetic = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date"]
        unique_together = [["pair", "date"]]

    def __str__(self):
        return f"{self.pair.code} {self.date}: {self.rate:.4f}"


class SourceQuotaUsage(models.Model):
    source = models.CharField(max_length=40)
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    request_count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [["source", "year", "month"]]
        verbose_name = "Uso de Cuota por Fuente"
        verbose_name_plural = "Uso de Cuota por Fuente"

    def __str__(self):
        return f"{self.source} {self.year:04d}-{self.month:02d}: {self.request_count}"


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


class CubIndexValue(models.Model):
    class Series(models.TextChoices):
        SC_STANDARD = "CUB_SC_STANDARD", "CUB-SC estándar"

    series = models.CharField(max_length=30, choices=Series, default=Series.SC_STANDARD)
    reference_month = models.DateField()
    applicable_month = models.DateField()
    value = models.DecimalField(max_digits=12, decimal_places=2)
    monthly_variation = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)
    source_url = models.URLField(blank=True, default="")
    verified_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-applicable_month"]
        constraints = [
            models.UniqueConstraint(
                fields=["series", "applicable_month"], name="unique_cub_series_month"
            ),
            models.CheckConstraint(condition=models.Q(value__gt=0), name="cub_value_positive"),
        ]
        verbose_name = "Valor CUB"
        verbose_name_plural = "Valores CUB"

    def __str__(self):
        return f"{self.get_series_display()} {self.applicable_month:%Y-%m}: R$ {self.value}"


class PropertyPurchasePlan(models.Model):
    name = models.CharField(max_length=120)
    contract_date = models.DateField()
    currency = models.CharField(max_length=3, default="BRL", editable=False)
    cub_series = models.CharField(
        max_length=30,
        choices=CubIndexValue.Series,
        default=CubIndexValue.Series.SC_STANDARD,
    )
    base_cub = models.ForeignKey(
        CubIndexValue,
        on_delete=models.PROTECT,
        related_name="base_for_plans",
    )
    base_cub_value = models.DecimalField(max_digits=12, decimal_places=2)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["archived_at", "name"]
        verbose_name = "Plan de vivienda"
        verbose_name_plural = "Planes de vivienda"

    def __str__(self):
        return self.name


class PaymentSeries(models.Model):
    class Kind(models.TextChoices):
        DOWN_PAYMENT = "DOWN_PAYMENT", "Entrada"
        MONTHLY = "MONTHLY", "Cuota mensual"
        REINFORCEMENT = "REINFORCEMENT", "Refuerzo anual"
        KEYS = "KEYS", "Entrega de llaves"

    plan = models.ForeignKey(
        PropertyPurchasePlan, on_delete=models.CASCADE, related_name="payment_series"
    )
    kind = models.CharField(max_length=20, choices=Kind)
    first_due_date = models.DateField()
    occurrence_count = models.PositiveIntegerField()
    interval_months = models.PositiveSmallIntegerField()
    base_amount = models.DecimalField(max_digits=14, decimal_places=2)
    applies_cub = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["first_due_date", "kind"]
        constraints = [
            models.UniqueConstraint(fields=["plan", "kind"], name="unique_payment_series_kind"),
            models.CheckConstraint(
                condition=models.Q(occurrence_count__gt=0), name="payment_series_count_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(interval_months__gt=0), name="payment_series_interval_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(base_amount__gt=0), name="payment_series_amount_positive"
            ),
        ]
        verbose_name = "Serie de pagos"
        verbose_name_plural = "Series de pagos"

    def __str__(self):
        return f"{self.plan} — {self.get_kind_display()}"


class PaymentObligation(models.Model):
    series = models.ForeignKey(PaymentSeries, on_delete=models.PROTECT, related_name="obligations")
    sequence = models.PositiveIntegerField()
    due_date = models.DateField()
    base_amount = models.DecimalField(max_digits=14, decimal_places=2)
    applies_cub = models.BooleanField(default=True)
    locked_cub = models.ForeignKey(
        CubIndexValue,
        on_delete=models.PROTECT,
        related_name="locked_obligations",
        null=True,
        blank=True,
    )
    calculation_base_cub_value = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    locked_cub_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    adjusted_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    final_amount_override = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    settled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["due_date", "series__kind", "sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["series", "sequence"], name="unique_obligation_sequence"
            ),
            models.CheckConstraint(
                condition=models.Q(base_amount__gt=0), name="payment_obligation_amount_positive"
            ),
        ]
        indexes = [models.Index(fields=["due_date"])]
        verbose_name = "Obligación de pago"
        verbose_name_plural = "Obligaciones de pago"

    def __str__(self):
        return f"{self.series.get_kind_display()} #{self.sequence} — {self.due_date}"


class PaymentTransaction(models.Model):
    obligation = models.ForeignKey(
        PaymentObligation, on_delete=models.PROTECT, related_name="transactions"
    )
    paid_on = models.DateField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    note = models.CharField(max_length=240, blank=True, default="")
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.CharField(max_length=240, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-paid_on", "-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="payment_transaction_amount_positive"
            )
        ]
        verbose_name = "Pago realizado"
        verbose_name_plural = "Pagos realizados"

    def __str__(self):
        return f"{self.obligation} — R$ {self.amount}"
