from django.urls import path

from rates import views

app_name = "rates"

urlpatterns = [
    # Root → overview
    path("", views.overview, name="root"),
    # Auth
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    # Overview
    path("overview/", views.overview, name="overview"),
    # Per-pair dashboard and partials (pair_code slug, e.g. "usd-brl")
    path("<str:pair_code>/", views.dashboard, name="dashboard"),
    path("<str:pair_code>/stats/", views.stats_partial, name="stats_partial"),
    path("<str:pair_code>/refresh/", views.refresh_data, name="refresh_data"),
    path("<str:pair_code>/config/", views.update_config, name="update_config"),
    path("<str:pair_code>/purchases/add/", views.add_purchase, name="add_purchase"),
    path(
        "<str:pair_code>/purchases/<int:pk>/delete/", views.delete_purchase, name="delete_purchase"
    ),
]
