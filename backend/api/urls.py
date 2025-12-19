from django.urls import path
from . import views

urlpatterns = [
    path("auth/login/", views.auth_login, name="auth_login"),
    path("auth/me/", views.auth_me, name="auth_me"),
    path("auth/logout/", views.auth_logout, name="auth_logout"),
    path("auth/signup/", views.auth_signup, name="auth_signup"),
    path("auth/forgot-password/", views.auth_forgot_password, name="auth_forgot_password"),
    path("auth/reset-password/", views.auth_reset_password, name="auth_reset_password"),
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
    # Admin JSON API (manager-only, used by React admin)
    path("admin/parts/", views.admin_parts, name="admin_parts"),
    path("admin/parts/<str:code>/", views.admin_part_detail, name="admin_part_detail"),
    path("admin/consumptions/", views.admin_consumptions, name="admin_consumptions"),
    path("admin/consumptions/<int:pk>/", views.admin_consumption_detail, name="admin_consumption_detail"),
    path("admin/users/", views.admin_users, name="admin_users"),
    path("admin/users/<int:pk>/", views.admin_user_detail, name="admin_user_detail"),
    path("admin/users/<int:pk>/password-reset-code/", views.admin_user_password_reset_code, name="admin_user_password_reset_code"),
]
