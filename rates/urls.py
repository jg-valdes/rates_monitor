from django.urls import path

from rates import payment_views, views

app_name = "rates"

urlpatterns = [
    # Root → overview
    path("", views.overview, name="root"),
    # Auth
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    # Overview
    path("overview/", views.overview, name="overview"),
    # Property payments
    path("payments/", payment_views.payments, name="payments"),
    path("payments/new/", payment_views.payment_plan_new, name="payment_plan_new"),
    path("payments/create/", payment_views.payment_plan_create, name="payment_plan_create"),
    path("payments/<int:plan_id>/", payment_views.payments, name="payments_plan"),
    path("payments/<int:plan_id>/edit/", payment_views.payment_plan_edit, name="payment_plan_edit"),
    path("payments/<int:plan_id>/cub/add/", payment_views.cub_add, name="cub_add"),
    path("payments/<int:plan_id>/cub/preview/", payment_views.cub_preview, name="cub_preview"),
    path("payments/<int:plan_id>/cub/confirm/", payment_views.cub_confirm, name="cub_confirm"),
    path(
        "payments/<int:plan_id>/obligations/<int:obligation_id>/pay/",
        payment_views.payment_add,
        name="payment_add",
    ),
    path(
        "payments/<int:plan_id>/obligations/<int:obligation_id>/special-payment/",
        payment_views.special_payment_save,
        name="special_payment_save",
    ),
    path(
        "payments/<int:plan_id>/obligations/<int:obligation_id>/update/",
        payment_views.obligation_update,
        name="obligation_update",
    ),
    path(
        "payments/<int:plan_id>/obligations/<int:obligation_id>/settle/",
        payment_views.obligation_settle,
        name="obligation_settle",
    ),
    path(
        "payments/<int:plan_id>/transactions/<int:transaction_id>/void/",
        payment_views.payment_void,
        name="payment_void",
    ),
    # Global actions
    path("send-alerts/", views.send_all_alerts, name="send_all_alerts"),
    path("oer-usage/", views.oer_usage_panel, name="oer_usage_panel"),
    # Per-pair dashboard and partials (pair_code slug, e.g. "usd-brl")
    path("<str:pair_code>/", views.dashboard, name="dashboard"),
    path("<str:pair_code>/stats/", views.stats_partial, name="stats_partial"),
    path("<str:pair_code>/refresh/", views.refresh_data, name="refresh_data"),
    path("<str:pair_code>/config/", views.update_config, name="update_config"),
    path("<str:pair_code>/purchases/add/", views.add_purchase, name="add_purchase"),
    path(
        "<str:pair_code>/purchases/<int:pk>/delete/", views.delete_purchase, name="delete_purchase"
    ),
    path("<str:pair_code>/test-alert/", views.test_alert, name="test_alert"),
]
