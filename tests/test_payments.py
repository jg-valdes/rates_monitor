import datetime
import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import requests
from django.urls import reverse
from django.utils import timezone

from rates.forms import PaymentPlanSetupForm
from rates.models import (
    CubIndexValue,
    PaymentObligation,
    PaymentSeries,
    PaymentTransaction,
    PropertyPurchasePlan,
)
from rates.services.cub_fetcher import CubFetchError, fetch_cub_history, parse_cub_history
from rates.services.payment_calculations import (
    active_payment_total,
    add_months,
    adjusted_amount,
    calculate_obligation,
    payment_status,
)


def _cub(month=datetime.date(2026, 1, 1), value="3000.00"):
    return CubIndexValue.objects.create(
        reference_month=add_months(month, -1),
        applicable_month=month,
        value=Decimal(value),
        source_url="https://example.com/cub",
    )


def _plan():
    base = _cub()
    plan = PropertyPurchasePlan.objects.create(
        name="Apartamento 301",
        contract_date=datetime.date(2026, 1, 10),
        base_cub=base,
        base_cub_value=base.value,
    )
    series = PaymentSeries.objects.create(
        plan=plan,
        kind=PaymentSeries.Kind.MONTHLY,
        first_due_date=datetime.date(2026, 2, 10),
        occurrence_count=2,
        interval_months=1,
        base_amount=Decimal("1000.00"),
        applies_cub=True,
    )
    first = PaymentObligation.objects.create(
        series=series,
        sequence=1,
        due_date=datetime.date(2026, 2, 10),
        base_amount=Decimal("1000.00"),
    )
    PaymentObligation.objects.create(
        series=series,
        sequence=2,
        due_date=datetime.date(2026, 3, 10),
        base_amount=Decimal("1000.00"),
    )
    return plan, first


class TestPaymentCalculations:
    def test_add_months_clamps_to_month_end(self):
        assert add_months(datetime.date(2026, 1, 31), 1) == datetime.date(2026, 2, 28)

    def test_add_months_handles_leap_year(self):
        assert add_months(datetime.date(2024, 1, 31), 1) == datetime.date(2024, 2, 29)

    def test_adjusted_amount_uses_decimal_half_up(self):
        result = adjusted_amount(Decimal("1000"), Decimal("3033.33"), Decimal("3000"))
        assert result == Decimal("1011.11")

    def test_adjusted_amount_rejects_zero_base(self):
        with pytest.raises(ValueError):
            adjusted_amount(Decimal("1000"), Decimal("3033.33"), Decimal("0"))

    def test_status_prioritizes_explicit_settlement(self):
        obligation = type(
            "Obligation", (), {"settled_at": timezone.now(), "due_date": datetime.date.today()}
        )
        assert (
            payment_status(obligation, Decimal("0"), Decimal("100"), datetime.date.today())
            == "PAID"
        )

    def test_exact_and_provisional_cub_are_distinguished(self):
        obligation = SimpleNamespace(
            final_amount_override=None,
            adjusted_amount=None,
            applies_cub=True,
            base_amount=Decimal("1000"),
            locked_cub=None,
        )
        plan = SimpleNamespace(base_cub_value=Decimal("3000"))
        cub = SimpleNamespace(value=Decimal("3030"))
        exact = calculate_obligation(obligation, plan, exact_cub=cub)
        provisional = calculate_obligation(obligation, plan, latest_cub=cub)
        assert exact == {
            "expected": Decimal("1010.00"),
            "source": "CUB",
            "exact": True,
            "cub": cub,
        }
        assert provisional["expected"] == Decimal("1010.00")
        assert provisional["source"] == "PROVISIONAL"
        assert provisional["exact"] is False

    def test_fixed_manual_and_pending_calculations(self):
        plan = SimpleNamespace(base_cub_value=Decimal("3000"))
        obligation = SimpleNamespace(
            final_amount_override=None,
            adjusted_amount=None,
            applies_cub=False,
            base_amount=Decimal("750"),
            locked_cub=None,
        )
        assert calculate_obligation(obligation, plan)["source"] == "FIXED"
        obligation.applies_cub = True
        assert calculate_obligation(obligation, plan)["source"] == "CUB_PENDING"
        obligation.final_amount_override = Decimal("725")
        assert calculate_obligation(obligation, plan)["expected"] == Decimal("725")

    @pytest.mark.parametrize(
        ("paid", "expected", "due_delta", "expected_status"),
        [
            ("100", "100", 1, "PAID"),
            ("20", "100", 1, "PARTIAL"),
            ("0", "100", -1, "OVERDUE"),
            ("0", "100", 0, "DUE"),
            ("0", "100", 1, "UPCOMING"),
            ("0", None, 1, "CUB_PENDING"),
        ],
    )
    def test_payment_statuses(self, paid, expected, due_delta, expected_status):
        today = datetime.date(2026, 7, 18)
        obligation = SimpleNamespace(
            settled_at=None, due_date=today + datetime.timedelta(days=due_delta)
        )
        expected_value = Decimal(expected) if expected is not None else None
        assert payment_status(obligation, Decimal(paid), expected_value, today) == expected_status

    def test_active_total_ignores_voided_transactions(self):
        transactions = [
            SimpleNamespace(amount=Decimal("50"), voided_at=None),
            SimpleNamespace(amount=Decimal("25"), voided_at=timezone.now()),
        ]
        assert active_payment_total(transactions) == Decimal("50.00")


