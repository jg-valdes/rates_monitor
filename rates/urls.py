from django.urls import path

from rates import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("partials/stats/", views.stats_partial, name="stats_partial"),
    path("refresh/", views.refresh_data, name="refresh_data"),
    path("config/", views.update_config, name="update_config"),
]
