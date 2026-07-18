from django.contrib import admin

from rates.models import (
    CubIndexValue,
    CurrencyPair,
    ExchangeRate,
    PairConfig,
    PaymentObligation,
    PaymentSeries,
    PaymentTransaction,
    PropertyPurchasePlan,
    Purchase,
)


@admin.register(CurrencyPair)
class CurrencyPairAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "api_code", "active"]
    list_editable = ["active"]
    ordering = ["code"]


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ["pair", "date", "rate", "high", "low", "created_at"]
    list_filter = ["pair"]
    ordering = ["-date"]
    search_fields = ["date"]
    date_hierarchy = "date"


@admin.register(PairConfig)
class PairConfigAdmin(admin.ModelAdmin):
    list_display = [
        "pair",
        "monthly_budget",
        "threshold_strong_buy",
        "threshold_moderate_buy",
        "threshold_do_not_buy",
    ]


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ["pair", "date", "amount_spent", "amount_received", "effective_rate", "note"]
    list_filter = ["pair"]
    ordering = ["-date"]
    date_hierarchy = "date"


@admin.register(CubIndexValue)
class CubIndexValueAdmin(admin.ModelAdmin):
    list_display = ["series", "applicable_month", "reference_month", "value", "monthly_variation"]
    list_filter = ["series"]
    ordering = ["-applicable_month"]
    date_hierarchy = "applicable_month"


@admin.register(PropertyPurchasePlan)
class PropertyPurchasePlanAdmin(admin.ModelAdmin):
    list_display = ["name", "contract_date", "base_cub_value", "archived_at"]
    ordering = ["name"]


@admin.register(PaymentSeries)
class PaymentSeriesAdmin(admin.ModelAdmin):
    list_display = [
        "plan",
        "kind",
        "first_due_date",
        "occurrence_count",
        "base_amount",
        "applies_cub",
    ]
    list_filter = ["plan", "kind", "applies_cub"]


@admin.register(PaymentObligation)
class PaymentObligationAdmin(admin.ModelAdmin):
    list_display = [
        "series",
        "sequence",
        "due_date",
        "base_amount",
        "adjusted_amount",
        "settled_at",
    ]
    list_filter = ["series__plan", "series__kind", "applies_cub"]
    date_hierarchy = "due_date"


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ["obligation", "paid_on", "amount", "voided_at", "note"]
    list_filter = ["obligation__series__plan"]
    date_hierarchy = "paid_on"
