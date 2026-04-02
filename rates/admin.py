from django.contrib import admin
from rates.models import ExchangeRate, UserConfig


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ["date", "rate", "high", "low", "created_at"]
    ordering = ["-date"]
    search_fields = ["date"]
    date_hierarchy = "date"


@admin.register(UserConfig)
class UserConfigAdmin(admin.ModelAdmin):
    list_display = [
        "monthly_usd_budget",
        "threshold_strong_buy",
        "threshold_moderate_buy",
        "threshold_do_not_buy",
    ]

    def has_add_permission(self, request):
        return not UserConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
