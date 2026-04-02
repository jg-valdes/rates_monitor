import json

from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from rates.models import ExchangeRate, UserConfig
from rates.services.decision import build_decision
from rates.services.fetcher import fetch_and_store
from rates.services.indicators import compute_all, compute_rolling_ma


def _build_context(rates_list, config):
    indicators = compute_all(rates_list)
    decision = build_decision(indicators, config) if indicators else None

    # Chart data (last 90 points)
    chart_rates = rates_list[-90:]
    values = [r.rate for r in chart_rates]
    chart_data = {
        "labels": [r.date.strftime("%d/%m/%y") for r in chart_rates],
        "values": values,
        "ma30": compute_rolling_ma(values, 30),
        "ma90": compute_rolling_ma(values, 90),
    }

    # History: last 30 dates with their computed signals
    history = _compute_history(rates_list, config, n=30)

    return {
        "indicators": indicators,
        "decision": decision,
        "config": config,
        "chart_data": json.dumps(chart_data),
        "history": history,
        "has_data": bool(rates_list),
    }


def _compute_history(rates_list, config, n=30):
    total = len(rates_list)
    start = max(0, total - n)
    history = []
    for i in range(start, total):
        subset = rates_list[: i + 1]
        if len(subset) < 2:
            continue
        ind = compute_all(subset)
        if ind:
            dec = build_decision(ind, config)
            history.append(
                {
                    "date": rates_list[i].date,
                    "rate": rates_list[i].rate,
                    **dec,
                }
            )
    return list(reversed(history))


def dashboard(request):
    rates_list = list(ExchangeRate.objects.order_by("date"))
    config = UserConfig.get_solo()
    ctx = _build_context(rates_list, config)
    return render(request, "rates/dashboard.html", ctx)


@require_http_methods(["GET"])
def stats_partial(request):
    rates_list = list(ExchangeRate.objects.order_by("date"))
    config = UserConfig.get_solo()
    indicators = compute_all(rates_list)
    decision = build_decision(indicators, config) if indicators else None
    return render(
        request,
        "rates/partials/stats.html",
        {"indicators": indicators, "decision": decision, "config": config},
    )


@require_http_methods(["POST"])
def refresh_data(request):
    """Fetch latest rates then return updated stats partial."""
    try:
        fetch_and_store(days=3)
    except Exception:
        pass  # fail silently — stale data is better than an error page
    rates_list = list(ExchangeRate.objects.order_by("date"))
    config = UserConfig.get_solo()
    indicators = compute_all(rates_list)
    decision = build_decision(indicators, config) if indicators else None
    return render(
        request,
        "rates/partials/stats.html",
        {"indicators": indicators, "decision": decision, "config": config},
    )


@require_http_methods(["POST"])
def update_config(request):
    config = UserConfig.get_solo()
    p = request.POST

    def _float(key, default):
        try:
            return float(p[key])
        except (KeyError, ValueError, TypeError):
            return default

    def _float_or_none(key):
        val = p.get(key, "").strip()
        try:
            return float(val) if val else None
        except ValueError:
            return None

    config.monthly_usd_budget = _float("monthly_usd_budget", config.monthly_usd_budget)
    config.threshold_strong_buy = _float("threshold_strong_buy", config.threshold_strong_buy)
    config.threshold_moderate_buy = _float("threshold_moderate_buy", config.threshold_moderate_buy)
    config.threshold_do_not_buy = _float("threshold_do_not_buy", config.threshold_do_not_buy)
    config.alert_webhook_url = p.get("alert_webhook_url", config.alert_webhook_url).strip()
    config.alert_on_strong_buy = "alert_on_strong_buy" in p
    config.alert_on_deviation_above = _float_or_none("alert_on_deviation_above")
    config.alert_on_rate_above = _float_or_none("alert_on_rate_above")
    config.save()

    if request.headers.get("HX-Request"):
        return render(
            request,
            "rates/partials/config_form.html",
            {"config": config, "saved": True},
        )
    return redirect("dashboard")