class TestCubParser:
    def test_parses_standard_and_excludes_desonerado(self):
        html = """
        <h2>CUB/2006 - ANO 2026</h2>
        <h3>CUB / Julho 2026</h3><p>R$ 3.121,62</p><p>variação +0,82%</p>
        <h2>CUB/Desonerado - ANO 2026</h2>
        <h3>CUB / Julho 2026</h3><p>R$ 2.913,10</p><p>variação +0,84%</p>
        """
        results = parse_cub_history(html)
        assert len(results) == 1
        assert results[0].applicable_month == datetime.date(2026, 7, 1)
        assert results[0].reference_month == datetime.date(2026, 6, 1)
        assert results[0].value == Decimal("3121.62")
        assert results[0].monthly_variation == Decimal("0.82")

    def test_rejects_unexpected_html(self):
        with pytest.raises(CubFetchError):
            parse_cub_history("<html>no index here</html>")

    def test_skips_empty_future_month_without_stealing_the_next_value(self):
        html = """
        <h2>CUB/2006 - ANO 2026</h2>
        <h3>CUB / Agosto 2026</h3><p>R$<br>variação %</p>
        <h3>CUB / Julho 2026</h3><p>R$ 3.121,62<br>variação +0,82%</p>
        <h3>CUB / Junho 2026</h3><p>R$ 3.096,25<br>variação +1,05%</p>
        """

        results = parse_cub_history(html)

        assert [item.applicable_month for item in results] == [
            datetime.date(2026, 7, 1),
            datetime.date(2026, 6, 1),
        ]
        assert [item.value for item in results] == [Decimal("3121.62"), Decimal("3096.25")]

    def test_fetch_preserves_the_exact_source_url(self):
        response = SimpleNamespace(
            text="<h3>CUB / Julho 2026</h3><p>R$ 3.121,62</p>",
            raise_for_status=lambda: None,
        )
        source_url = "https://official.example/cub-history"
        with patch("rates.services.cub_fetcher.requests.get", return_value=response) as get:
            results = fetch_cub_history(source_url)

        get.assert_called_once_with(source_url, timeout=15)
        assert results[0].source_url == source_url

    def test_fetch_wraps_network_failures(self):
        with (
            patch(
                "rates.services.cub_fetcher.requests.get",
                side_effect=requests.RequestException("timeout"),
            ),
            pytest.raises(CubFetchError, match="No se pudo consultar"),
        ):
            fetch_cub_history()


