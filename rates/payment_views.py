import datetime
import json
from decimal import Decimal

from django.conf import settings
from django.db import models, transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from rates.forms import (
    CubIndexValueForm,
    PaymentObligationForm,
    PaymentPlanSetupForm,
    PaymentTransactionForm,
)
from rates.models import (
    CubIndexValue,
    CurrencyPair,
    ExchangeRate,
    PaymentObligation,
    PaymentSeries,
    PaymentTransaction,
    PropertyPurchasePlan,
)
from rates.services.cub_fetcher import (
    DEFAULT_CUB_CURRENT_SOURCE_URL,
    DEFAULT_CUB_SOURCE_URL,
    CubFetchError,
    fetch_cub_history,
)
from rates.services.payment_calculations import (
    active_payment_total,
    add_months,
    adjusted_amount,
    calculate_obligation,
    month_start,
    payment_status,
)


def _plan_or_default(plan_id=None):
    plans = PropertyPurchasePlan.objects.filter(archived_at__isnull=True)
    if plan_id is not None:
        return get_object_or_404(plans, pk=plan_id)
    return plans.first()


@require_http_methods(["GET"])
def payments(request, plan_id=None):
    plan = _plan_or_default(plan_id)
    if plan is None:
        return render(
            request,
            "rates/payments.html",
            {"plan": None, "setup_form": PaymentPlanSetupForm()},
        )
    return render(request, "rates/payments.html", _workspace_context(plan))


@require_http_methods(["GET"])
def payment_plan_new(request):
    return render(
        request,
        "rates/payments.html",
        {"plan": None, "setup_form": PaymentPlanSetupForm(), "creating_additional": True},
    )


@require_http_methods(["POST"])
def payment_plan_create(request):
    form = PaymentPlanSetupForm(request.POST)
    preview = form.schedule_preview() if form.is_valid() else []
    if request.POST.get("action") != "save" or not form.is_valid():
        return render(
            request,
            "rates/payments.html",
            {"plan": None, "setup_form": form, "schedule_preview": preview},
            status=200 if form.is_valid() else 400,
        )

    data = form.cleaned_data
    with transaction.atomic():
        base_cub, _ = CubIndexValue.objects.update_or_create(
            series=CubIndexValue.Series.SC_STANDARD,
            applicable_month=data["base_cub_month"],
            defaults={
                "reference_month": _previous_month(data["base_cub_month"]),
                "value": data["base_cub_value"],
                "source_url": getattr(settings, "CUB_SOURCE_URL", DEFAULT_CUB_SOURCE_URL),
            },
        )
        plan = PropertyPurchasePlan.objects.create(
            name=data["name"],
            contract_date=data["contract_date"],
            base_cub=base_cub,
            base_cub_value=data["base_cub_value"],
        )
        specs = _series_specs(data)
        preview_by_kind = {}
        for kind, sequence, due_date, amount, applies_cub in preview:
            preview_by_kind.setdefault(kind, []).append((sequence, due_date, amount, applies_cub))
        for kind, spec in specs.items():
            series = PaymentSeries.objects.create(
                plan=plan,
                kind=kind,
                first_due_date=spec["first_due_date"],
                occurrence_count=spec["count"],
                interval_months=spec["interval"],
                base_amount=spec["amount"],
                applies_cub=spec["applies_cub"],
            )
            PaymentObligation.objects.bulk_create(
                [
                    PaymentObligation(
                        series=series,
                        sequence=sequence,
                        due_date=due_date,
                        base_amount=amount,
                        applies_cub=applies_cub,
                    )
                    for sequence, due_date, amount, applies_cub in preview_by_kind[kind]
                ]
            )
    return redirect("rates:payments_plan", plan_id=plan.pk)


