from django.conf import settings
from django.db import models
from django.utils import timezone


class Part(models.Model):
    code = models.CharField(max_length=64, primary_key=True)
    designation = models.CharField(max_length=255, blank=True, default="")
    criticite = models.CharField(max_length=16, default="normal")
    stock_actuel = models.FloatField(default=0)
    stock_securite = models.FloatField(default=0)
    moyenne_m3 = models.FloatField(default=0)
    prevision_m1 = models.FloatField(default=0)
    ecart_pourcent = models.FloatField(default=0)
    prix_unitaire = models.FloatField(default=0)
    fournisseur = models.CharField(max_length=255, blank=True, default="")
    delai = models.FloatField(default=0)  # jours
    n_ac_2025 = models.FloatField(default=0)
    approuve = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Part"
        verbose_name_plural = "Parts"

    def to_dict(self):
        return {
            "code": self.code,
            "designation": self.designation,
            "criticite": self.criticite,
            "stockActuel": self.stock_actuel,
            "stockSecurite": self.stock_securite,
            "moyenneM3": self.moyenne_m3,
            "previsionM1": self.prevision_m1,
            "ecartPourcent": self.ecart_pourcent,
            "prixUnitaire": self.prix_unitaire,
            "fournisseur": self.fournisseur,
            "delai": self.delai,
            "n_ac_2025": self.n_ac_2025,
        }


class Consumption(models.Model):
    part = models.ForeignKey(Part, on_delete=models.CASCADE)
    date = models.DateField()
    valeur = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Consumption"
        verbose_name_plural = "Consumptions"
        unique_together = ("part", "date")


class BudgetConfig(models.Model):
    budget_cap = models.FloatField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Budget configuration"
        verbose_name_plural = "Budget configuration"


class Selection(models.Model):
    part = models.OneToOneField(Part, on_delete=models.CASCADE)
    selected = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Selection"
        verbose_name_plural = "Selections"


class ActivityLog(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    utilisateur = models.CharField(max_length=128, default="Système")
    role = models.CharField(max_length=64, default="Auto")
    action = models.CharField(max_length=255)
    module = models.CharField(max_length=64)
    details = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "Activity Log"
        verbose_name_plural = "Activity Logs"


class ParametersConfig(models.Model):
    """
    Stores application-wide tuning parameters exposed in the UI.
    Singleton row (id=1) used for simplicity.
    """

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    rupture_threshold = models.FloatField(default=10)  # percentage
    long_lead_days = models.PositiveIntegerField(default=60)
    budget_cap = models.FloatField(null=True, blank=True)
    auto_select_critical = models.BooleanField(default=True)
    active_model = models.CharField(max_length=64, default="hist-gradient-boosting")
    refresh_frequency = models.CharField(
        max_length=32,
        default="hebdomadaire",
        choices=(
            ("journalier", "journalier"),
            ("hebdomadaire", "hebdomadaire"),
            ("mensuel", "mensuel"),
        ),
    )
    notify_rupture = models.BooleanField(default=True)
    notify_budget = models.BooleanField(default=True)
    notify_digest = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.CharField(max_length=128, default="Système")
    updated_role = models.CharField(max_length=64, default="Auto")

    class Meta:
        verbose_name = "Parameters configuration"
        verbose_name_plural = "Parameters configuration"


class UserProfile(models.Model):
    ROLE_MANAGER = "manager"
    ROLE_APPROVISIONNEMENT = "approvisionnement"
    ROLE_LOGISTIQUE = "logistique"
    ROLE_SUPERADMIN = "superadmin"

    ROLE_CHOICES = (
        (ROLE_MANAGER, "Manager"),
        (ROLE_APPROVISIONNEMENT, "Approvisionnement"),
        (ROLE_LOGISTIQUE, "Logistique"),
        (ROLE_SUPERADMIN, "Super administrateur"),
    )

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=32, choices=ROLE_CHOICES, default=ROLE_MANAGER)
    nom = models.CharField(max_length=128, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "User profile"
        verbose_name_plural = "User profiles"

    def to_dict(self):
        display_name = self.nom or getattr(self.user, "get_full_name", lambda: "")() or getattr(self.user, "username", "")
        return {
            "id": str(self.user_id),
            "nom": display_name,
            "email": getattr(self.user, "email", "") or "",
            "role": self.role,
        }


class PasswordResetCode(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="password_reset_codes")
    code_hash = models.CharField(max_length=64)  # sha256 hex digest
    # Stockage temporaire du code en clair pour permettre au superadmin de le communiquer
    # à l'utilisateur (interface d'administration). Il est vidé dès utilisation.
    code_plain = models.CharField(max_length=16, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Password reset code"
        verbose_name_plural = "Password reset codes"
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["expires_at"]),
            models.Index(fields=["used_at"]),
        ]

    def is_valid(self) -> bool:
        return self.used_at is None and self.expires_at > timezone.now()