@pytest.mark.django_db
class TestPaymentPlanSetup:
    def _payload(self, action="preview"):
        return {
            "action": action,
            "name": "Casa Brava",
            "contract_date": "2026-01-12",
            "base_cub_month": "2026-01",
            "base_cub_value": "3000.00",
            "down_payment_enabled": "on",
            "down_payment_first_due_date": "2025-11-15",
            "down_payment_count": "3",
            "down_payment_interval_months": "1",
            "down_payment_amount": "15000.00",
            "monthly_first_due_date": "2026-02-28",
            "monthly_count": "3",
            "monthly_amount": "1000.00",
            "monthly_applies_cub": "on",
            "reinforcement_enabled": "on",
            "reinforcement_first_due_date": "2026-12-15",
            "reinforcement_count": "2",
            "reinforcement_amount": "5000.00",
            "reinforcement_applies_cub": "on",
            "keys_enabled": "on",
            "keys_due_date": "2028-06-30",
            "keys_amount": "20000.00",
            "keys_applies_cub": "on",
        }

    def test_empty_workspace_shows_setup(self, client):
        response = client.get(reverse("rates:payments"))
        body = response.content.decode()
        assert response.status_code == 200
        assert "Configura tu vivienda" in body
        assert 'type="date"' in body
        assert 'type="month"' in body
        assert "money-input" in body
        assert "showPicker" in body

    def test_preview_does_not_write(self, client):
        response = client.post(reverse("rates:payment_plan_create"), self._payload())
        body = response.content.decode()
        assert response.status_code == 200
        assert "9 obligaciones serán creadas" in body
        assert "Entrada #3" in body
        assert 'value="2026-01-12"' in body
        assert 'value="2026-01"' in body
        assert not PropertyPurchasePlan.objects.exists()

    def test_save_generates_all_obligations(self, client):
        response = client.post(reverse("rates:payment_plan_create"), self._payload(action="save"))
        plan = PropertyPurchasePlan.objects.get()
        assert response.status_code == 302
        assert response.url == reverse("rates:payments_plan", kwargs={"plan_id": plan.pk})
        assert plan.payment_series.count() == 4
        assert PaymentObligation.objects.filter(series__plan=plan).count() == 9
        entrance = plan.payment_series.get(kind=PaymentSeries.Kind.DOWN_PAYMENT)
        assert entrance.applies_cub is False
        assert list(entrance.obligations.values_list("due_date", flat=True)) == [
            datetime.date(2025, 11, 15),
            datetime.date(2025, 12, 15),
            datetime.date(2026, 1, 15),
        ]

    def test_enabled_group_requires_its_fields(self, client):
        payload = self._payload()
        payload.pop("reinforcement_amount")
        response = client.post(reverse("rates:payment_plan_create"), payload)
        assert response.status_code == 400
        assert "obligatorio" in response.content.decode()

    def test_invalid_form_has_no_schedule_preview(self):
        form = PaymentPlanSetupForm({})
        assert form.schedule_preview() == []