@require_http_methods(["GET", "POST"])
def payment_plan_edit(request, plan_id):
    plan = get_object_or_404(PropertyPurchasePlan, pk=plan_id)
    if request.method == "GET":
        form = PaymentPlanSetupForm(initial=_plan_form_initial(plan))
        return render(
            request,
            "rates/payments.html",
            {
                "plan": None,
                "editing_plan": plan,
                "setup_form": form,
                "protected_obligation_count": _protected_obligations(plan).count(),
            },
        )

    form = PaymentPlanSetupForm(request.POST)
    if form.is_valid():
        conflicts = _plan_edit_conflicts(plan, _series_specs(form.cleaned_data))
        for message in conflicts:
            form.add_error(None, message)
    if not form.is_valid():
        return render(
            request,
            "rates/payments.html",
            {
                "plan": None,
                "editing_plan": plan,
                "setup_form": form,
                "protected_obligation_count": _protected_obligations(plan).count(),
            },
            status=400,
        )

    with transaction.atomic():
        _update_payment_plan(plan, form.cleaned_data)
    return redirect("rates:payments_plan", plan_id=plan.pk)


@require_http_methods(["POST"])
def cub_add(request, plan_id):
    plan = get_object_or_404(PropertyPurchasePlan, pk=plan_id)
    form = CubIndexValueForm(request.POST)
    if not form.is_valid():
        return _render_workspace(
            request, plan, cub_form=form, status=_validation_error_status(request)
        )
    _save_cub(plan, form)
    return _render_or_redirect(request, plan)


def _save_cub(plan, form):
    data = form.cleaned_data
    cub, _ = CubIndexValue.objects.update_or_create(
        series=plan.cub_series,
        applicable_month=data["applicable_month"],
        defaults={
            "reference_month": form.reference_month(),
            "value": data["value"],
            "monthly_variation": data.get("monthly_variation"),
            "source_url": data.get("source_url")
            or getattr(settings, "CUB_SOURCE_URL", DEFAULT_CUB_SOURCE_URL),
        },
    )
    _apply_exact_cub(plan, cub)
    return cub


@require_http_methods(["GET"])
def cub_preview(request, plan_id):
    plan = get_object_or_404(PropertyPurchasePlan, pk=plan_id)
    source_url = getattr(settings, "CUB_SOURCE_URL", DEFAULT_CUB_SOURCE_URL)
    current_source_url = getattr(
        settings, "CUB_CURRENT_SOURCE_URL", DEFAULT_CUB_CURRENT_SOURCE_URL
    )
    try:
        found = fetch_cub_history(source_url, current_source_url)
        existing = {
            item.applicable_month: item
            for item in CubIndexValue.objects.filter(series=plan.cub_series)
        }
        previews = []
        for item in found[:18]:
            current = existing.get(item.applicable_month)
            value_changed = current is not None and current.value != item.value
            proposed_variation = item.monthly_variation
            if proposed_variation is None and current is not None:
                proposed_variation = current.monthly_variation
            variation_changed = (
                current is not None and current.monthly_variation != proposed_variation
            )
            if current is None or value_changed or variation_changed:
                delta = item.value - current.value if current is not None else None
                delta_percent = (
                    (delta / current.value * Decimal("100")).quantize(Decimal("0.01"))
                    if current is not None and current.value
                    else None
                )
                previews.append(
                    {
                        "item": item,
                        "current": current,
                        "changed": current is not None,
                        "value_changed": value_changed,
                        "variation_changed": variation_changed,
                        "proposed_variation": proposed_variation,
                        "delta": delta,
                        "delta_percent": delta_percent,
                    }
                )
        context = {
            "plan": plan,
            "previews": previews,
            "source_url": current_source_url,
            "history_source_url": source_url,
        }
    except CubFetchError as exc:
        context = {
            "plan": plan,
            "cub_preview_error": str(exc),
            "source_url": current_source_url,
            "history_source_url": source_url,
        }
    return render(request, "rates/partials/cub_preview.html", context)


@require_http_methods(["POST"])
def cub_confirm(request, plan_id):
    return cub_add(request, plan_id)


