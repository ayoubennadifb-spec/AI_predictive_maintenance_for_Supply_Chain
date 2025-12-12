from django.urls import path
from . import views

urlpatterns = [
    path("auth/login/", views.auth_login, name="auth_login"),
    path("auth/signup/", views.auth_signup, name="auth_signup"),
    path("previsions/", views.previsions, name="previsions"),
    path("purchases/", views.purchases, name="purchases"),
    path("metrics/", views.metrics, name="metrics"),
    path("consommations/", views.consumptions, name="consommations"),
    path("consommations/reset/", views.reset_consumptions, name="reset_consumptions"),
    path("budget/state/", views.budget_state, name="budget_state"),
    path("parameters/", views.parameters, name="parameters"),
    path("approvals/", views.approvals, name="approvals"),
    path("export/previsions.csv", views.export_previsions_csv_view, name="export_previsions_csv"),
    path("export/budget.csv", views.export_budget_csv_view, name="export_budget_csv"),
    path("export/consommations.csv", views.export_consommations_csv_view, name="export_consommations_csv"),
    path("activities/", views.activities, name="activities"),
    path("consommations/import/", views.import_consumptions, name="import_consumptions"),
    path("recompute/previsions/", views.recompute_previsions, name="recompute_previsions"),
]
