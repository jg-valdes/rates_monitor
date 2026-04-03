from django.contrib import admin

from rates.models import CurrencyPair, ExchangeRate, PairConfig, Purchase


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