@require_http_methods(["POST"])
def cub_confirm_batch(request, plan_id):
    plan = get_object_or_404(PropertyPurchasePlan, pk=plan_id)
    source_url = getattr(settings, "CUB_SOURCE_URL", DEFAULT_CUB_SOURCE_URL)
    selected_months = list(dict.fromkeys(request.POST.getlist("selected_month")))
    if not selected_months:
        return render(
            request,
            "rates/partials/cub_preview.html",
            {
                "plan": plan,
                "cub_preview_error": "Selecciona al menos un valor para confirmar.",
                "source_url": source_url,
            },
        )

    forms = []
    for month in selected_months[:18]:
        form = CubIndexValueForm(
            {
                "applicable_month": month,
                "value": request.POST.get(f"value_{month}", ""),
                "monthly_variation": request.POST.get(f"variation_{month}", ""),
                "source_url": request.POST.get(f"source_{month}", source_url),
            }
        )
        if not form.is_valid():
            return render(
                request,
                "rates/partials/cub_preview.html",
                {
                    "plan": plan,
                    "cub_preview_error": f"El valor propuesto para {month} no es válido.",
                    "source_url": source_url,
                },
            )
        forms.append(form)

    with transaction.atomic():
        for form in forms:
            _save_cub(plan, form)
    return _render_or_redirect(request, plan)


@require_http_methods(["POST"])
def payment_add(request, plan_id, obligation_id):
    plan = get_object_or_404(PropertyPurchasePlan, pk=plan_id)
    obligation = get_object_or_404(
        PaymentObligation.objects.select_related("series"), pk=obligation_id, series__plan=plan
    )
    form = PaymentTransactionForm(request.POST)
    if not form.is_valid():
        return _render_workspace(
            request,
            plan,
            payment_form=form,
            payment_obligation_id=obligation.pk,
            status=_validation_error_status(request),
        )
    with transaction.atomic():
        if obligation.calculation_base_cub_value is None:
            obligation.calculation_base_cub_value = plan.base_cub_value
            obligation.save(update_fields=["calculation_base_cub_value", "updated_at"])
        _lock_obligation_if_exact(obligation, plan)
        payment = form.save(commit=False)
        payment.obligation = obligation
        payment.save()
        _auto_settle(obligation, plan)
    return _render_or_redirect(request, plan)


@require_http_methods(["POST"])
def special_payment_save(request, plan_id, obligation_id):
    plan = get_object_or_404(PropertyPurchasePlan, pk=plan_id)
    obligation = get_object_or_404(
        PaymentObligation.objects.select_related("series"),
        pk=obligation_id,
        series__plan=plan,
    )
    if obligation.series.kind == PaymentSeries.Kind.MONTHLY:
        return HttpResponse("Esta acción es solo para pagos especiales.", status=400)
    payment = None
    transaction_id = request.POST.get("transaction_id")
    if transaction_id:
        payment = get_object_or_404(
            PaymentTransaction,
            pk=transaction_id,
            obligation=obligation,
            voided_at__isnull=True,
        )
    form = PaymentTransactionForm(request.POST, instance=payment)
    if not form.is_valid():
        return _render_workspace(
            request,
            plan,
            payment_form=form,
            payment_obligation_id=obligation.pk,
            status=_validation_error_status(request),
        )
    with transaction.atomic():
        if obligation.calculation_base_cub_value is None:
            obligation.calculation_base_cub_value = plan.base_cub_value
            obligation.save(update_fields=["calculation_base_cub_value", "updated_at"])
        _lock_obligation_if_exact(obligation, plan)
        item = form.save(commit=False)
        item.obligation = obligation
        item.save()
        obligation.settled_at = None
        obligation.save(update_fields=["settled_at", "updated_at"])
        _auto_settle(obligation, plan)
    return _render_or_redirect(request, plan)


