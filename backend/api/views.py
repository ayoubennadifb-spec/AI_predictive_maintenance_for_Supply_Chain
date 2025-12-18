import json
from datetime import datetime, date as dt_date, timedelta
from pathlib import Path

from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

import pandas as pd

from .export import export_budget_csv, export_consumptions_csv, export_previsions_csv
from .models import ActivityLog, BudgetConfig, Consumption, Part, Selection, UserProfile
from .utils import (
    check_api_auth,
    ensure_parts_loaded,
    load_json,
    log_activity,
    requester_identity,
    get_parameters_config,
)

BASE_DIR = Path(__file__).resolve().parent.parent


def error_response(message: str, status: int = 400, code: str | None = None, details: str | None = None):
    """Helper to return a consistent JSON error payload."""
    payload = {"error": message}
    if code is not None:
        payload["code"] = code
    if details is not None:
        payload["details"] = details
    return JsonResponse(payload, status=status)


def ensure_manager(request):
    """
    Helper for manager-only admin APIs.

    - Enforces API token via check_api_auth
    - Enforces X-Role == manager (UserProfile.ROLE_MANAGER)

    Returns ((user, role), None) on success, or (None, JsonResponse) on failure.
    """
    if not check_api_auth(request):
        return None, error_response("Unauthorized", status=403, code="unauthorized")

    user, role = requester_identity(request)
    if role != UserProfile.ROLE_MANAGER:
        return None, error_response("Accès réservé aux managers", status=403, code="forbidden")

    return (user, role), None


def ensure_super_admin(request):
    """
    Helper for super-admin-only APIs (user management).

    - Enforces API token via check_api_auth
    - Enforces X-Role == superadmin (UserProfile.ROLE_SUPERADMIN)

    Returns ((user, role), None) on success, or (None, JsonResponse) on failure.
    """
    if not check_api_auth(request):
        return None, error_response("Unauthorized", status=403, code="unauthorized")

    user, role = requester_identity(request)
    if role != UserProfile.ROLE_SUPERADMIN:
        return None, error_response("Accès réservé aux super-administrateurs", status=403, code="forbidden")

    return (user, role), None


# ---------------------------------------------------------------------------
# Prévisions & achats
# ---------------------------------------------------------------------------


@require_GET
def previsions(request):
    """
    Liste des pièces avec leurs prévisions.

    Filtres simples côté serveur pour rester cohérent avec l'UI :
    - search : recherche sur code / désignation / fournisseur
    - criticite : urgent / moyen / normal
    - limit / offset : pagination simple
    """
    ensure_parts_loaded()
    qs = Part.objects.all().order_by("code")

    search = request.GET.get("search")
    criticite = request.GET.get("criticite")

    if search:
        s = search.strip()
        if s:
            qs = qs.filter(
                Q(code__icontains=s)
                | Q(designation__icontains=s)
                | Q(fournisseur__icontains=s)
            )

    if criticite:
        qs = qs.filter(criticite__iexact=criticite.strip())

    limit = request.GET.get("limit")
    offset = request.GET.get("offset")

    try:
        if offset is not None:
            qs = qs[int(offset) :]
        if limit is not None:
            qs = qs[: int(limit)]
    except (TypeError, ValueError):
        # En cas de mauvais paramètres, on retourne simplement la liste filtrée
        pass

    data = [p.to_dict() for p in qs]
    return JsonResponse(data, safe=False)


@require_GET
def purchases(request):
    """
    Besoins d'achat dérivés de n_ac_2025.

    Filtres :
    - search : code / désignation / fournisseur
    - criticite : urgent / moyen / normal
    - limit / offset : pagination
    """
    ensure_parts_loaded()
    qs = Part.objects.all().order_by("code")

    search = request.GET.get("search")
    criticite = request.GET.get("criticite")

    if search:
        s = search.strip()
        if s:
            qs = qs.filter(
                Q(code__icontains=s)
                | Q(designation__icontains=s)
                | Q(fournisseur__icontains=s)
            )

    if criticite:
        qs = qs.filter(criticite__iexact=criticite.strip())

    limit = request.GET.get("limit")
    offset = request.GET.get("offset")

    try:
        if offset is not None:
            qs = qs[int(offset) :]
        if limit is not None:
            qs = qs[: int(limit)]
    except (TypeError, ValueError):
        pass

    data = []
    for idx, p in enumerate(qs):
        qty = max(0, p.n_ac_2025)
        data.append(
            {
                "id": idx + 1,
                "code": p.code,
                "designation": p.designation,
                "criticite": p.criticite,
                "quantite": qty,
                "prixUnitaire": p.prix_unitaire,
                "total": qty * p.prix_unitaire,
                "delai": p.delai,
            }
        )

    return JsonResponse(data, safe=False)


@require_GET
def metrics(request):
    if not check_api_auth(request):
        return error_response("Unauthorized", status=403, code="unauthorized")
    """Renvoie les métriques du modèle ML à partir du JSON exporté."""
    metrics_path = (
        BASE_DIR.parent
        / "webapp"
        / "UI for forecasting2"
        / "src"
        / "assets"
        / "model_metrics.json"
    )
    data = load_json(metrics_path) or {}
    return JsonResponse(data, safe=False)


@require_GET
def export_previsions_csv_view(request):
    if not check_api_auth(request):
        return error_response("Unauthorized", status=403, code="unauthorized")
    ensure_parts_loaded()
    return export_previsions_csv()


@require_GET
def export_budget_csv_view(request):
    if not check_api_auth(request):
        return error_response("Unauthorized", status=403, code="unauthorized")
    ensure_parts_loaded()
    return export_budget_csv()


@require_GET
def export_consommations_csv_view(request):
    if not check_api_auth(request):
        return error_response("Unauthorized", status=403, code="unauthorized")
    ensure_parts_loaded()
    return export_consumptions_csv()


# ---------------------------------------------------------------------------
# Saisie des consommations
# ---------------------------------------------------------------------------