@pytest.mark.django_db
class TestPaymentWorkspace:
    def test_dashboard_renders_plan_and_navigation(self, client):
        plan, _ = _plan()
        response = client.get(reverse("rates:payments_plan", kwargs={"plan_id": plan.pk}))
        body = response.content.decode()
        assert response.status_code == 200
        assert "Apartamento 301" in body
        assert "Vivienda" in body
        assert "data-mobile-nav" in body
        assert "order-3" in body
        assert "Variación de la cuota mensual" in body
        assert "Índice CUB-SC vigente" in body
        assert body.count("Consultar fuente") == 1
        assert "URL consultada por el importador" in body
        assert "https://www.sindusconbc.com.br/cub/" in body
        assert 'href="https://example.com/cub"' in body
        assert "Abre la publicación original" in body
        assert "Ver fuente ↗" in body
        assert "Plan de cuotas" in body
        assert "Pagos registrados" in body
        assert "lg:col-span-8" in body
        assert "lg:col-span-4" in body
        assert 'value="1000.00"' in body
        assert 'value="1000.000000"' not in body

    def test_payment_chart_uses_rolling_window_through_next_month(self, client):
        plan, _ = _plan()
        with patch(
            "rates.payment_views.timezone.localdate",
            return_value=datetime.date(2026, 4, 18),
        ):
            response = client.get(reverse("rates:payments_plan", kwargs={"plan_id": plan.pk}))
        chart = json.loads(response.context["chart_data"])
        assert chart["labels"] == [
            "06/2025",
            "07/2025",
            "08/2025",
            "09/2025",
            "10/2025",
            "11/2025",
            "12/2025",
            "01/2026",
            "02/2026",
            "03/2026",
            "04/2026",
            "05/2026",
        ]
        assert chart["base"][-4:-2] == [1000.0, 1000.0]
        assert chart["base"][-2:] == [None, None]

    def test_htmx_validation_error_is_visible(self, client):
        plan, _ = _plan()
        response = client.post(
            reverse("rates:cub_add", kwargs={"plan_id": plan.pk}),
            {"applicable_month": "2026-02", "value": "3030.001"},
            HTTP_HX_REQUEST="true",
        )
        body = response.content.decode()
        assert response.status_code == 200
        assert "No se pudo guardar el cambio" in body
        assert "Valor CUB" in body

    def test_special_payments_are_collapsed_above_monthly_tables_and_can_be_paid(self, client):
        plan, _ = _plan()
        series = PaymentSeries.objects.create(
            plan=plan,
            kind=PaymentSeries.Kind.DOWN_PAYMENT,
            first_due_date=datetime.date(2025, 11, 15),
            occurrence_count=1,
            interval_months=1,
            base_amount=Decimal("15000.00"),
            applies_cub=False,
        )
        entrance = PaymentObligation.objects.create(
            series=series,
            sequence=1,
            due_date=datetime.date(2025, 11, 15),
            base_amount=Decimal("15000.00"),
            applies_cub=False,
        )
        response = client.get(reverse("rates:payments_plan", kwargs={"plan_id": plan.pk}))
        body = response.content.decode()
        assert body.index("Pagos especiales") < body.index("Plan de cuotas")
        assert '<details class="group mb-5' in body
        assert (
            reverse(
                "rates:special_payment_save",
                kwargs={"plan_id": plan.pk, "obligation_id": entrance.pk},
            )
            in body
        )
        assert entrance not in [row["obligation"] for row in response.context["monthly_rows"]]

        payment_response = client.post(
            reverse(
                "rates:special_payment_save",
                kwargs={"plan_id": plan.pk, "obligation_id": entrance.pk},
            ),
            {"paid_on": "2025-11-15", "amount": "15000.00", "note": "Entrada 1"},
            HTTP_HX_REQUEST="true",
        )
        entrance.refresh_from_db()
        assert payment_response.status_code == 200
        assert entrance.settled_at is not None
        payment = entrance.transactions.get()
        assert payment.note == "Entrada 1"
        saved_body = payment_response.content.decode()
        assert f'name="transaction_id" value="{payment.pk}"' in saved_body
        assert 'value="15000.00"' in saved_body
        assert 'value="Entrada 1"' in saved_body

        update_response = client.post(
            reverse(
                "rates:special_payment_save",
                kwargs={"plan_id": plan.pk, "obligation_id": entrance.pk},
            ),
            {
                "transaction_id": str(payment.pk),
                "paid_on": "2025-11-16",
                "amount": "14900.00",
                "note": "Entrada corregida",
            },
            HTTP_HX_REQUEST="true",
        )
        entrance.refresh_from_db()
        payment.refresh_from_db()
        assert update_response.status_code == 200
        assert entrance.transactions.count() == 1
        assert entrance.settled_at is None
        assert payment.paid_on == datetime.date(2025, 11, 16)
        assert payment.amount == Decimal("14900.00")
        assert payment.note == "Entrada corregida"

    def test_special_payment_editor_rejects_monthly_obligations(self, client):
        plan, monthly = _plan()
        response = client.post(
            reverse(
                "rates:special_payment_save",
                kwargs={"plan_id": plan.pk, "obligation_id": monthly.pk},
            ),
            {"paid_on": "2026-02-10", "amount": "1000.00"},
        )
        assert response.status_code == 400
        assert not monthly.transactions.exists()

    def test_manual_cub_locks_matching_obligation(self, client):
        plan, first = _plan()
        response = client.post(
            reverse("rates:cub_add", kwargs={"plan_id": plan.pk}),
            {
                "applicable_month": "2026-02",
                "value": "3030.00",
                "monthly_variation": "1.00",
                "source_url": "https://example.com/cub",
            },
        )
        first.refresh_from_db()
        assert response.status_code == 302
        assert first.adjusted_amount == Decimal("1010.00")
        assert first.locked_cub_value == Decimal("3030.00")

    def test_cub_update_never_changes_an_obligation_with_an_active_payment(self, client):
        plan, first = _plan()
        PaymentTransaction.objects.create(
            obligation=first,
            paid_on=datetime.date(2026, 2, 5),
            amount=Decimal("100.00"),
        )

        response = client.post(
            reverse("rates:cub_add", kwargs={"plan_id": plan.pk}),
            {
                "applicable_month": "2026-02",
                "value": "3030.00",
                "source_url": "https://example.com/cub",
            },
        )

        first.refresh_from_db()
        assert response.status_code == 302
        assert first.locked_cub is None
        assert first.locked_cub_value is None
        assert first.adjusted_amount is None

    def test_cub_update_never_changes_a_manually_settled_obligation(self, client):
        plan, first = _plan()
        first.settled_at = timezone.now()
        first.final_amount_override = Decimal("995.00")
        first.save(update_fields=["settled_at", "final_amount_override"])

        response = client.post(
            reverse("rates:cub_add", kwargs={"plan_id": plan.pk}),
            {
                "applicable_month": "2026-02",
                "value": "3030.00",
                "source_url": "https://example.com/cub",
            },
        )

        first.refresh_from_db()
        assert response.status_code == 302
        assert first.final_amount_override == Decimal("995.00")
        assert first.locked_cub is None
        assert first.locked_cub_value is None
        assert first.adjusted_amount is None

    def test_adds_partial_then_full_payment(self, client):
        plan, first = _plan()
        _cub(datetime.date(2026, 2, 1), "3030.00")
        url = reverse("rates:payment_add", kwargs={"plan_id": plan.pk, "obligation_id": first.pk})
        client.post(url, {"paid_on": "2026-02-09", "amount": "500.00", "note": "Parte 1"})
        first.refresh_from_db()
        assert first.settled_at is None
        client.post(url, {"paid_on": "2026-02-10", "amount": "510.00", "note": "Parte 2"})
        first.refresh_from_db()
        assert first.settled_at is not None
        assert first.transactions.count() == 2

    def test_paid_obligation_shows_increase_over_base(self, client):
        plan, first = _plan()
        first.base_amount = Decimal("6800.00")
        first.adjusted_amount = Decimal("7009.20")
        first.settled_at = timezone.now()
        first.save()
        PaymentTransaction.objects.create(
            obligation=first,
            paid_on=datetime.date(2026, 2, 10),
            amount=Decimal("7009.20"),
        )
        response = client.get(reverse("rates:payments_plan", kwargs={"plan_id": plan.pk}))
        row = next(item for item in response.context["rows"] if item["obligation"] == first)
        assert row["paid_vs_base_percent"] == Decimal("3.08")
        assert "▲" in response.content.decode()
        assert "vs. base" not in response.content.decode()

    def test_void_keeps_record_and_reopens_obligation(self, client):
        plan, first = _plan()
        first.adjusted_amount = Decimal("1000.00")
        first.settled_at = timezone.now()
        first.save()
        item = PaymentTransaction.objects.create(
            obligation=first, paid_on=datetime.date(2026, 2, 10), amount=Decimal("1000")
        )
        response = client.post(
            reverse("rates:payment_void", kwargs={"plan_id": plan.pk, "transaction_id": item.pk}),
            {"void_reason": "Duplicado"},
        )
        item.refresh_from_db()
        first.refresh_from_db()
        assert response.status_code == 302
        assert item.voided_at is not None
        assert item.void_reason == "Duplicado"
        assert first.settled_at is None

    def test_obligation_with_payment_can_be_edited_manually_without_recalculation(self, client):
        plan, first = _plan()
        first.adjusted_amount = Decimal("1010.00")
        first.save(update_fields=["adjusted_amount"])
        PaymentTransaction.objects.create(
            obligation=first, paid_on=datetime.date(2026, 2, 1), amount=Decimal("50")
        )
        response = client.post(
            reverse(
                "rates:obligation_update",
                kwargs={"plan_id": plan.pk, "obligation_id": first.pk},
            ),
            {
                "due_date": "2026-03-01",
                "base_amount": "900.00",
                "applies_cub": "on",
                "final_amount_override": "995.00",
            },
        )
        first.refresh_from_db()
        assert response.status_code == 302
        assert first.due_date == datetime.date(2026, 3, 1)
        assert first.base_amount == Decimal("900.00")
        assert first.adjusted_amount == Decimal("1010.00")
        assert first.final_amount_override == Decimal("995.00")

    def test_assisted_preview_never_writes(self, client):
        plan, _ = _plan()
        detected = type(
            "Preview",
            (),
            {
                "applicable_month": datetime.date(2026, 2, 1),
                "reference_month": datetime.date(2026, 1, 1),
                "value": Decimal("3030.00"),
                "monthly_variation": Decimal("1.00"),
                "source_url": "https://example.com/cub",
            },
        )()
        before = CubIndexValue.objects.count()
        with patch("rates.payment_views.fetch_cub_history", return_value=[detected]):
            response = client.get(
                reverse("rates:cub_preview", kwargs={"plan_id": plan.pk}),
                HTTP_HX_REQUEST="true",
            )
        assert response.status_code == 200
        body = response.content.decode()
        assert "Confirmar" in body
        assert 'value="3030.00"' in body
        assert 'value="3030.000000"' not in body
        assert CubIndexValue.objects.count() == before

    def test_assisted_preview_compares_saved_and_proposed_values(self, client):
        plan, _ = _plan()
        current = _cub(datetime.date(2026, 2, 1), "3000.00")
        current.monthly_variation = Decimal("0.50")
        current.save(update_fields=["monthly_variation"])
        detected = SimpleNamespace(
            applicable_month=datetime.date(2026, 2, 1),
            reference_month=datetime.date(2026, 1, 1),
            value=Decimal("3030.00"),
            monthly_variation=Decimal("1.00"),
            source_url="https://example.com/cub",
        )

        with patch("rates.payment_views.fetch_cub_history", return_value=[detected]):
            response = client.get(reverse("rates:cub_preview", kwargs={"plan_id": plan.pk}))

        preview = response.context["previews"][0]
        body = response.content.decode()
        assert preview["current"] == current
        assert preview["delta"] == Decimal("30.00")
        assert preview["delta_percent"] == Decimal("1.00")
        assert "Guardado" in body
        assert "Propuesto" in body
        assert "Diferencia:" in body
        assert "Confirmar seleccionados" in body
        assert "Descartar revisión" in body

    def test_batch_confirmation_saves_multiple_selected_months(self, client):
        plan, first = _plan()
        second = PaymentObligation.objects.get(series__plan=plan, sequence=2)

        response = client.post(
            reverse("rates:cub_confirm_batch", kwargs={"plan_id": plan.pk}),
            {
                "selected_month": ["2026-02", "2026-03"],
                "value_2026-02": "3030.00",
                "variation_2026-02": "1.00",
                "source_2026-02": "https://example.com/cub",
                "value_2026-03": "3060.00",
                "variation_2026-03": "0.99",
                "source_2026-03": "https://example.com/cub",
            },
            HTTP_HX_REQUEST="true",
        )

        first.refresh_from_db()
        second.refresh_from_db()
        february = CubIndexValue.objects.get(applicable_month=datetime.date(2026, 2, 1))
        march = CubIndexValue.objects.get(applicable_month=datetime.date(2026, 3, 1))
        assert response.status_code == 200
        assert february.value == Decimal("3030.00")
        assert march.value == Decimal("3060.00")
        assert first.adjusted_amount == Decimal("1010.00")
        assert second.adjusted_amount == Decimal("1020.00")

    def test_batch_confirmation_leaves_unselected_proposals_unchanged(self, client):
        plan, _ = _plan()
        february = _cub(datetime.date(2026, 2, 1), "3000.00")

        response = client.post(
            reverse("rates:cub_confirm_batch", kwargs={"plan_id": plan.pk}),
            {
                "selected_month": ["2026-03"],
                "value_2026-02": "3030.00",
                "source_2026-02": "https://example.com/cub",
                "value_2026-03": "3060.00",
                "source_2026-03": "https://example.com/cub",
            },
            HTTP_HX_REQUEST="true",
        )

        february.refresh_from_db()
        march = CubIndexValue.objects.get(applicable_month=datetime.date(2026, 3, 1))
        assert response.status_code == 200
        assert february.value == Decimal("3000.00")
        assert march.value == Decimal("3060.00")

    def test_batch_confirmation_requires_a_selection(self, client):
        plan, _ = _plan()
        before = CubIndexValue.objects.count()

        response = client.post(
            reverse("rates:cub_confirm_batch", kwargs={"plan_id": plan.pk}),
            {},
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 200
        assert "Selecciona al menos un valor" in response.content.decode()
        assert CubIndexValue.objects.count() == before

    def test_assisted_confirmation_accepts_rendered_decimal_values(self, client):
        plan, first = _plan()
        response = client.post(
            reverse("rates:cub_confirm", kwargs={"plan_id": plan.pk}),
            {
                "applicable_month": "2026-02",
                "value": "3121.62",
                "monthly_variation": "0.8200",
                "source_url": "https://example.com/cub",
            },
            HTTP_HX_REQUEST="true",
        )
        first.refresh_from_db()
        assert response.status_code == 200
        assert CubIndexValue.objects.get(
            series=plan.cub_series, applicable_month=datetime.date(2026, 2, 1)
        ).value == Decimal("3121.62")
        assert first.adjusted_amount == Decimal("1040.54")

    def test_assisted_preview_handles_failure(self, client):
        plan, _ = _plan()
        with patch(
            "rates.payment_views.fetch_cub_history", side_effect=CubFetchError("fuente caída")
        ):
            response = client.get(reverse("rates:cub_preview", kwargs={"plan_id": plan.pk}))
        assert response.status_code == 200
        assert "fuente caída" in response.content.decode()


@pytest.mark.django_db
class TestPaymentPlanEdit:
    def _payload(self, **overrides):
        payload = {
            "name": "Apartamento actualizado",
            "contract_date": "2026-01-15",
            "base_cub_month": "2026-01",
            "base_cub_value": "3100.00",
            "monthly_first_due_date": "2026-04-15",
            "monthly_count": "3",
            "monthly_amount": "1200.00",
            "monthly_applies_cub": "on",
        }
        payload.update(overrides)
        return payload

    def test_get_preloads_current_plan_and_explains_protected_rows(self, client):
        plan, first = _plan()
        PaymentTransaction.objects.create(
            obligation=first,
            paid_on=datetime.date(2026, 2, 1),
            amount=Decimal("1000"),
        )
        response = client.get(reverse("rates:payment_plan_edit", kwargs={"plan_id": plan.pk}))
        body = response.content.decode()
        assert response.status_code == 200
        assert "Editar plan de compra" in body
        assert "1 obligación protegida" in body
        assert 'value="Apartamento 301"' in body
        assert 'value="2026-01"' in body

    def test_save_rebuilds_only_unpaid_obligations(self, client):
        plan, paid = _plan()
        paid.adjusted_amount = Decimal("1010.00")
        paid.save(update_fields=["adjusted_amount"])
        PaymentTransaction.objects.create(
            obligation=paid,
            paid_on=datetime.date(2026, 2, 1),
            amount=Decimal("1010"),
        )

        response = client.post(
            reverse("rates:payment_plan_edit", kwargs={"plan_id": plan.pk}),
            self._payload(),
        )

        plan.refresh_from_db()
        paid.refresh_from_db()
        obligations = list(PaymentObligation.objects.filter(series__plan=plan).order_by("sequence"))
        assert response.status_code == 302
        assert plan.name == "Apartamento actualizado"
        assert plan.base_cub_value == Decimal("3100.00")
        assert len(obligations) == 3
        assert paid.due_date == datetime.date(2026, 2, 10)
        assert paid.base_amount == Decimal("1000.00")
        assert paid.adjusted_amount == Decimal("1010.00")
        assert paid.calculation_base_cub_value == Decimal("3000.00")
        assert obligations[1].due_date == datetime.date(2026, 5, 15)
        assert obligations[1].base_amount == Decimal("1200.00")
        assert obligations[1].adjusted_amount is None
        assert obligations[2].due_date == datetime.date(2026, 6, 15)

    def test_adds_and_reconfigures_three_down_payment_installments(self, client):
        plan, _ = _plan()
        payload = self._payload(
            down_payment_enabled="on",
            down_payment_first_due_date="2025-10-10",
            down_payment_count="3",
            down_payment_interval_months="1",
            down_payment_amount="12000.00",
        )
        response = client.post(
            reverse("rates:payment_plan_edit", kwargs={"plan_id": plan.pk}), payload
        )
        entrance = plan.payment_series.get(kind=PaymentSeries.Kind.DOWN_PAYMENT)
        assert response.status_code == 302
        assert entrance.occurrence_count == 3
        assert list(entrance.obligations.values_list("base_amount", flat=True)) == [
            Decimal("12000.00"),
            Decimal("12000.00"),
            Decimal("12000.00"),
        ]

        paid = entrance.obligations.get(sequence=1)
        PaymentTransaction.objects.create(
            obligation=paid, paid_on=datetime.date(2025, 10, 10), amount=Decimal("12000.00")
        )
        payload.update(down_payment_first_due_date="2025-11-20", down_payment_amount="13000.00")
        client.post(reverse("rates:payment_plan_edit", kwargs={"plan_id": plan.pk}), payload)
        paid.refresh_from_db()
        second = entrance.obligations.get(sequence=2)
        assert paid.due_date == datetime.date(2025, 10, 10)
        assert paid.base_amount == Decimal("12000.00")
        assert second.due_date == datetime.date(2025, 12, 20)
        assert second.base_amount == Decimal("13000.00")

    def test_edit_preloads_all_special_payment_series(self, client):
        plan, _ = _plan()
        payload = self._payload(
            down_payment_enabled="on",
            down_payment_first_due_date="2025-10-10",
            down_payment_count="3",
            down_payment_interval_months="1",
            down_payment_amount="12000.00",
            reinforcement_enabled="on",
            reinforcement_first_due_date="2026-12-15",
            reinforcement_count="2",
            reinforcement_amount="5000.00",
            keys_enabled="on",
            keys_due_date="2028-06-30",
            keys_amount="20000.00",
        )
        save_response = client.post(
            reverse("rates:payment_plan_edit", kwargs={"plan_id": plan.pk}), payload
        )
        response = client.get(reverse("rates:payment_plan_edit", kwargs={"plan_id": plan.pk}))
        body = response.content.decode()
        assert save_response.status_code == 302
        assert 'name="down_payment_enabled"' in body
        assert 'value="2025-10-10"' in body
        assert 'name="down_payment_count" value="3"' in body
        assert 'value="2026-12-15"' in body
        assert 'name="reinforcement_count" value="2"' in body
        assert 'value="2028-06-30"' in body
        assert 'name="keys_amount" value="20000.00"' in body

    def test_cannot_reduce_count_below_a_paid_sequence(self, client):
        plan, _ = _plan()
        second = PaymentObligation.objects.get(series__plan=plan, sequence=2)
        PaymentTransaction.objects.create(
            obligation=second,
            paid_on=datetime.date(2026, 3, 1),
            amount=Decimal("1000"),
        )
        response = client.post(
            reverse("rates:payment_plan_edit", kwargs={"plan_id": plan.pk}),
            self._payload(monthly_count="1"),
        )
        assert response.status_code == 400
        assert "la cantidad no puede bajar de 2" in response.content.decode()
        assert PaymentObligation.objects.filter(series__plan=plan).count() == 2