@require_http_methods(["POST"])
def payment_void(request, plan_id, transaction_id):
    plan = get_object_or_404(PropertyPurchasePlan, pk=plan_id)
    item = get_object_or_404(
        PaymentTransaction.objects.select_related("obligation__series"),
        pk=transaction_id,
        obligation__series__plan=plan,
    )
    if item.voided_at is None:
        item.voided_at = timezone.now()
        item.void_reason = request.POST.get("void_reason", "").strip() or "Corrección manual"
        item.save(update_fields=["voided_at", "void_reason"])
        obligation = item.obligation
        obligation.settled_at = None
        obligation.save(update_fields=["settled_at", "updated_at"])
        _auto_settle(obligation, plan)
    return _render_or_redirect(request, plan)


@require_http_methods(["POST"])
def obligation_update(request, plan_id, obligation_id):
    plan = get_object_or_404(PropertyPurchasePlan, pk=plan_id)
    obligation = get_object_or_404(PaymentObligation, pk=obligation_id, series__plan=plan)
    is_protected = obligation.settled_at is not None or obligation.transactions.exists()
    form = PaymentObligationForm(request.POST, instance=obligation)
    if not form.is_valid():
        return _render_workspace(
            request,
            plan,
            obligation_form=form,
            edit_obligation_id=obligation.pk,
            status=_validation_error_status(request),
        )
    item = form.save(commit=False)
    if not is_protected:
        item.locked_cub = None
        item.locked_cub_value = None
        item.adjusted_amount = None
    item.save()
    return _render_or_redirect(request, plan)


@require_http_methods(["POST"])
def obligation_settle(request, plan_id, obligation_id):
    plan = get_object_or_404(PropertyPurchasePlan, pk=plan_id)
    obligation = get_object_or_404(PaymentObligation, pk=obligation_id, series__plan=plan)
    paid = active_payment_total(obligation.transactions.all())
    raw_final = request.POST.get("final_amount_override", "").strip()
    try:
        final_amount = Decimal(raw_final) if raw_final else paid
    except Exception:
        return HttpResponse("Monto final inválido.", status=400)
    if final_amount <= 0 or paid <= 0:
        return HttpResponse("Registra al menos un pago antes de cerrar la obligación.", status=400)
    obligation.final_amount_override = final_amount
    obligation.settled_at = timezone.now()
    obligation.save(update_fields=["final_amount_override", "settled_at", "updated_at"])
    return _render_or_redirect(request, plan)


def _series_specs(data):
    specs = {
        PaymentSeries.Kind.MONTHLY: {
            "first_due_date": data["monthly_first_due_date"],
            "count": data["monthly_count"],
            "interval": 1,
            "amount": data["monthly_amount"],
            "applies_cub": data["monthly_applies_cub"],
        }
    }
    if data.get("down_payment_enabled"):
        specs[PaymentSeries.Kind.DOWN_PAYMENT] = {
            "first_due_date": data["down_payment_first_due_date"],
            "count": data["down_payment_count"],
            "interval": data["down_payment_interval_months"],
            "amount": data["down_payment_amount"],
            "applies_cub": data["down_payment_applies_cub"],
        }
    if data.get("reinforcement_enabled"):
        specs[PaymentSeries.Kind.REINFORCEMENT] = {
            "first_due_date": data["reinforcement_first_due_date"],
            "count": data["reinforcement_count"],
            "interval": 12,
            "amount": data["reinforcement_amount"],
            "applies_cub": data["reinforcement_applies_cub"],
        }
    if data.get("keys_enabled"):
        specs[PaymentSeries.Kind.KEYS] = {
            "first_due_date": data["keys_due_date"],
            "count": 1,
            "interval": 1,
            "amount": data["keys_amount"],
            "applies_cub": data["keys_applies_cub"],
        }
    return specs