@csrf_exempt
@require_http_methods(["GET", "POST"])
def consumptions(request):
    ensure_parts_loaded()
    if request.method == "GET":
        date_str = request.GET.get("date")
        month_param = request.GET.get("month")
        qs = Consumption.objects.all()
        if date_str:
            qs = qs.filter(date=date_str)
        if month_param:
            try:
                year, month = month_param.split("-")
                year_i = int(year)
                month_i = int(month)
                qs = qs.filter(date__year=year_i, date__month=month_i)

                # En vue "mois", on agrège par code pour garantir 1 ligne/code.
                if not date_str:
                    agg = (
                        qs.values("part__code")
                        .annotate(valeur=Sum("valeur"))
                        .order_by("part__code")
                    )
                    month_date = dt_date(year_i, month_i, 1).isoformat()
                    data = [
                        {
                            "code": r["part__code"],
                            "date": month_date,
                            "valeur": float(r["valeur"] or 0.0),
                        }
                        for r in agg
                    ]
                    return JsonResponse(data, safe=False)
            except Exception:
                pass
        data = [
            {
                "code": c.part.code,
                "date": c.date.isoformat(),
                "valeur": c.valeur,
            }
            for c in qs
        ]
        return JsonResponse(data, safe=False)

    # POST
    if not check_api_auth(request):
        return error_response("Unauthorized", status=403, code="unauthorized")

    user, role = requester_identity(request)
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return error_response("Invalid JSON", status=400, code="invalid_json")

    items = payload if isinstance(payload, list) else [payload]
    saved = []
    errors = []
    predictions = []

    def recompute_prevision(part: Part) -> tuple[float, float]:
        """
        n_pm = prévision mensuelle issue du modèle (prévision_m1 ou moyenne_m3),
        n_ac = max(0, n_pm + n_ss - n_sa + n_pm * dl)
        n_sa = stock_actuel (mis à jour avec les saisies cumulées du mois)
        """
        # IMPORTANT: prevision_m1 peut valoir 0.0 (prédiction ML valide). Ne pas utiliser `or` ici.
        n_pm = float(part.prevision_m1) if part.prevision_m1 is not None else float(part.moyenne_m3 or 0.0)
        delai_mois = max(0.0, part.delai / 30.0)
        n_ac = max(0.0, n_pm + part.stock_securite - part.stock_actuel + n_pm * delai_mois)
        part.n_ac_2025 = n_ac
        part.save(update_fields=["n_ac_2025"])
        return n_pm, n_ac

    for item in items:
        code = item.get("code")
        date_value = item.get("date")
        valeur = item.get("valeur")

        if not code or not date_value or valeur is None:
            errors.append({"item": item, "error": "missing fields"})
            continue

        part = Part.objects.filter(code=code).first()
        if not part:
            errors.append({"item": item, "error": "unknown part"})
            continue

        try:
            try:
                parsed_date = dt_date.fromisoformat(date_value)
            except Exception:
                errors.append({"item": item, "error": "invalid date"})
                continue

            val = float(valeur)
            if val < 0:
                errors.append({"item": item, "error": "negative value"})
                continue

            # Cumulative per month: on stocke la valeur mensuelle accumulée (valeur absolue).
            existing = (
                Consumption.objects.filter(part=part, date__year=parsed_date.year, date__month=parsed_date.month)
                .order_by("date")
                .first()
            )
            if existing:
                existing.valeur = val
                obj = existing
                obj.save(update_fields=["valeur"])
            else:
                obj = Consumption.objects.create(part=part, date=parsed_date, valeur=val)

            # stock_actuel = n_sa (valeur mensuelle accumulée saisie/importée)
            part.stock_actuel = max(0.0, val)
            part.save(update_fields=["stock_actuel"])

            new_prev, n_ac = recompute_prevision(part)
            saved.append(
                {
                    "code": obj.part.code,
                    "date": obj.date.isoformat(),
                    "valeur": obj.valeur,
                }
            )
            predictions.append({"code": part.code, "previsionM1": new_prev, "n_ac_2025": n_ac})
        except (ValueError, IntegrityError) as exc:
            errors.append({"item": item, "error": str(exc)})

    if saved:
        log_activity(
            action=f"Saisie consommations ({len(saved)})",
            module="Saisie",
            details=f"Dates: {', '.join(sorted({s['date'] for s in saved}))}",
            utilisateur=user,
            role=role,
        )

    status = 207 if errors else 201
    return JsonResponse({"saved": saved, "errors": errors, "predictions": predictions}, status=status)


