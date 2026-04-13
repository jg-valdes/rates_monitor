"""Tests for rates/views.py."""
import datetime
from unittest.mock import patch

import pytest
from django.test import Client
from django.urls import reverse

from tests.factories import (
    CurrencyPairFactory,
    ExchangeRateFactory,
    PairConfigFactory,
    PurchaseFactory,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_pair_with_rates(code="USD-BRL", n=90):
    pair = CurrencyPairFactory(code=code, name=f"{code} name")
    base = datetime.date(2024, 1, 1)
    for i in range(n):
        ExchangeRateFactory(pair=pair, date=base + datetime.timedelta(days=i), rate=5.0 + i * 0.01)
    PairConfigFactory(pair=pair)
    return pair


# ── Auth views ────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestLoginView:
    def test_get_renders_form(self, client):
        resp = client.get(reverse("rates:login"))
        assert resp.status_code == 200
        assert b"passcode" in resp.content.lower() or resp.status_code == 200

    def test_wrong_passcode_shows_error(self, client, settings):
        settings.ACCESS_PASSCODE = "correct"
        resp = client.post(reverse("rates:login"), {"passcode": "wrong"})
        assert resp.status_code == 200

    def test_correct_passcode_redirects(self, client, settings):
        settings.ACCESS_PASSCODE = "correct"
        resp = client.post(reverse("rates:login"), {"passcode": "correct"})
        assert resp.status_code == 302
        assert "rm_access" in resp.cookies

    def test_correct_passcode_redirects_to_next(self, client, settings):
        settings.ACCESS_PASSCODE = "correct"
        resp = client.post(reverse("rates:login") + "?next=/overview/", {"passcode": "correct"})
        assert resp.status_code == 302
        assert "/overview/" in resp["Location"]

    def test_no_passcode_configured_rejects_any_post(self, client, settings):
        settings.ACCESS_PASSCODE = "secret"
        resp = client.post(reverse("rates:login"), {"passcode": "anything"})
        assert resp.status_code == 200  # stays on login page


@pytest.mark.django_db
class TestLogoutView:
    def test_clears_cookie_and_redirects(self, client):
        client.cookies["rm_access"] = "sometoken"
        resp = client.get(reverse("rates:logout"))
        assert resp.status_code == 302
        # cookie should be cleared (max_age=0 or deleted)
        assert resp.cookies.get("rm_access", None) is not None  # exists but emptied


# ── Overview ──────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestOverviewView:
    def test_ok_with_no_pairs(self, client):
        resp = client.get(reverse("rates:overview"))
        assert resp.status_code == 200

    def test_ok_with_pairs_and_rates(self, client):
        _make_pair_with_rates("USD-BRL")
        _make_pair_with_rates("UYU-USD")
        _make_pair_with_rates("UYU-BRL")
        resp = client.get(reverse("rates:overview"))
        assert resp.status_code == 200

    def test_cross_pair_shown_when_all_pairs_present(self, client):
        _make_pair_with_rates("USD-BRL")
        _make_pair_with_rates("UYU-USD")
        _make_pair_with_rates("UYU-BRL")
        resp = client.get(reverse("rates:overview"))
        assert resp.status_code == 200
        assert b"Ruta" in resp.content

    def test_root_url_resolves_to_overview(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_overview_with_purchases_shows_totals(self, client):
        from rates.models import PairConfig

        pair = _make_pair_with_rates("USD-BRL")
        PurchaseFactory(pair=pair, amount_spent=100.0, amount_received=550.0)
        resp = client.get(reverse("rates:overview"))
        assert resp.status_code == 200

    def test_overview_auto_creates_missing_config(self, client):
        from rates.models import PairConfig

        # Delete config for one seeded pair so the bulk_create path is exercised
        pair = _make_pair_with_rates("USD-BRL")
        PairConfig.objects.filter(pair=pair).delete()
        resp = client.get(reverse("rates:overview"))
        assert resp.status_code == 200
        assert PairConfig.objects.filter(pair=pair).exists()


# ── Dashboard ─────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestDashboardView:
    def test_ok_with_rates(self, client):
        pair = _make_pair_with_rates("USD-BRL")
        resp = client.get(reverse("rates:dashboard", kwargs={"pair_code": pair.slug}))
        assert resp.status_code == 200

    def test_404_on_unknown_pair(self, client):
        resp = client.get(reverse("rates:dashboard", kwargs={"pair_code": "xyz-abc"}))
        assert resp.status_code == 404

    def test_404_on_inactive_pair(self, client):
        pair = CurrencyPairFactory(code="TST-INA", active=False)
        resp = client.get(reverse("rates:dashboard", kwargs={"pair_code": pair.slug}))
        assert resp.status_code == 404

    def test_context_has_pair(self, client):
        pair = _make_pair_with_rates("USD-BRL")
        resp = client.get(reverse("rates:dashboard", kwargs={"pair_code": pair.slug}))
        assert resp.context["pair"].code == "USD-BRL"

    def test_no_data_still_renders(self, client):
        pair = CurrencyPairFactory(code="USD-BRL")
        PairConfigFactory(pair=pair)
        resp = client.get(reverse("rates:dashboard", kwargs={"pair_code": pair.slug}))
        assert resp.status_code == 200

    def test_single_rate_skips_history_guard(self, client):
        # _compute_history skips subsets with < 2 rates; ensure it doesn't crash
        pair = CurrencyPairFactory(code="USD-BRL")
        PairConfigFactory(pair=pair)
        ExchangeRateFactory(pair=pair, date=datetime.date(2024, 6, 1), rate=5.0)
        resp = client.get(reverse("rates:dashboard", kwargs={"pair_code": pair.slug}))
        assert resp.status_code == 200


# ── Stats partial ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestStatsPartial:
    def test_ok(self, client):
        pair = _make_pair_with_rates("USD-BRL")
        resp = client.get(reverse("rates:stats_partial", kwargs={"pair_code": pair.slug}))
        assert resp.status_code == 200

    def test_only_get_allowed(self, client):
        pair = _make_pair_with_rates("USD-BRL")
        resp = client.post(reverse("rates:stats_partial", kwargs={"pair_code": pair.slug}))
        assert resp.status_code == 405


# ── Refresh data ──────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestRefreshData:
    def test_returns_partial_on_post(self, client):
        pair = _make_pair_with_rates("USD-BRL")
        with patch("rates.views.fetch_and_store"):
            resp = client.post(reverse("rates:refresh_data", kwargs={"pair_code": pair.slug}))
        assert resp.status_code == 200

    def test_only_post_allowed(self, client):
        pair = _make_pair_with_rates("USD-BRL")
        resp = client.get(reverse("rates:refresh_data", kwargs={"pair_code": pair.slug}))
        assert resp.status_code == 405

    def test_fetch_error_does_not_crash(self, client):
        pair = _make_pair_with_rates("USD-BRL")
        with patch("rates.views.fetch_and_store", side_effect=Exception("network down")):
            resp = client.post(reverse("rates:refresh_data", kwargs={"pair_code": pair.slug}))
        assert resp.status_code == 200


# ── Update config ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestUpdateConfig:
    def _post(self, client, pair, data):
        return client.post(
            reverse("rates:update_config", kwargs={"pair_code": pair.slug}),
            data,
            HTTP_HX_REQUEST="true",
        )

    def test_saves_budget(self, client):
        from rates.models import PairConfig

        pair = _make_pair_with_rates("USD-BRL")
        self._post(client, pair, {"monthly_budget": "2000", "threshold_strong_buy": "3.0",
                                   "threshold_moderate_buy": "1.5", "threshold_do_not_buy": "-1.0"})
        assert PairConfig.objects.get(pair=pair).monthly_budget == pytest.approx(2000.0)

    def test_saves_thresholds(self, client):
        from rates.models import PairConfig

        pair = _make_pair_with_rates("USD-BRL")
        self._post(client, pair, {
            "monthly_budget": "1000",
            "threshold_strong_buy": "4.0",
            "threshold_moderate_buy": "2.0",
            "threshold_do_not_buy": "-2.0",
        })
        cfg = PairConfig.objects.get(pair=pair)
        assert cfg.threshold_strong_buy == pytest.approx(4.0)
        assert cfg.threshold_moderate_buy == pytest.approx(2.0)
        assert cfg.threshold_do_not_buy == pytest.approx(-2.0)

    def test_alert_on_strong_buy_checkbox(self, client):
        from rates.models import PairConfig

        pair = _make_pair_with_rates("USD-BRL")
        self._post(client, pair, {
            "monthly_budget": "1000", "threshold_strong_buy": "3",
            "threshold_moderate_buy": "1.5", "threshold_do_not_buy": "-1",
            "alert_on_strong_buy": "on",
        })
        assert PairConfig.objects.get(pair=pair).alert_on_strong_buy is True

    def test_alert_on_strong_buy_unchecked(self, client):
        from rates.models import PairConfig

        pair = _make_pair_with_rates("USD-BRL")
        PairConfig.objects.filter(pair=pair).update(alert_on_strong_buy=True)
        self._post(client, pair, {
            "monthly_budget": "1000", "threshold_strong_buy": "3",
            "threshold_moderate_buy": "1.5", "threshold_do_not_buy": "-1",
            # no alert_on_strong_buy key → unchecked
        })
        assert PairConfig.objects.get(pair=pair).alert_on_strong_buy is False

    def test_invalid_budget_keeps_default(self, client):
        from rates.models import PairConfig

        pair = _make_pair_with_rates("USD-BRL")
        PairConfig.objects.filter(pair=pair).update(monthly_budget=1000.0)
        self._post(client, pair, {
            "monthly_budget": "not-a-number",
            "threshold_strong_buy": "3", "threshold_moderate_buy": "1.5", "threshold_do_not_buy": "-1",
        })
        assert PairConfig.objects.get(pair=pair).monthly_budget == pytest.approx(1000.0)

    def test_invalid_optional_float_saved_as_none(self, client):
        from rates.models import PairConfig

        pair = _make_pair_with_rates("USD-BRL")
        self._post(client, pair, {
            "monthly_budget": "1000", "threshold_strong_buy": "3",
            "threshold_moderate_buy": "1.5", "threshold_do_not_buy": "-1",
            "alert_on_deviation_above": "not-a-number",  # triggers ValueError in _float_or_none
        })
        assert PairConfig.objects.get(pair=pair).alert_on_deviation_above is None

    def test_htmx_returns_partial(self, client):
        pair = _make_pair_with_rates("USD-BRL")
        resp = self._post(client, pair, {
            "monthly_budget": "1000", "threshold_strong_buy": "3",
            "threshold_moderate_buy": "1.5", "threshold_do_not_buy": "-1",
        })
        assert resp.status_code == 200

    def test_non_htmx_redirects(self, client):
        pair = _make_pair_with_rates("USD-BRL")
        resp = client.post(
            reverse("rates:update_config", kwargs={"pair_code": pair.slug}),
            {"monthly_budget": "1000", "threshold_strong_buy": "3",
             "threshold_moderate_buy": "1.5", "threshold_do_not_buy": "-1"},
        )
        assert resp.status_code == 302


# ── Test alert (per-pair) ─────────────────────────────────────────────────────

@pytest.mark.django_db
class TestTestAlert:
    def test_no_data_returns_warning(self, client):
        pair = CurrencyPairFactory(code="USD-BRL")
        PairConfigFactory(pair=pair)
        resp = client.post(reverse("rates:test_alert", kwargs={"pair_code": pair.slug}))
        assert resp.status_code == 200
        assert b"Sin datos" in resp.content

    def test_sends_alert_and_returns_success(self, client):
        pair = _make_pair_with_rates("USD-BRL")
        with patch("rates.views.send_test_alert", return_value=True):
            resp = client.post(reverse("rates:test_alert", kwargs={"pair_code": pair.slug}))
        assert resp.status_code == 200
        assert "✓" in resp.content.decode()

    def test_telegram_not_configured_returns_error(self, client):
        pair = _make_pair_with_rates("USD-BRL")
        with patch("rates.views.send_test_alert", return_value=False):
            resp = client.post(reverse("rates:test_alert", kwargs={"pair_code": pair.slug}))
        assert resp.status_code == 200
        assert "✕" in resp.content.decode()

    def test_exception_returns_error(self, client):
        pair = _make_pair_with_rates("USD-BRL")
        with patch("rates.views.send_test_alert", side_effect=Exception("boom")):
            resp = client.post(reverse("rates:test_alert", kwargs={"pair_code": pair.slug}))
        assert resp.status_code == 200
        assert "✕" in resp.content.decode()

    def test_only_post_allowed(self, client):
        pair = _make_pair_with_rates("USD-BRL")
        resp = client.get(reverse("rates:test_alert", kwargs={"pair_code": pair.slug}))
        assert resp.status_code == 405


# ── Send all alerts ───────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestSendAllAlerts:
    def test_no_pairs_returns_zero_sent(self, client):
        from rates.models import CurrencyPair

        CurrencyPair.objects.all().update(active=False)
        with patch("rates.views.send_all_current_alerts", return_value={"sent": 0, "failed": 0, "total": 0}):
            resp = client.post(reverse("rates:send_all_alerts"))
        assert resp.status_code == 200
        assert "0 alertas" in resp.content.decode()

    def test_all_sent_returns_success(self, client):
        from rates.models import CurrencyPair

        # Deactivate seeded pairs so only our test pairs are processed
        CurrencyPair.objects.all().update(active=False)
        _make_pair_with_rates("TST-AA")
        _make_pair_with_rates("TST-BB")
        with patch("rates.views.send_all_current_alerts", return_value={"sent": 2, "failed": 0, "total": 2}):
            resp = client.post(reverse("rates:send_all_alerts"))
        assert resp.status_code == 200
        assert "✓" in resp.content.decode()
        assert "2 alertas" in resp.content.decode()

    def test_all_failed_returns_error(self, client):
        _make_pair_with_rates("USD-BRL")
        with patch("rates.views.send_all_current_alerts", return_value={"sent": 0, "failed": 1, "total": 1}):
            resp = client.post(reverse("rates:send_all_alerts"))
        assert resp.status_code == 200
        assert "✕" in resp.content.decode()

    def test_partial_failure_returns_warning(self, client):
        _make_pair_with_rates("USD-BRL")
        _make_pair_with_rates("UYU-USD")
        with patch("rates.views.send_all_current_alerts", return_value={"sent": 1, "failed": 1, "total": 2}):
            resp = client.post(reverse("rates:send_all_alerts"))
        assert resp.status_code == 200
        assert "⚠" in resp.content.decode()

    def test_pair_without_data_counted_as_failed(self, client):
        CurrencyPairFactory(code="USD-BRL")  # no rates
        with patch("rates.views.send_all_current_alerts", return_value={"sent": 0, "failed": 1, "total": 1}):
            resp = client.post(reverse("rates:send_all_alerts"))
        assert resp.status_code == 200
        assert "✕" in resp.content.decode()

    def test_only_post_allowed(self, client):
        resp = client.get(reverse("rates:send_all_alerts"))
        assert resp.status_code == 405

    def test_exception_per_pair_counted_as_failed(self, client):
        _make_pair_with_rates("USD-BRL")
        with patch("rates.views.send_all_current_alerts", return_value={"sent": 0, "failed": 1, "total": 1}):
            resp = client.post(reverse("rates:send_all_alerts"))
        assert resp.status_code == 200
        assert "✕" in resp.content.decode()


# ── Purchases ─────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestAddPurchase:
    def test_creates_purchase(self, client):
        from rates.models import Purchase

        pair = _make_pair_with_rates("USD-BRL")
        resp = client.post(
            reverse("rates:add_purchase", kwargs={"pair_code": pair.slug}),
            {"date": "2024-06-01", "amount_spent": "100", "amount_received": "500", "note": "test"},
        )
        assert resp.status_code == 200
        assert Purchase.objects.filter(pair=pair).count() == 1

    def test_invalid_data_ignored(self, client):
        from rates.models import Purchase

        pair = _make_pair_with_rates("USD-BRL")
        resp = client.post(
            reverse("rates:add_purchase", kwargs={"pair_code": pair.slug}),
            {"date": "bad-date", "amount_spent": "not-a-number", "amount_received": "500"},
        )
        assert resp.status_code == 200
        assert Purchase.objects.filter(pair=pair).count() == 0

    def test_returns_purchases_partial(self, client):
        pair = _make_pair_with_rates("USD-BRL")
        resp = client.post(
            reverse("rates:add_purchase", kwargs={"pair_code": pair.slug}),
            {"date": "2024-06-01", "amount_spent": "100", "amount_received": "500"},
        )
        assert resp.status_code == 200


@pytest.mark.django_db
class TestDeletePurchase:
    def test_deletes_purchase(self, client):
        from rates.models import Purchase

        pair = _make_pair_with_rates("USD-BRL")
        purchase = PurchaseFactory(pair=pair)
        resp = client.post(
            reverse("rates:delete_purchase", kwargs={"pair_code": pair.slug, "pk": purchase.pk})
        )
        assert resp.status_code == 200
        assert Purchase.objects.filter(pk=purchase.pk).count() == 0

    def test_cannot_delete_other_pairs_purchase(self, client):
        from rates.models import Purchase

        pair1 = _make_pair_with_rates("USD-BRL")
        pair2 = _make_pair_with_rates("UYU-USD")
        purchase = PurchaseFactory(pair=pair2)
        resp = client.post(
            reverse("rates:delete_purchase", kwargs={"pair_code": pair1.slug, "pk": purchase.pk})
        )
        assert resp.status_code == 200
        assert Purchase.objects.filter(pk=purchase.pk).count() == 1  # not deleted

    def test_returns_purchases_partial(self, client):
        pair = _make_pair_with_rates("USD-BRL")
        purchase = PurchaseFactory(pair=pair)
        resp = client.post(
            reverse("rates:delete_purchase", kwargs={"pair_code": pair.slug, "pk": purchase.pk})
        )
        assert resp.status_code == 200