def _plan_form_initial(plan):
    series = {item.kind: item for item in plan.payment_series.all()}
    monthly = series[PaymentSeries.Kind.MONTHLY]
    down_payment = series.get(PaymentSeries.Kind.DOWN_PAYMENT)
    reinforcement = series.get(PaymentSeries.Kind.REINFORCEMENT)
    keys = series.get(PaymentSeries.Kind.KEYS)
    return {
        "name": plan.name,
        "contract_date": plan.contract_date,
        "base_cub_month": plan.base_cub.applicable_month,
        "base_cub_value": plan.base_cub_value,
        "down_payment_enabled": down_payment is not None,
        "down_payment_first_due_date": (down_payment.first_due_date if down_payment else None),
        "down_payment_count": down_payment.occurrence_count if down_payment else None,
        "down_payment_interval_months": (down_payment.interval_months if down_payment else 1),
        "down_payment_amount": down_payment.base_amount if down_payment else None,
        "down_payment_applies_cub": down_payment.applies_cub if down_payment else False,
        "monthly_first_due_date": monthly.first_due_date,
        "monthly_count": monthly.occurrence_count,
        "monthly_amount": monthly.base_amount,
        "monthly_applies_cub": monthly.applies_cub,
        "reinforcement_enabled": reinforcement is not None,
        "reinforcement_first_due_date": (reinforcement.first_due_date if reinforcement else None),
        "reinforcement_count": reinforcement.occurrence_count if reinforcement else None,
        "reinforcement_amount": reinforcement.base_amount if reinforcement else None,
        "reinforcement_applies_cub": reinforcement.applies_cub if reinforcement else True,
        "keys_enabled": keys is not None,
        "keys_due_date": keys.first_due_date if keys else None,
        "keys_amount": keys.base_amount if keys else None,
        "keys_applies_cub": keys.applies_cub if keys else True,
    }


def _protected_obligations(plan):
    transaction_obligation_ids = PaymentTransaction.objects.values_list("obligation_id", flat=True)
    return PaymentObligation.objects.filter(series__plan=plan).filter(
        models.Q(settled_at__isnull=False) | models.Q(pk__in=transaction_obligation_ids)
    )


def _plan_edit_conflicts(plan, specs):
    conflicts = []
    existing_series = {item.kind: item for item in plan.payment_series.all()}
    for kind, series in existing_series.items():
        protected = _protected_obligations(plan).filter(series=series)
        if kind not in specs and protected.exists():
            conflicts.append(
                f"No puedes quitar {series.get_kind_display().lower()} porque tiene pagos "
                "registrados. Edita esas obligaciones manualmente."
            )
            continue
        if kind in specs:
            highest_protected = (
                protected.order_by("-sequence").values_list("sequence", flat=True).first()
            )
            if highest_protected and specs[kind]["count"] < highest_protected:
                conflicts.append(
                    f"{series.get_kind_display()} #{highest_protected} ya tiene pagos; "
                    f"la cantidad no puede bajar de {highest_protected}."
                )
    return conflicts


