import json
import logging

from django.conf import settings
from django.core import signing
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
import hmac

from rates.models import CurrencyPair, ExchangeRate, PairConfig, Purchase
from rates.services.cross_pair import compute_cross_pair
from rates.services.decision import build_decision
from rates.services.fetcher import fetch_and_store
from rates.services.indicators import compute_all, compute_rolling_ma

logger = logging.getLogger(__name__)

# ── Auth ──────────────────────────────────────────────────────────────────────


def login_view(request):
    if request.method == "POST":
        submitted = request.POST.get("passcode", "")
        expected = getattr(settings, "ACCESS_PASSCODE", "")
        if expected and hmac.compare_digest(submitted, expected):
            token = signing.dumps("ok")
            response = redirect(request.GET.get("next", "/"))
            response.set_cookie(
                "rm_access",
                token,
                max_age=86400,
                httponly=True,
                samesite="Lax",
                secure=not settings.DEBUG,
            )
            return response
        return render(request, "rates/login.html", {"error": True})
    return render(request, "rates/login.html", {})


def logout_view(request):
    response = redirect("rates:login")
    response.delete_cookie("rm_access")
    return response


# ── Overview ──────────────────────────────────────────────────────────────────


def overview(request):
    pairs = list(CurrencyPair.objects.filter(active=True))
    pair_ids = [p.id for p in pairs]

    # One query for all rates, pre-grouped by pair
    rates_by_pair: dict[int, list] = {p.id: [] for p in pairs}
    for rate in ExchangeRate.objects.filter(pair_id__in=pair_ids).order_by("date"):
        rates_by_pair[rate.pair_id].append(rate)

    # One query (+ optional bulk insert) for all configs
    configs = {c.pair_id: c for c in PairConfig.objects.filter(pair_id__in=pair_ids)}
    missing = [p for p in pairs if p.id not in configs]
    if missing:
        PairConfig.objects.bulk_create([PairConfig(pair=p) for p in missing])
        configs = {c.pair_id: c for c in PairConfig.objects.filter(pair_id__in=pair_ids)}

    # One aggregation for all purchase totals
    totals_map = {}
    for row in (
        Purchase.objects.filter(pair_id__in=pair_ids)
        .values("pair_id")
        .annotate(total_spent=Sum("amount_spent"), total_received=Sum("amount_received"), count=Count("id"))
    ):
        spent = row["total_spent"] or 0.0
        received = row["total_received"] or 0.0
        totals_map[row["pair_id"]] = {
            "total_spent": round(spent, 2),
            "total_received": round(received, 2),
            "avg_rate": round(received / spent, 6) if spent else 0.0,
            "count": row["count"],
        }

    summaries = []
    for pair in pairs:
        rates_list = rates_by_pair.get(pair.id, [])
        config = configs[pair.id]
        indicators = compute_all(rates_list)
        decision = build_decision(indicators, config) if indicators else None
        summaries.append(
            {
                "pair": pair,
                "indicators": indicators,
                "decision": decision,
                "totals": totals_map.get(pair.id),
            }
        )

    cross = compute_cross_pair()
    return render(request, "rates/overview.html", {"summaries": summaries, "cross": cross})


# ── Dashboard (per pair) ───────────────────────────────────────────────────────


def dashboard(request, pair_code):
    pair = get_object_or_404(CurrencyPair, code=pair_code.upper(), active=True)
    config = _get_or_create_config(pair)
    rates_list = list(ExchangeRate.objects.filter(pair=pair).order_by("date"))
    ctx = _build_context(pair, rates_list, config)
    ctx["purchases"] = Purchase.objects.filter(pair=pair)
    ctx["totals"] = _purchase_totals(pair)
    return render(request, "rates/dashboard.html", ctx)


@require_http_methods(["GET"])
def stats_partial(request, pair_code):
    pair = get_object_or_404(CurrencyPair, code=pair_code.upper(), active=True)
    config = _get_or_create_config(pair)
    rates_list = list(ExchangeRate.objects.filter(pair=pair).order_by("date"))
    indicators = compute_all(rates_list)
    decision = build_decision(indicators, config) if indicators else None
    return render(
        request,
        "rates/partials/stats.html",
        {"pair": pair, "indicators": indicators, "decision": decision, "config": config},
    )


@require_http_methods(["POST"])
def refresh_data(request, pair_code):
    pair = get_object_or_404(CurrencyPair, code=pair_code.upper(), active=True)
    config = _get_or_create_config(pair)
    try:
        fetch_and_store(pair, days=3)
    except Exception:
        logger.warning("refresh_data: fetch_and_store failed for %s", pair.code, exc_info=True)
    rates_list = list(ExchangeRate.objects.filter(pair=pair).order_by("date"))
    indicators = compute_all(rates_list)
    decision = build_decision(indicators, config) if indicators else None
    return render(
        request,
        "rates/partials/stats.html",
        {"pair": pair, "indicators": indicators, "decision": decision, "config": config},
    )


@require_http_methods(["POST"])
def update_config(request, pair_code):
    pair = get_object_or_404(CurrencyPair, code=pair_code.upper(), active=True)
    config = _get_or_create_config(pair)
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

    config.monthly_budget = _float("monthly_budget", config.monthly_budget)
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
            {"pair": pair, "config": config, "saved": True},
        )
    return redirect("rates:dashboard", pair_code=pair.slug)


# ── Purchases ─────────────────────────────────────────────────────────────────


@require_http_methods(["POST"])
def add_purchase(request, pair_code):
    pair = get_object_or_404(CurrencyPair, code=pair_code.upper(), active=True)
    try:
        Purchase.objects.create(
            pair=pair,
            date=request.POST["date"],
            amount_spent=float(request.POST["amount_spent"]),
            amount_received=float(request.POST["amount_received"]),
            note=request.POST.get("note", "").strip(),
        )
    except (KeyError, ValueError):
        pass
    return render(
        request,
        "rates/partials/purchases.html",
        {
            "pair": pair,
            "purchases": Purchase.objects.filter(pair=pair),
            "totals": _purchase_totals(pair),
        },
    )


@require_http_methods(["POST"])
def delete_purchase(request, pair_code, pk):
    pair = get_object_or_404(CurrencyPair, code=pair_code.upper(), active=True)
    Purchase.objects.filter(pk=pk, pair=pair).delete()
    return render(
        request,
        "rates/partials/purchases.html",
        {
            "pair": pair,
            "purchases": Purchase.objects.filter(pair=pair),
            "totals": _purchase_totals(pair),
        },
    )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _purchase_totals(pair) -> dict | None:
    items = list(Purchase.objects.filter(pair=pair))
    if not items:
        return None
    total_spent = sum(p.amount_spent for p in items)
    total_received = sum(p.amount_received for p in items)
    avg_rate = round(total_received / total_spent, 6) if total_spent else 0.0
    return {
        "total_spent": round(total_spent, 2),
        "total_received": round(total_received, 2),
        "avg_rate": avg_rate,
        "count": len(items),
    }


def _get_or_create_config(pair):
    config, _ = PairConfig.objects.get_or_create(pair=pair)
    return config


def _build_context(pair, rates_list, config):
    indicators = compute_all(rates_list)
    decision = build_decision(indicators, config) if indicators else None

    chart_rates = rates_list[-90:]
    values = [r.rate for r in chart_rates]
    chart_data = {
        "labels": [r.date.strftime("%d/%m/%y") for r in chart_rates],
        "values": values,
        "ma30": compute_rolling_ma(values, 30),
        "ma90": compute_rolling_ma(values, 90),
    }

    history = _compute_history(rates_list, config, n=30)

    return {
        "pair": pair,
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
