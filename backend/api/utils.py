import json
from pathlib import Path
from django.db import transaction
import os
from .models import Part, ActivityLog, ParametersConfig, UserProfile
from . import inference

BASE_DIR = Path(__file__).resolve().parent.parent
_predictions_synced = False


def _compute_nac(n_pm: float, n_ss: float, n_sa: float, delai_jours: float) -> float:
    delai_mois = max(0.0, (delai_jours or 0.0) / 30.0)
    return max(0.0, n_pm + n_ss - n_sa + n_pm * delai_mois)


def _path_predictions() -> Path:
    return BASE_DIR.parent / "webapp" / "UI for forecasting2" / "src" / "assets" / "predictions_2025.json"


def _path_stock_secu() -> Path:
    return BASE_DIR.parent / "webapp" / "UI for forecasting2" / "src" / "assets" / "stock_securite.json"


def load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


@transaction.atomic
def ensure_parts_loaded():
    global _predictions_synced
    if Part.objects.exists():
        # Auto-heal : si la DB a des prévisions incohérentes (ex: prévision_m1 != fichier
        # predictions_2025.json), on resynchronise une seule fois par processus.
        if not _predictions_synced:
            _predictions_synced = True
            try:
                preds = load_json(_path_predictions()) or []
                pred_map = {
                    str(r.get("code")): float(r.get("previsionM1") or 0.0)
                    for r in preds
                    if r.get("code") is not None
                }
                to_update = []
                for part in Part.objects.all():
                    expected = pred_map.get(part.code)
                    if expected is None:
                        continue
                    desired_nac = _compute_nac(
                        n_pm=expected,
                        n_ss=part.stock_securite or 0.0,
                        n_sa=part.stock_actuel or 0.0,
                        delai_jours=part.delai or 0.0,
                    )
                    current_prevision = float(part.prevision_m1 or 0.0)
                    current_nac = float(part.n_ac_2025 or 0.0)
                    if abs(current_prevision - expected) <= 1e-9 and abs(current_nac - desired_nac) <= 1e-6:
                        continue
                    part.prevision_m1 = expected
                    part.n_ac_2025 = desired_nac
                    to_update.append(part)
                if to_update:
                    Part.objects.bulk_update(to_update, ["prevision_m1", "n_ac_2025"])
            except Exception:
                # Ne jamais bloquer l'API si la resynchro échoue.
                pass
        return
    # Try to run inference; fallback to JSON assets
    try:
        preds_df = inference.run_inference()
        # enrich with part2 data for stocks/delais/prix
        part2 = (BASE_DIR.parent / "data" / "processed" / "part2_clean_step2.parquet")
        p2_df = None
        if part2.exists():
            import pandas as pd
            p2_df = pd.read_parquet(part2)
            p2_df = p2_df.set_index("code_piece")
        bulk = []
        for _, row in preds_df.iterrows():
            code = str(row["code_piece"])
            p2 = p2_df.loc[code] if p2_df is not None and code in p2_df.index else None
            stock_securite = float(p2["stock_securite"]) if p2 is not None else 0.0
            stock_actuel = float(p2["stock_actuel"]) if p2 is not None else 0.0
            delai = float(p2["Délai de livr prévi"]) if p2 is not None and "Délai de livr prévi" in p2 else 0.0
            prix_uni = float(p2["prix_uni_final"]) if p2 is not None and "prix_uni_final" in p2 else 0.0
            designation = str(p2["Désignation langue"]) if p2 is not None and "Désignation langue" in p2 else ""
            criticite = str(p2["classif"]) if p2 is not None and "classif" in p2 else "normal"
            moyenne_m3 = float(p2["cons_moy_mensuelle"]) if p2 is not None and "cons_moy_mensuelle" in p2 else float(row["n_pm_2025"])
            prevision_m1 = float(row["n_pm_2025"])
            n_ac_2025 = max(0.0, prevision_m1 + stock_securite - stock_actuel + prevision_m1 * max(0.0, delai / 30.0))
            bulk.append(
                Part(
                    code=code,
                    designation=designation,
                    criticite=criticite,
                    stock_actuel=stock_actuel,
                    stock_securite=stock_securite,
                    moyenne_m3=moyenne_m3,
                    prevision_m1=prevision_m1,
                    prix_unitaire=prix_uni,
                    fournisseur="N/A",
                    delai=delai,
                    n_ac_2025=n_ac_2025,
                )
            )
        Part.objects.bulk_create(bulk, ignore_conflicts=True)
        return
    except Exception:
        pass

    preds = load_json(_path_predictions()) or []
    stock_map = load_json(_path_stock_secu()) or {}
    bulk = []
    for r in preds:
        code = str(r.get("code"))
        bulk.append(
            Part(
                code=code,
                designation=r.get("designation", "") or "",
                criticite=str(r.get("criticite") or "normal"),
                stock_actuel=float(r.get("stockActuel") or 0),
                stock_securite=float(stock_map.get(code, r.get("moyenneM3") or 0)),
                moyenne_m3=float(r.get("moyenneM3") or 0),
                prevision_m1=float(r.get("previsionM1") or 0),
                ecart_pourcent=float(r.get("ecartPourcent") or 0),
                prix_unitaire=float(r.get("prixUnitaire") or 0),
                fournisseur=r.get("fournisseur", "") or "",
                delai=float(r.get("delai") or 0),
                n_ac_2025=float(r.get("n_ac_2025") or 0),
            )
        )
    Part.objects.bulk_create(bulk, ignore_conflicts=True)


def log_activity(action: str, module: str, details: str = "", utilisateur: str = "Système", role: str = "Auto"):
    ActivityLog.objects.create(
        action=action[:255],
        module=module[:64],
        details=details,
        utilisateur=utilisateur,
        role=role,
    )


def check_api_auth(request) -> bool:
    """
    Token check: if API_TOKEN is defined in env, request must include matching X-API-KEY.
    If not defined, auth is bypassed (dev mode).
    """
    token = os.getenv("API_TOKEN")
    if not token:
        return True

    # If the request is already authenticated via Django session, do not require an API key.
    try:
        user_obj = getattr(request, "user", None)
        if user_obj and getattr(user_obj, "is_authenticated", False):
            return True
    except Exception:
        pass

    # Auth endpoints must remain accessible to allow users to log in / reset passwords.
    try:
        if (request.path or "").startswith("/api/auth/"):
            return True
    except Exception:
        pass

    provided = request.headers.get("X-API-KEY")
    return provided == token


def requester_identity(request):
    """
    Return the requester identity for activity logs.

    Prefer the authenticated Django user (session) when available.
    Falls back to request headers for backward compatibility.
    """
    try:
        user_obj = getattr(request, "user", None)
        if user_obj and getattr(user_obj, "is_authenticated", False):
            profile = getattr(user_obj, "profile", None)
            role = getattr(profile, "role", None) or UserProfile.ROLE_MANAGER
            display_name = (
                getattr(profile, "nom", "") if profile else ""
            ) or getattr(user_obj, "get_full_name", lambda: "")() or getattr(user_obj, "username", "") or "Utilisateur"
            return display_name, role
    except Exception:
        pass

    user = request.headers.get("X-User", "Système")
    role = request.headers.get("X-Role", "Auto")
    return user, role


def get_parameters_config() -> ParametersConfig:
    """Return the singleton parameters config, creating it with defaults if missing."""
    obj, _ = ParametersConfig.objects.get_or_create(id=1)
    return obj