def _update_payment_plan(plan, data):
    _snapshot_protected_base_cub(plan)
    base_cub, _ = CubIndexValue.objects.update_or_create(
        series=plan.cub_series,
        applicable_month=data["base_cub_month"],
        defaults={
            "reference_month": _previous_month(data["base_cub_month"]),
            "value": data["base_cub_value"],
            "source_url": getattr(settings, "CUB_SOURCE_URL", DEFAULT_CUB_SOURCE_URL),
        },
    )
    plan.name = data["name"]
    plan.contract_date = data["contract_date"]
    plan.base_cub = base_cub
    plan.base_cub_value = data["base_cub_value"]
    plan.save(update_fields=["name", "contract_date", "base_cub", "base_cub_value", "updated_at"])

    specs = _series_specs(data)
    existing_series = {item.kind: item for item in plan.payment_series.all()}
    for kind, series in list(existing_series.items()):
        if kind in specs:
            continue
        protected_ids = _protected_obligations(plan).filter(series=series).values("pk")
        series.obligations.exclude(pk__in=protected_ids).delete()
        if not series.obligations.exists():
            series.delete()

    for kind, spec in specs.items():
        series, _ = PaymentSeries.objects.get_or_create(
            plan=plan,
            kind=kind,
            defaults={
                "first_due_date": spec["first_due_date"],
                "occurrence_count": spec["count"],
                "interval_months": spec["interval"],
                "base_amount": spec["amount"],
                "applies_cub": spec["applies_cub"],
            },
        )
        series.first_due_date = spec["first_due_date"]
        series.occurrence_count = spec["count"]
        series.interval_months = spec["interval"]
        series.base_amount = spec["amount"]
        series.applies_cub = spec["applies_cub"]
        series.save()

        existing = {
            item.sequence: item for item in series.obligations.prefetch_related("transactions")
        }
        for sequence in range(1, spec["count"] + 1):
            due_date = add_months(spec["first_due_date"], (sequence - 1) * spec["interval"])
            obligation = existing.get(sequence)
            if obligation is None:
                PaymentObligation.objects.create(
                    series=series,
                    sequence=sequence,
                    due_date=due_date,
                    base_amount=spec["amount"],
                    applies_cub=spec["applies_cub"],
                )
                continue
            is_protected = obligation.settled_at is not None or bool(obligation.transactions.all())
            if is_protected:
                continue
            obligation.due_date = due_date
            obligation.base_amount = spec["amount"]
            obligation.applies_cub = spec["applies_cub"]
            obligation.locked_cub = None
            obligation.calculation_base_cub_value = None
            obligation.locked_cub_value = None
            obligation.adjusted_amount = None
            obligation.final_amount_override = None
            obligation.save()

        for sequence, obligation in existing.items():
            if sequence <= spec["count"]:
                continue
            is_protected = obligation.settled_at is not None or bool(obligation.transactions.all())
            if not is_protected:
                obligation.delete()


def _snapshot_protected_base_cub(plan):
    _protected_obligations(plan).filter(calculation_base_cub_value__isnull=True).update(
        calculation_base_cub_value=plan.base_cub_value
    )


def _previous_month(value):
    if value.month == 1:
        return datetime.date(value.year - 1, 12, 1)
    return datetime.date(value.year, value.month - 1, 1)


def _lock_obligation_if_exact(obligation, plan):
    if obligation.adjusted_amount is not None or obligation.final_amount_override is not None:
        return
    if not obligation.applies_cub:
        obligation.adjusted_amount = obligation.base_amount
        obligation.save(update_fields=["adjusted_amount", "updated_at"])
        return
    cub = CubIndexValue.objects.filter(
        series=plan.cub_series, applicable_month=month_start(obligation.due_date)
    ).first()
    if cub:
        obligation.locked_cub = cub
        obligation.locked_cub_value = cub.value
        obligation.adjusted_amount = adjusted_amount(
            obligation.base_amount,
            cub.value,
            obligation.calculation_base_cub_value or plan.base_cub_value,
        )
        obligation.save(
            update_fields=["locked_cub", "locked_cub_value", "adjusted_amount", "updated_at"]
        )


def _apply_exact_cub(plan, cub):
    obligations = PaymentObligation.objects.filter(
        series__plan=plan,
        due_date__year=cub.applicable_month.year,
        due_date__month=cub.applicable_month.month,
        applies_cub=True,
    ).prefetch_related("transactions")
    for obligation in obligations:
        has_payments = any(item.voided_at is None for item in obligation.transactions.all())
        if has_payments or obligation.settled_at is not None:
            continue
        obligation.locked_cub = cub
        obligation.locked_cub_value = cub.value
        obligation.adjusted_amount = adjusted_amount(
            obligation.base_amount,
            cub.value,
            obligation.calculation_base_cub_value or plan.base_cub_value,
        )
        obligation.save(
            update_fields=["locked_cub", "locked_cub_value", "adjusted_amount", "updated_at"]
        )