@csrf_exempt
@require_http_methods(["POST"])
def reset_consumptions(request):
    """
    Réinitialise la consommation/stock_saisi (n_sa) à 0 pour le mois donné.
    - Supprime les enregistrements Consumption du mois.
    - Remet stock_actuel=0 et recalcule n_ac_2025 pour garder la cohérence.
    """
    ensure_parts_loaded()
    if not check_api_auth(request):
        return error_response("Unauthorized", status=403, code="unauthorized")

    user, role = requester_identity(request)
    try:
        payload = json.loads(request.body.decode("utf-8")) if request.body else {}
    except Exception:
        payload = {}

    month_param = (payload.get("month") or "").strip()
    date_param = (payload.get("date") or "").strip()
    if not month_param and date_param:
        month_param = date_param[:7]

    if not month_param or len(month_param) != 7 or "-" not in month_param:
        return error_response("month required (YYYY-MM)", status=400, code="missing_month")

    try:
        year_s, month_s = month_param.split("-")
        year_i = int(year_s)
        month_i = int(month_s)
        if not (1 <= month_i <= 12):
            raise ValueError("invalid month")
    except Exception:
        return error_response("invalid month", status=400, code="invalid_month")

    deleted_count, _ = Consumption.objects.filter(date__year=year_i, date__month=month_i).delete()

    parts = list(Part.objects.all())
    for part in parts:
        part.stock_actuel = 0.0
        # IMPORTANT: prevision_m1 peut valoir 0.0 (prédiction ML valide). Ne pas utiliser `or` ici.
        n_pm = float(part.prevision_m1) if part.prevision_m1 is not None else float(part.moyenne_m3 or 0.0)
        delai_mois = max(0.0, (part.delai or 0.0) / 30.0)
        part.n_ac_2025 = max(0.0, n_pm + (part.stock_securite or 0.0) - part.stock_actuel + n_pm * delai_mois)

    if parts:
        Part.objects.bulk_update(parts, ["stock_actuel", "n_ac_2025"])

    log_activity(
        action="Réinitialisation consommations",
        module="Saisie",
        details=f"month={month_param}, deleted={deleted_count}",
        utilisateur=user,
        role=role,
    )

    return JsonResponse(
        {
            "ok": True,
            "month": month_param,
            "deleted": deleted_count,
            "parts_reset": len(parts),
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def import_consumptions(request):
    """
    Import CSV (code;valeur[,date optionnel]) et applique les règles de cumul + recalcul.
    """
    ensure_parts_loaded()
    if not check_api_auth(request):
        return error_response("Unauthorized", status=403, code="unauthorized")

    user, role = requester_identity(request)
    upload = request.FILES.get("file")
    date_override = request.POST.get("date")  # optionnel, sinon date du jour
    if not upload:
        return error_response("No file provided", status=400, code="missing_file")

    try:
        content = upload.read().decode("utf-8")
    except Exception:
        return error_response("Cannot read file", status=400, code="invalid_file")

    import csv
    from io import StringIO

    reader = csv.reader(StringIO(content), delimiter=";")
    rows = list(reader)
    if not rows:
        return error_response("Empty file", status=400, code="empty_file")

    # Skip header if first cell is 'code'
    if rows and rows[0] and str(rows[0][0]).strip().lower() == "code":
        rows = rows[1:]

    cfg = get_parameters_config()
    saved: list[dict] = []
    errors: list[dict] = []
    predictions: list[dict] = []

    def recompute_prevision(part: Part) -> tuple[float, float]:
        # IMPORTANT: prevision_m1 peut valoir 0.0 (prédiction ML valide). Ne pas utiliser `or` ici.
        n_pm = float(part.prevision_m1) if part.prevision_m1 is not None else float(part.moyenne_m3 or 0.0)
        delai_mois = max(0.0, part.delai / 30.0)
        n_ac = max(0.0, n_pm + part.stock_securite - part.stock_actuel + n_pm * delai_mois)
        part.n_ac_2025 = n_ac
        part.save(update_fields=["n_ac_2025"])
        return n_pm, n_ac

    for line in rows:
        if not line or len(line) < 2:
            errors.append({"line": line, "error": "missing columns"})
            continue
        code = str(line[0]).strip()
        val_raw = line[1]
        date_raw = line[2] if len(line) > 2 else date_override
        if not code:
            errors.append({"line": line, "error": "missing code"})
            continue
        part = Part.objects.filter(code=code).first()
        if not part:
            errors.append({"line": line, "error": "unknown part"})
            continue
        try:
            val = float(val_raw)
            if val < 0:
                errors.append({"line": line, "error": "negative value"})
                continue
        except Exception:
            errors.append({"line": line, "error": "invalid value"})
            continue

        # Date
        if date_raw:
            try:
                parsed_date = dt_date.fromisoformat(date_raw)
            except Exception:
                errors.append({"line": line, "error": "invalid date"})
                continue
        else:
            parsed_date = dt_date.today().replace(day=1)

        # cumul mensuel
        existing = (
            Consumption.objects.filter(part=part, date__year=parsed_date.year, date__month=parsed_date.month)
            .order_by("date")
            .first()
        )
        if existing:
            existing.valeur += val
            obj = existing
            obj.save(update_fields=["valeur"])
        else:
            obj = Consumption.objects.create(part=part, date=parsed_date, valeur=val)

        # mettre à jour le stock actuel en cumulant la saisie du mois
        part.stock_actuel = max(0.0, (part.stock_actuel or 0.0) + val)
        part.save(update_fields=["stock_actuel"])

        new_prev, n_ac = recompute_prevision(part)
        saved.append(
            {
                "code": obj.part.code,
                "date": obj.date.isoformat(),
                "valeur": obj.valeur,
                "delta": val,
            }
        )
        predictions.append({"code": part.code, "previsionM1": new_prev, "n_ac_2025": n_ac})

    if saved:
        log_activity(
          action=f"Import consommations ({len(saved)})",
          module="Saisie",
          details=f"fichier={upload.name}, date={date_override or 'auto'}",
          utilisateur=user,
          role=role,
        )

    status = 207 if errors else 201
    return JsonResponse({"saved": saved, "errors": errors, "predictions": predictions}, status=status)


# ---------------------------------------------------------------------------
# Approvals & budget
# ---------------------------------------------------------------------------


@csrf_exempt
@require_http_methods(["GET", "POST"])
def approvals(request):
    ensure_parts_loaded()
    if request.method == "GET":
        approved = list(
            Part.objects.filter(approuve=True).values_list("code", flat=True)
        )
        return JsonResponse({"approved": approved})

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return error_response("Invalid JSON", status=400, code="invalid_json")

    codes = payload.get("codes") if isinstance(payload, dict) else None
    if not codes or not isinstance(codes, list):
        return error_response("codes list required", status=400, code="missing_codes")

    if not check_api_auth(request):
        return error_response("Unauthorized", status=403, code="unauthorized")

    user, role = requester_identity(request)
    Part.objects.filter(code__in=codes).update(approuve=True)
    log_activity(
        action=f"Approvals ({len(codes)})",
        module="Prévisions",
        details=",".join(codes),
        utilisateur=user,
        role=role,
    )
    return JsonResponse({"approved": codes})


@csrf_exempt
@require_http_methods(["GET", "POST"])
def budget_state(request):
    ensure_parts_loaded()

    if request.method == "GET":
        config, _ = BudgetConfig.objects.get_or_create(id=1)
        selections = Selection.objects.filter(selected=True).values_list(
            "part__code", flat=True
        )
        return JsonResponse(
            {
                "budget_cap": config.budget_cap,
                "selected_codes": list(selections),
            }
        )

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return error_response("Invalid JSON", status=400, code="invalid_json")

    cap = payload.get("budget_cap")
    selected_codes = payload.get("selected_codes", [])

    if not check_api_auth(request):
        return error_response("Unauthorized", status=403, code="unauthorized")

    user, role = requester_identity(request)

    try:
        parsed_cap = None if cap is None or cap == "" else float(cap)
    except (TypeError, ValueError):
        return error_response(
            "budget_cap must be a number or null",
            status=400,
            code="invalid_budget_cap",
        )

    config, _ = BudgetConfig.objects.get_or_create(id=1)
    config.budget_cap = parsed_cap
    config.save()

    # reset then set selections
    Selection.objects.all().delete()
    bulk = []
    for code in selected_codes:
        part = Part.objects.filter(code=code).first()
        if part:
            bulk.append(Selection(part=part, selected=True))
    Selection.objects.bulk_create(bulk)

    log_activity(
        action="Budget/selection sauvegardés",
        module="Budget",
        details=f"cap={config.budget_cap}, selected={len(selected_codes)}",
        utilisateur=user,
        role=role,
    )
    return JsonResponse(
        {
            "ok": True,
            "budget_cap": config.budget_cap,
            "selected_codes": selected_codes,
        }
    )


# ---------------------------------------------------------------------------
# Paramètres système (reliés à l'UI Paramètres)
# ---------------------------------------------------------------------------


def _serialize_parameters(config):
    return {
        "ruptureThreshold": config.rupture_threshold,
        "longLeadDays": config.long_lead_days,
        "budgetCap": config.budget_cap,
        "autoSelectCritical": config.auto_select_critical,
        "activeModel": config.active_model,
        "refreshFrequency": config.refresh_frequency,
        "notifyRupture": config.notify_rupture,
        "notifyBudget": config.notify_budget,
        "notifyDigest": config.notify_digest,
        "updatedAt": config.updated_at.isoformat(),
        "updatedBy": config.updated_by,
        "updatedRole": config.updated_role,
    }


@csrf_exempt
@require_http_methods(["GET", "POST"])
def parameters(request):
    config = get_parameters_config()

    if request.method == "GET":
        return JsonResponse(_serialize_parameters(config))

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return error_response("Invalid JSON", status=400, code="invalid_json")

    if not check_api_auth(request):
        return error_response("Unauthorized", status=403, code="unauthorized")

    user, role = requester_identity(request)

    # Validation
    def _num(value, allow_none=False):
        if value is None and allow_none:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            raise ValueError

    try:
        if "ruptureThreshold" in payload:
            rt = _num(payload.get("ruptureThreshold"))
            if rt < 0 or rt > 100:
                return error_response("ruptureThreshold must be between 0 and 100", status=400, code="invalid_rupture_threshold")
            config.rupture_threshold = rt

        if "longLeadDays" in payload:
            ld = _num(payload.get("longLeadDays"))
            if ld < 0:
                return error_response("longLeadDays must be >= 0", status=400, code="invalid_long_lead")
            config.long_lead_days = int(ld)

        if "budgetCap" in payload:
            config.budget_cap = _num(payload.get("budgetCap"), allow_none=True)

        if "autoSelectCritical" in payload:
            config.auto_select_critical = bool(payload.get("autoSelectCritical"))

        if "activeModel" in payload:
            val = str(payload.get("activeModel") or "").strip() or "hist-gradient-boosting"
            config.active_model = val[:64]

        if "refreshFrequency" in payload:
            freq = str(payload.get("refreshFrequency") or "").strip()
            allowed = {"journalier", "hebdomadaire", "mensuel"}
            if freq not in allowed:
                return error_response("refreshFrequency invalid", status=400, code="invalid_refresh_frequency")
            config.refresh_frequency = freq

        if "notifyRupture" in payload:
            config.notify_rupture = bool(payload.get("notifyRupture"))
        if "notifyBudget" in payload:
            config.notify_budget = bool(payload.get("notifyBudget"))
        if "notifyDigest" in payload:
            config.notify_digest = bool(payload.get("notifyDigest"))
    except ValueError:
        return error_response("Invalid numeric value", status=400, code="invalid_number")

    config.updated_by = user
    config.updated_role = role
    config.save()

    log_activity(
        action="Paramètres mis à jour",
        module="Paramètres",
        details=f"rupture={config.rupture_threshold}, lead={config.long_lead_days}, budgetCap={config.budget_cap}",
        utilisateur=user,
        role=role,
    )
    return JsonResponse(_serialize_parameters(config))


# ---------------------------------------------------------------------------
# Activités / audit
# ---------------------------------------------------------------------------


@require_GET
def activities(request):
    if not check_api_auth(request):
        return error_response("Unauthorized", status=403, code="unauthorized")
    """
    Retourne les activités récentes.

    Filtres optionnels via query params :
    - module : nom de module (Saisie, Budget, Prévisions, Admin, ...)
    - from : datetime ISO (>= created_at)
    - to : datetime ISO (<= created_at)
    - limit : nombre maximum d'entrées (défaut 50)
    """
    qs = ActivityLog.objects.all().order_by("-created_at")

    module = request.GET.get("module")
    if module:
        qs = qs.filter(module__iexact=module.strip())

    from_param = request.GET.get("from")
    to_param = request.GET.get("to")

    if from_param:
        try:
            dt_from = datetime.fromisoformat(from_param)
            qs = qs.filter(created_at__gte=dt_from)
        except ValueError:
            # on ignore un filtre mal formaté
            pass

    if to_param:
        try:
            dt_to = datetime.fromisoformat(to_param)
            qs = qs.filter(created_at__lte=dt_to)
        except ValueError:
            pass

    limit_param = request.GET.get("limit")
    try:
        limit = int(limit_param) if limit_param is not None else 50
    except (TypeError, ValueError):
        limit = 50
    if limit <= 0:
        limit = 50

    qs = qs[:limit]

    data = [
        {
            "utilisateur": a.utilisateur,
            "role": a.role,
            "action": a.action,
            "module": a.module,
            "details": a.details,
            "date": a.created_at.isoformat(),
        }
        for a in qs
    ]
    return JsonResponse(data, safe=False)


# ---------------------------------------------------------------------------
# Recompute previsions from trained model
# ---------------------------------------------------------------------------


@csrf_exempt
@require_http_methods(["POST"])
def recompute_previsions(request):
    """
    Re-run model inference (HistGradientBoosting) and update Part prevision/n_ac.
    Uses part2 dataset for stock/délai if available.
    """
    if not check_api_auth(request):
        return error_response("Unauthorized", status=403, code="unauthorized")

    try:
        from .inference import run_inference
    except Exception as exc:
        return error_response("Inference module unavailable", status=500, code="inference_missing", details=str(exc))

    try:
        preds_df = run_inference()
    except Exception as exc:
        return error_response("Inference failed", status=500, code="inference_failed", details=str(exc))

    part2_path = BASE_DIR.parent / "data" / "processed" / "part2_clean_step2.parquet"
    p2_df = pd.read_parquet(part2_path) if part2_path.exists() else pd.DataFrame()
    p2_df = p2_df.set_index("code_piece") if not p2_df.empty else p2_df

    updated = 0
    created = 0
    cfg = get_parameters_config()

    for _, row in preds_df.iterrows():
        code = str(row["code_piece"])
        part = Part.objects.filter(code=code).first()
        if not part:
            part = Part(code=code)
            created += 1
        p2 = p2_df.loc[code] if not p2_df.empty and code in p2_df.index else None

        stock_securite = float(p2["stock_securite"]) if p2 is not None else 0.0
        stock_actuel = float(p2["stock_actuel"]) if p2 is not None else 0.0
        delai = float(p2["Délai de livr prévi"]) if p2 is not None and "Délai de livr prévi" in p2 else 0.0
        prix_uni = float(p2["prix_uni_final"]) if p2 is not None and "prix_uni_final" in p2 else 0.0
        designation = str(p2["Désignation langue"]) if p2 is not None and "Désignation langue" in p2 else ""
        criticite = str(p2["classif"]) if p2 is not None and "classif" in p2 else "normal"
        moyenne_m3 = float(p2["cons_moy_mensuelle"]) if p2 is not None and "cons_moy_mensuelle" in p2 else float(row["n_pm_2025"])

        prevision_m1 = float(row["n_pm_2025"])
        delai_mois = max(0.0, delai / 30.0)
        n_ac = max(0.0, prevision_m1 + stock_securite - stock_actuel + prevision_m1 * delai_mois)

        # Ajustement criticité / délai
        if cfg.auto_select_critical and criticite.lower().startswith("a"):
            prevision_m1 *= 1.05
        if delai > cfg.long_lead_days:
            prevision_m1 *= 1.05
        n_ac = max(0.0, prevision_m1 + stock_securite - stock_actuel + prevision_m1 * delai_mois)

        part.designation = designation
        part.criticite = criticite
        part.stock_actuel = stock_actuel
        part.stock_securite = stock_securite
        part.moyenne_m3 = moyenne_m3
        part.prevision_m1 = prevision_m1
        part.prix_unitaire = prix_uni
        part.fournisseur = "N/A"
        part.delai = delai
        part.n_ac_2025 = n_ac
        part.save()
        updated += 1

    log_activity(
        action=f"Recompute previsions (model) updated={updated}, created={created}",
        module="ML",
        details="HistGradientBoosting inference",
        utilisateur=requester_identity(request)[0],
        role=requester_identity(request)[1],
    )

    return JsonResponse({"updated": updated, "created": created})


# ---------------------------------------------------------------------------
# Admin JSON API (manager-only) - React administration
# ---------------------------------------------------------------------------


def _serialize_part_admin(part: Part) -> dict:
    return {
        "code": part.code,
        "designation": part.designation,
        "criticite": part.criticite,
        "stock_actuel": float(part.stock_actuel or 0.0),
        "stock_securite": float(part.stock_securite or 0.0),
        "moyenne_m3": float(part.moyenne_m3 or 0.0),
        "prevision_m1": float(part.prevision_m1 or 0.0),
        "ecart_pourcent": float(part.ecart_pourcent or 0.0),
        "prix_unitaire": float(part.prix_unitaire or 0.0),
        "fournisseur": part.fournisseur,
        "delai": float(part.delai or 0.0),
        "n_ac_2025": float(part.n_ac_2025 or 0.0),
        "approuve": bool(part.approuve),
    }


def _serialize_consumption_admin(obj: Consumption) -> dict:
    return {
        "id": obj.id,
        "part_code": obj.part.code,
        "date": obj.date.isoformat(),
        "valeur": float(obj.valeur or 0.0),
        "created_at": obj.created_at.isoformat(),
    }


def _serialize_user_admin(profile: UserProfile) -> dict:
    user = profile.user
    display_name = profile.nom or getattr(user, "get_full_name", lambda: "")() or getattr(user, "username", "")
    return {
        "id": int(getattr(user, "pk", 0)),
        "username": getattr(user, "username", ""),
        "email": getattr(user, "email", "") or "",
        "nom": display_name,
        "role": profile.role,
        "created_at": profile.created_at.isoformat(),
    }


def _parse_float(value, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError


def _recompute_part_nac(part: Part) -> tuple[float, float]:
    """
    Helper to recompute n_ac_2025 after a stock change.
    Mirrors the logic used in consumptions/import views.
    """
    # IMPORTANT: prevision_m1 can legitimately be 0.0 (valid ML prediction) -> do not use `or`.
    n_pm = float(part.prevision_m1) if part.prevision_m1 is not None else float(part.moyenne_m3 or 0.0)
    delai_mois = max(0.0, (part.delai or 0.0) / 30.0)
    n_ac = max(0.0, n_pm + (part.stock_securite or 0.0) - (part.stock_actuel or 0.0) + n_pm * delai_mois)
    part.n_ac_2025 = n_ac
    part.save(update_fields=["n_ac_2025"])
    return n_pm, n_ac


@csrf_exempt
@require_http_methods(["GET", "POST"])
def admin_parts(request):
    ensure_parts_loaded()
    identity, error = ensure_manager(request)
    if error:
        return error
    user, role = identity

    if request.method == "GET":
        qs = Part.objects.all().order_by("code")

        search = request.GET.get("search")
        criticite = request.GET.get("criticite")

        if search:
            s = search.strip()
            if s:
                qs = qs.filter(
                    Q(code__icontains=s)
                    | Q(designation__icontains=s)
                    | Q(fournisseur__icontains=s)
                )

        if criticite:
            qs = qs.filter(criticite__iexact=criticite.strip())

        total = qs.count()
        limit = request.GET.get("limit")
        offset = request.GET.get("offset")
        try:
            if offset is not None:
                qs = qs[int(offset) :]
            if limit is not None:
                qs = qs[: int(limit)]
        except (TypeError, ValueError):
            # ignore bad pagination parameters
            pass

        data = [_serialize_part_admin(p) for p in qs]
        return JsonResponse({"results": data, "count": total})

    # POST -> create a new Part
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return error_response("Invalid JSON", status=400, code="invalid_json")

    code = str(payload.get("code") or "").strip()
    if not code:
        return error_response("code is required", status=400, code="missing_code")

    try:
        part = Part.objects.create(
            code=code,
            designation=str(payload.get("designation") or ""),
            criticite=str(payload.get("criticite") or "normal"),
            stock_actuel=_parse_float(payload.get("stock_actuel"), 0.0),
            stock_securite=_parse_float(payload.get("stock_securite"), 0.0),
            moyenne_m3=_parse_float(payload.get("moyenne_m3"), 0.0),
            prevision_m1=_parse_float(payload.get("prevision_m1"), 0.0),
            ecart_pourcent=_parse_float(payload.get("ecart_pourcent"), 0.0),
            prix_unitaire=_parse_float(payload.get("prix_unitaire"), 0.0),
            fournisseur=str(payload.get("fournisseur") or ""),
            delai=_parse_float(payload.get("delai"), 0.0),
            n_ac_2025=_parse_float(payload.get("n_ac_2025"), 0.0),
            approuve=bool(payload.get("approuve", False)),
        )
    except ValueError:
        return error_response("Invalid numeric value", status=400, code="invalid_number")
    except IntegrityError:
        return error_response("Part already exists", status=409, code="part_exists")

    log_activity(
        action=f"Pièce créée ({part.code})",
        module="Admin",
        utilisateur=user,
        role=role,
    )
    return JsonResponse(_serialize_part_admin(part), status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH", "DELETE"])
def admin_part_detail(request, code: str):
    ensure_parts_loaded()
    identity, error = ensure_manager(request)
    if error:
        return error
    user, role = identity

    part = Part.objects.filter(code=code).first()
    if not part:
        return error_response("Part not found", status=404, code="not_found")

    if request.method == "GET":
        return JsonResponse(_serialize_part_admin(part))

    if request.method == "DELETE":
        part.delete()
        log_activity(
            action=f"Pièce supprimée ({code})",
            module="Admin",
            utilisateur=user,
            role=role,
        )
        return JsonResponse({"ok": True})

    # PUT/PATCH -> update
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return error_response("Invalid JSON", status=400, code="invalid_json")

    fields_to_update: list[str] = []

    def set_num(field: str):
        if field in payload:
            try:
                value = _parse_float(payload.get(field))
            except ValueError:
                raise ValueError(field)
            setattr(part, field, value)
            fields_to_update.append(field)

    def set_str(field: str):
        if field in payload:
            setattr(part, field, str(payload.get(field) or ""))
            fields_to_update.append(field)

    try:
        set_str("designation")
        set_str("criticite")
        set_str("fournisseur")
        set_num("stock_actuel")
        set_num("stock_securite")
        set_num("moyenne_m3")
        set_num("prevision_m1")
        set_num("ecart_pourcent")
        set_num("prix_unitaire")
        set_num("delai")
        set_num("n_ac_2025")
    except ValueError as exc:
        field = str(exc) if str(exc) else "field"
        return error_response(f"Invalid numeric value for {field}", status=400, code="invalid_number")

    if "approuve" in payload:
        part.approuve = bool(payload.get("approuve"))
        fields_to_update.append("approuve")

    if fields_to_update:
        part.save(update_fields=fields_to_update)

    log_activity(
        action=f"Pièce mise à jour ({part.code})",
        module="Admin",
        utilisateur=user,
        role=role,
    )
    return JsonResponse(_serialize_part_admin(part))


@csrf_exempt
@require_http_methods(["GET", "POST"])
def admin_consumptions(request):
    ensure_parts_loaded()
    identity, error = ensure_manager(request)
    if error:
        return error
    user, role = identity

    if request.method == "GET":
        qs = Consumption.objects.select_related("part").all().order_by("-date", "part__code")

        code = request.GET.get("code")
        if code:
            qs = qs.filter(part__code__icontains=code.strip())

        from_param = request.GET.get("from")
        to_param = request.GET.get("to")

        if from_param:
            try:
                d_from = dt_date.fromisoformat(from_param)
                qs = qs.filter(date__gte=d_from)
            except ValueError:
                pass

        if to_param:
            try:
                d_to = dt_date.fromisoformat(to_param)
                qs = qs.filter(date__lte=d_to)
            except ValueError:
                pass

        total = qs.count()
        limit = request.GET.get("limit")
        offset = request.GET.get("offset")
        try:
            if offset is not None:
                qs = qs[int(offset) :]
            if limit is not None:
                qs = qs[: int(limit)]
        except (TypeError, ValueError):
            pass

        data = [_serialize_consumption_admin(c) for c in qs]
        return JsonResponse({"results": data, "count": total})

    # POST -> create / upsert
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return error_response("Invalid JSON", status=400, code="invalid_json")

    code = str(payload.get("code") or "").strip()
    date_value = payload.get("date")
    valeur = payload.get("valeur")

    if not code or not date_value or valeur is None:
        return error_response("code, date and valeur are required", status=400, code="missing_fields")

    part = Part.objects.filter(code=code).first()
    if not part:
        return error_response("Unknown part", status=404, code="unknown_part")

    try:
        parsed_date = dt_date.fromisoformat(str(date_value))
    except Exception:
        return error_response("Invalid date", status=400, code="invalid_date")

    try:
        val = _parse_float(valeur, 0.0)
    except ValueError:
        return error_response("Invalid valeur", status=400, code="invalid_number")

    if val < 0:
        return error_response("valeur must be >= 0", status=400, code="invalid_number")

    obj, created = Consumption.objects.update_or_create(
        part=part,
        date=parsed_date,
        defaults={"valeur": val},
    )

    part.stock_actuel = max(0.0, val)
    part.save(update_fields=["stock_actuel"])
    _recompute_part_nac(part)

    log_activity(
        action=f"Consommation {'créée' if created else 'mise à jour'} ({part.code} {parsed_date.isoformat()})",
        module="Admin",
        utilisateur=user,
        role=role,
    )
    status_code = 201 if created else 200
    return JsonResponse(_serialize_consumption_admin(obj), status=status_code)


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH", "DELETE"])
def admin_consumption_detail(request, pk: int):
    ensure_parts_loaded()
    identity, error = ensure_manager(request)
    if error:
        return error
    user, role = identity

    obj = Consumption.objects.select_related("part").filter(pk=pk).first()
    if not obj:
        return error_response("Consumption not found", status=404, code="not_found")

    part = obj.part

    if request.method == "GET":
        return JsonResponse(_serialize_consumption_admin(obj))

    if request.method == "DELETE":
        code = part.code
        date_str = obj.date.isoformat()
        obj.delete()
        part.stock_actuel = 0.0
        part.save(update_fields=["stock_actuel"])
        _recompute_part_nac(part)
        log_activity(
            action=f"Consommation supprimée ({code} {date_str})",
            module="Admin",
            utilisateur=user,
            role=role,
        )
        return JsonResponse({"ok": True})

    # PUT/PATCH -> update valeur/date
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return error_response("Invalid JSON", status=400, code="invalid_json")

    updated = False

    if "date" in payload:
        try:
            new_date = dt_date.fromisoformat(str(payload.get("date")))
            obj.date = new_date
            updated = True
        except Exception:
            return error_response("Invalid date", status=400, code="invalid_date")

    if "valeur" in payload:
        try:
            val = _parse_float(payload.get("valeur"), 0.0)
        except ValueError:
            return error_response("Invalid valeur", status=400, code="invalid_number")
        if val < 0:
            return error_response("valeur must be >= 0", status=400, code="invalid_number")
        obj.valeur = val
        part.stock_actuel = max(0.0, val)
        part.save(update_fields=["stock_actuel"])
        _recompute_part_nac(part)
        updated = True

    if updated:
        obj.save(update_fields=["date", "valeur"])
        log_activity(
            action=f"Consommation mise à jour ({part.code} {obj.date.isoformat()})",
            module="Admin",
            utilisateur=user,
            role=role,
        )

    return JsonResponse(_serialize_consumption_admin(obj))


@csrf_exempt
@require_http_methods(["GET", "POST"])
def admin_users(request):
    # Only super-admins can manage user accounts.
    identity, error = ensure_super_admin(request)
    if error:
        return error
    user, role = identity

    if request.method == "GET":
        qs = UserProfile.objects.select_related("user").all().order_by("-created_at")

        search = request.GET.get("search")
        if search:
            s = search.strip()
            if s:
                qs = qs.filter(
                    Q(user__username__icontains=s)
                    | Q(user__email__icontains=s)
                    | Q(nom__icontains=s)
                )

        total = qs.count()
        limit = request.GET.get("limit")
        offset = request.GET.get("offset")
        try:
            if offset is not None:
                qs = qs[int(offset) :]
            if limit is not None:
                qs = qs[: int(limit)]
        except (TypeError, ValueError):
            pass

        data = [_serialize_user_admin(p) for p in qs]
        return JsonResponse({"results": data, "count": total})

    # POST -> create user
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return error_response("Invalid JSON", status=400, code="invalid_json")

    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    email = str(payload.get("email") or "").strip()
    nom = str(payload.get("nom") or "").strip()
    role_raw = payload.get("role")

    from_role = _normalize_role(str(role_raw) if role_raw is not None else None)
    if not username or not from_role:
        return error_response("username and role are required", status=400, code="missing_fields")

    if password and len(password) < 4:
        return error_response("Password too short", status=400, code="password_too_short")

    User = get_user_model()
    if User.objects.filter(username__iexact=username).exists():
        return error_response("Username already exists", status=409, code="username_exists")

    try:
        user_obj = User.objects.create_user(username=username, email=email or None, password=password or None)
        if nom:
            try:
                user_obj.first_name = nom
                user_obj.save(update_fields=["first_name"])
            except Exception:
                pass
        profile = UserProfile.objects.create(user=user_obj, role=from_role, nom=nom)
    except Exception as exc:
        return error_response("Signup failed", status=500, code="signup_failed", details=str(exc))

    log_activity(
        action=f"Utilisateur créé ({username})",
        module="Admin",
        utilisateur=user,
        role=role,
    )
    return JsonResponse(_serialize_user_admin(profile), status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH", "DELETE"])
def admin_user_detail(request, pk: int):
    # Only super-admins can manage user accounts.
    identity, error = ensure_super_admin(request)
    if error:
        return error
    actor, actor_role = identity

    profile = UserProfile.objects.select_related("user").filter(user_id=pk).first()
    if not profile:
        return error_response("User not found", status=404, code="not_found")

    user = profile.user

    if request.method == "GET":
        return JsonResponse(_serialize_user_admin(profile))

    if request.method == "DELETE":
        username = user.username
        profile.delete()
        user.delete()
        log_activity(
            action=f"Utilisateur supprimé ({username})",
            module="Admin",
            utilisateur=actor,
            role=actor_role,
        )
        return JsonResponse({"ok": True})

    # PUT/PATCH -> update user/profile
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return error_response("Invalid JSON", status=400, code="invalid_json")

    fields_user: list[str] = []
    fields_profile: list[str] = []

    if "username" in payload:
        new_username = str(payload.get("username") or "").strip()
        if new_username and new_username.lower() != user.username.lower():
            User = get_user_model()
            if User.objects.filter(username__iexact=new_username).exclude(pk=user.pk).exists():
                return error_response("Username already exists", status=409, code="username_exists")
            user.username = new_username
            fields_user.append("username")

    if "email" in payload:
        user.email = str(payload.get("email") or "").strip()
        fields_user.append("email")

    if "nom" in payload:
        profile.nom = str(payload.get("nom") or "").strip()
        fields_profile.append("nom")
        try:
            user.first_name = profile.nom
            fields_user.append("first_name")
        except Exception:
            pass

    if "role" in payload:
        role_raw = payload.get("role")
        normalized = _normalize_role(str(role_raw) if role_raw is not None else None)
        if not normalized:
            return error_response("Invalid role", status=400, code="invalid_role")
        profile.role = normalized
        fields_profile.append("role")

    if "password" in payload:
        password = str(payload.get("password") or "")
        if password:
            if len(password) < 4:
                return error_response("Password too short", status=400, code="password_too_short")
            user.set_password(password)
            fields_user.append("password")

    if fields_user:
        user.save(update_fields=list(set(fields_user)))
    if fields_profile:
        profile.save(update_fields=list(set(fields_profile)))

    log_activity(
        action=f"Utilisateur mis à jour ({user.username})",
        module="Admin",
        utilisateur=actor,
        role=actor_role,
    )

    return JsonResponse(_serialize_user_admin(profile))


# ---------------------------------------------------------------------------
# Auth (signup/login) - simple JSON API for the React app
# ---------------------------------------------------------------------------


def _normalize_role(raw: str | None) -> str:
    v = (raw or "").strip().lower()
    if v in {"manager"}:
        return UserProfile.ROLE_MANAGER
    if v in {"approvisionnement", "approvisionneur", "appro"}:
        return UserProfile.ROLE_APPROVISIONNEMENT
    if v in {"logistique", "logiqtique", "log"}:
        return UserProfile.ROLE_LOGISTIQUE
    if v in {"superadmin", "super-admin", "admin"}:
        return UserProfile.ROLE_SUPERADMIN
    return ""


def _user_payload(user) -> dict:
    try:
        profile = user.profile
    except Exception:
        profile = None
    if profile:
        return profile.to_dict()
    return {
        "id": str(getattr(user, "pk", "")),
        "nom": getattr(user, "get_full_name", lambda: "")() or getattr(user, "username", ""),
        "email": getattr(user, "email", "") or "",
        "role": UserProfile.ROLE_MANAGER,
    }


@csrf_exempt
@require_http_methods(["POST"])
def auth_signup(request):
    """
    Create a new user for the webapp.

    Body JSON:
    - username (required)
    - password (required)
    - email (optional)
    - nom (optional)
    - role (required): manager | approvisionnement | logistique | superadmin
    """
    if not check_api_auth(request):
        return error_response("Unauthorized", status=403, code="unauthorized")

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return error_response("Invalid JSON", status=400, code="invalid_json")

    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    email = str(payload.get("email") or "").strip()
    nom = str(payload.get("nom") or "").strip()
    role_raw = payload.get("role")
    role = _normalize_role(str(role_raw) if role_raw is not None else None)

    if not username or not password or not role:
        return error_response("Missing fields", status=400, code="missing_fields")

    if len(password) < 4:
        return error_response("Password too short", status=400, code="password_too_short")

    User = get_user_model()
    if User.objects.filter(username__iexact=username).exists():
        return error_response("Username already exists", status=409, code="username_exists")

    try:
        user = User.objects.create_user(username=username, email=email or None, password=password)
        if nom:
            # Default Django User has first_name/last_name; store full name in first_name for simplicity.
            try:
                user.first_name = nom
                user.save(update_fields=["first_name"])
            except Exception:
                pass
        UserProfile.objects.create(user=user, role=role, nom=nom)
    except Exception as exc:
        return error_response("Signup failed", status=500, code="signup_failed", details=str(exc))

    return JsonResponse({"ok": True, "user": _user_payload(user)}, status=201)


@csrf_exempt
@require_http_methods(["POST"])
def auth_login(request):
    """
    Login endpoint for the webapp.

    Body JSON:
    - usernameOrEmail
    - password
    """
    if not check_api_auth(request):
        return error_response("Unauthorized", status=403, code="unauthorized")

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return error_response("Invalid JSON", status=400, code="invalid_json")

    username_or_email = str(payload.get("usernameOrEmail") or "").strip()
    password = str(payload.get("password") or "")

    if not username_or_email or not password:
        return error_response("Missing fields", status=400, code="missing_fields")

    user = authenticate(request, username=username_or_email, password=password)
    if user is None and "@" in username_or_email:
        User = get_user_model()
        candidate = User.objects.filter(email__iexact=username_or_email).first()
        if candidate:
            user = authenticate(request, username=candidate.username, password=password)

    if user is None:
        return error_response("Invalid credentials", status=401, code="invalid_credentials")

    # Ensure profile exists (backward compatibility)
    profile = getattr(user, "profile", None)
    if not profile:
        UserProfile.objects.get_or_create(
            user=user,
            defaults={
                "role": UserProfile.ROLE_MANAGER,
                "nom": getattr(user, "get_full_name", lambda: "")() or getattr(user, "username", ""),
            },
        )

    return JsonResponse({"ok": True, "user": _user_payload(user)})
