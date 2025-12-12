from django.contrib import admin

from .models import (
    ActivityLog,
    BudgetConfig,
    Consumption,
    ParametersConfig,
    Part,
    Selection,
    UserProfile,
)


@admin.register(Part)
class PartAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "designation",
        "criticite",
        "stock_actuel",
        "prevision_m1",
        "n_ac_2025",
    )
    search_fields = ("code", "designation", "fournisseur")
    list_filter = ("criticite",)
    ordering = ("code",)


@admin.register(Consumption)
class ConsumptionAdmin(admin.ModelAdmin):
    list_display = ("part", "date", "valeur", "created_at")
    search_fields = ("part__code",)
    list_filter = ("date",)
    ordering = ("-date",)


@admin.register(BudgetConfig)
class BudgetConfigAdmin(admin.ModelAdmin):
    list_display = ("budget_cap", "updated_at")
    ordering = ("-updated_at",)


@admin.register(Selection)
class SelectionAdmin(admin.ModelAdmin):
    list_display = ("part", "selected")
    search_fields = ("part__code",)
    list_filter = ("selected",)


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "utilisateur", "role", "module", "action")
    search_fields = ("utilisateur", "role", "module", "action")
    list_filter = ("module", "role")
    ordering = ("-created_at",)


@admin.register(ParametersConfig)
class ParametersConfigAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "rupture_threshold",
        "long_lead_days",
        "budget_cap",
        "active_model",
        "refresh_frequency",
        "notify_rupture",
        "notify_budget",
        "notify_digest",
        "updated_at",
        "updated_by",
    )
    readonly_fields = ("updated_at",)
    list_filter = ("refresh_frequency", "notify_rupture", "notify_budget", "notify_digest")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "nom", "role", "created_at")
    search_fields = ("user__username", "user__email", "nom")
    list_filter = ("role",)
    ordering = ("-created_at",)


# Cosmetic admin titles
admin.site.site_header = "OCP Prévision - Admin"
admin.site.site_title = "OCP Prévision"
admin.site.index_title = "Administration backend"