def _auto_settle(obligation, plan):
    transactions = list(obligation.transactions.all())
    paid = active_payment_total(transactions)
    exact_cub = None
    if obligation.applies_cub:
        exact_cub = CubIndexValue.objects.filter(
            series=plan.cub_series, applicable_month=month_start(obligation.due_date)
        ).first()
    calculation = calculate_obligation(obligation, plan, exact_cub=exact_cub)
    if (
        calculation["exact"]
        and calculation["expected"] is not None
        and paid >= calculation["expected"]
    ):
        obligation.settled_at = obligation.settled_at or timezone.now()
        obligation.save(update_fields=["settled_at", "updated_at"])


def _workspace_context(plan, **overrides):
    today = timezone.localdate()
    current_month = month_start(today)
    cub_values = list(CubIndexValue.objects.filter(series=plan.cub_series))
    cub_by_month = {item.applicable_month: item for item in cub_values}
    latest_cub = next(
        (item for item in cub_values if item.applicable_month <= current_month), plan.base_cub
    )
    obligations = list(
        PaymentObligation.objects.filter(series__plan=plan)
        .select_related("series", "locked_cub")
        .prefetch_related("transactions")
    )
    rows = []
    payment_history = []
    nominal_total = Decimal("0.00")
    expected_total = Decimal("0.00")
    actual_total = Decimal("0.00")
    settled_count = 0
    provisional_count = 0
    for obligation in obligations:
        exact_cub = cub_by_month.get(month_start(obligation.due_date))
        calculation = calculate_obligation(
            obligation, plan, exact_cub=exact_cub, latest_cub=latest_cub
        )
        transactions = list(obligation.transactions.all())
        paid = active_payment_total(transactions)
        status = payment_status(obligation, paid, calculation["expected"], today)
        remaining = None
        variance = None
        paid_vs_base_percent = None
        if calculation["expected"] is not None:
            remaining = max(calculation["expected"] - paid, Decimal("0.00"))
            variance = paid - calculation["expected"] if status == "PAID" else None
            expected_total += calculation["expected"]
        if status == "PAID" and paid > 0:
            paid_vs_base_percent = (
                (paid - obligation.base_amount) / obligation.base_amount * Decimal("100")
            ).quantize(Decimal("0.01"))
        if calculation["source"] == "PROVISIONAL":
            provisional_count += 1
        nominal_total += obligation.base_amount
        actual_total += paid
        if status == "PAID":
            settled_count += 1
        row = {
            "obligation": obligation,
            "kind": obligation.series.kind,
            "kind_label": obligation.series.get_kind_display(),
            "calculation": calculation,
            "paid": paid,
            "paid_vs_base_percent": paid_vs_base_percent,
            "remaining": remaining,
            "variance": variance,
            "status": status,
            "transactions": transactions,
            "editable_payment": next(
                (item for item in transactions if item.voided_at is None), None
            ),
            "additional_active_payment_count": max(
                sum(item.voided_at is None for item in transactions) - 1, 0
            ),
        }
        rows.append(row)
        payment_history.extend({"item": item, "row": row} for item in transactions)
    payment_history.sort(
        key=lambda entry: (entry["item"].paid_on, entry["item"].created_at), reverse=True
    )
    open_rows = [row for row in rows if row["status"] != "PAID"]
    next_rows = []
    if open_rows:
        next_date = min(row["obligation"].due_date for row in open_rows)
        next_rows = [row for row in open_rows if row["obligation"].due_date == next_date]
    next_expected = (
        sum((row["calculation"]["expected"] for row in next_rows), Decimal("0.00"))
        if next_rows and all(row["calculation"]["expected"] is not None for row in next_rows)
        else None
    )
    usd_rate = None
    usd_rate_date = None
    usd_pair = CurrencyPair.objects.filter(code="USD-BRL").first()
    if usd_pair:
        latest_rate = ExchangeRate.objects.filter(pair=usd_pair).order_by("-date").first()
        if latest_rate and latest_rate.rate:
            usd_rate = Decimal(str(latest_rate.rate))
            usd_rate_date = latest_rate.date
    usd_estimate = (
        (next_expected / usd_rate).quantize(Decimal("0.01"))
        if next_expected is not None and usd_rate
        else None
    )
    chart_start = add_months(current_month, -10)
    chart_end = add_months(current_month, 1)
    chart_months = [add_months(chart_start, offset) for offset in range(12)]
    monthly_by_month = {
        month_start(row["obligation"].due_date): row
        for row in rows
        if row["kind"] == PaymentSeries.Kind.MONTHLY
        and chart_start <= month_start(row["obligation"].due_date) <= chart_end
    }
    chart_data = {
        "labels": [month.strftime("%m/%Y") for month in chart_months],
        "base": [
            float(monthly_by_month[month]["obligation"].base_amount)
            if month in monthly_by_month
            else None
            for month in chart_months
        ],
        "adjusted": [
            float(monthly_by_month[month]["calculation"]["expected"])
            if month in monthly_by_month
            and monthly_by_month[month]["calculation"]["expected"] is not None
            else None
            for month in chart_months
        ],
    }
    progress_percent = round(settled_count / len(rows) * 100) if rows else 0
    monthly_rows = [row for row in rows if row["kind"] == PaymentSeries.Kind.MONTHLY]
    special_rows = [row for row in rows if row["kind"] != PaymentSeries.Kind.MONTHLY]
    cub_fetch_url = getattr(settings, "CUB_SOURCE_URL", DEFAULT_CUB_SOURCE_URL)
    cub_current_fetch_url = getattr(
        settings, "CUB_CURRENT_SOURCE_URL", DEFAULT_CUB_CURRENT_SOURCE_URL
    )
    context = {
        "plan": plan,
        "plans": PropertyPurchasePlan.objects.filter(archived_at__isnull=True),
        "rows": rows,
        "monthly_rows": monthly_rows,
        "special_rows": special_rows,
        "payment_history": payment_history,
        "next_rows": next_rows,
        "next_expected": next_expected,
        "usd_rate": usd_rate,
        "usd_rate_date": usd_rate_date,
        "usd_estimate": usd_estimate,
        "nominal_total": nominal_total,
        "expected_total": expected_total,
        "actual_total": actual_total,
        "remaining_total": max(expected_total - actual_total, Decimal("0.00")),
        "settled_count": settled_count,
        "obligation_count": len(rows),
        "provisional_count": provisional_count,
        "progress_percent": progress_percent,
        "cub_values": cub_values[:24],
        "latest_cub": latest_cub,
        "cub_fetch_url": cub_fetch_url,
        "cub_current_fetch_url": cub_current_fetch_url,
        "cub_source_url": latest_cub.source_url or cub_fetch_url,
        "chart_data": json.dumps(chart_data),
        "chart_start": chart_start,
        "chart_end": chart_end,
        "cub_form": CubIndexValueForm(
            initial={"source_url": getattr(settings, "CUB_SOURCE_URL", DEFAULT_CUB_SOURCE_URL)}
        ),
        "payment_form": PaymentTransactionForm(),
        "obligation_form": PaymentObligationForm(),
    }
    context.update(overrides)
    return context


def _render_workspace(request, plan, status=200, **overrides):
    template = (
        "rates/partials/payment_workspace.html"
        if request.headers.get("HX-Request")
        else "rates/payments.html"
    )
    return render(request, template, _workspace_context(plan, **overrides), status=status)


def _validation_error_status(request):
    """HTMX only swaps successful responses, so render validation errors with 200."""
    return 200 if request.headers.get("HX-Request") else 400


def _render_or_redirect(request, plan):
    if request.headers.get("HX-Request"):
        return _render_workspace(request, plan)
    return redirect("rates:payments_plan", plan_id=plan.pk)
