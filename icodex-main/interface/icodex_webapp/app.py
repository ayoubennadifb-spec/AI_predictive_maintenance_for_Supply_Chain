"""
Minimal multi-role ICodex web app.
- Signup/login with role (student|teacher) and basic profile fields.
- Teachers can upload a PDF, run the existing pipeline, preview the quiz, and assign tests to classes.
- Students see assigned tests, can mark them as completed (placeholder), and download reports.
Data is stored in a JSON file (no database).
"""

from __future__ import annotations

import json
import importlib.util
import re
import os
import base64
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from datetime import datetime, timezone, timedelta

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    Body,
)
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pipeline.config import DEFAULT_RAW_BANK_QUESTIONS
from pipeline.errors import PipelineStepError
from pipeline.graph import run_pipeline_graph
from pipeline.state import PipelineState, create_pipeline_state, model_dump_safe
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
REPO_ROOT = PROJECT_ROOT.parent
EVALUATOR_PATH = REPO_ROOT / "answers evaluation" / "answer_evaluator.py"
MASTERY_PATH = REPO_ROOT / "answers evaluation" / "mastery_scorer.py"
RECOMMENDER_PATH = REPO_ROOT / "questions recommander" / "question_recommender.py"
FRONTEND_BUILD_CANDIDATES = [
    REPO_ROOT / "interface" / "icodex_figma_interface" / "build",
]
_frontend_override = os.environ.get("ICODEX_FRONTEND_BUILD")
if _frontend_override:
    override_path = Path(_frontend_override)
    FRONTEND_BUILD = override_path if override_path.is_absolute() else (REPO_ROOT / override_path)
else:
    FRONTEND_BUILD = next((p for p in FRONTEND_BUILD_CANDIDATES if p.exists()), FRONTEND_BUILD_CANDIDATES[0])
FRONTEND_ASSETS = FRONTEND_BUILD / "assets"
_data_dir_override = os.environ.get("ICODEX_DATA_DIR")
if _data_dir_override:
    data_dir_path = Path(_data_dir_override)
    DATA_DIR = data_dir_path if data_dir_path.is_absolute() else (REPO_ROOT / data_dir_path)
else:
    DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
_state_file_override = os.environ.get("ICODEX_STATE_FILE")
if _state_file_override:
    state_file_path = Path(_state_file_override)
    STATE_FILE = state_file_path if state_file_path.is_absolute() else (DATA_DIR / state_file_path)
else:
    STATE_FILE = DATA_DIR / "state.json"
STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

DATABASE_URL = (
    os.environ.get("DATABASE_URL")
    or os.environ.get("ICODEX_DATABASE_URL")
    or ""
).strip() or None

DEFAULT_FEATURE_FLAGS = {
    "show_risk_signals": True,
    "auto_test_review": True,
    "ai_quality_metrics": True,
    "behavior_insights": True,
}

DEFAULT_GAMIFICATION_CONFIG = {
    "enabled": True,
    "xp_base": 10,
    "daily_question_cap": 60,
    "difficulty_multipliers": {"easy": 0.8, "medium": 1.0, "hard": 1.3},
    "improvement_bonus_multiplier": 2.0,
    "leaderboards_enabled": True,
    "quests_enabled": True,
    "auto_generate_quests": True,
    "auto_quest_reward": 30,
    "auto_quest_target": 5,
}

ACHIEVEMENT_DEFS = [
    {"key": "consistency", "name": "Consistency", "description": "Keep a 7‑day streak.", "type": "streak", "threshold": 7},
    {"key": "deep_work", "name": "Deep Work", "description": "Complete a 20-question practice session.", "type": "practice", "threshold": 20},
    {"key": "accuracy", "name": "Accuracy", "description": "Score 90%+ on a medium/hard test.", "type": "test_accuracy", "threshold": 90},
    {"key": "concept_mastery", "name": "Concept Master", "description": "Reach 85% mastery on a concept.", "type": "mastery", "threshold": 85},
    {"key": "comeback", "name": "The Comeback", "description": "Improve your score after a weak attempt.", "type": "improvement", "threshold": 5},
]

DEFAULT_ADMIN_PERMISSIONS = {
    "manage_users": True,
    "manage_classes": True,
    "review_tests": True,
    "view_reports": True,
    "edit_feature_flags": True,
}

DEFAULT_MODEL_META = {
    "active_model": os.environ.get("ICODEX_MODEL_NAME", "llama-3.3-70b"),
    "provider": os.environ.get("ICODEX_MODEL_PROVIDER", "Cerebras"),
    "last_updated_at": os.environ.get("ICODEX_MODEL_UPDATED_AT", ""),
}

DEFAULT_ENVIRONMENT_META = {
    "name": os.environ.get("ICODEX_ENV", "Live"),
    "version": os.environ.get("ICODEX_VERSION", "dev"),
}

HEALTH_SKIP_DB = os.environ.get("ICODEX_SKIP_DB_HEALTH", "").strip().lower() in {"1", "true", "yes", "on"}
DEFAULT_DB_CONNECT_TIMEOUT = int(os.environ.get("ICODEX_DB_CONNECT_TIMEOUT", "5") or 5)
FORCE_FILE_STATE = os.environ.get("ICODEX_FORCE_FILE_STATE", "").strip().lower() in {"1", "true", "yes", "on"}

SUPPORTED_SOURCE_EXTENSIONS = {".pdf", ".docx", ".pptx"}

app = FastAPI(title="ICodex Model")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
if FRONTEND_ASSETS.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_ASSETS), name="frontend-assets")


# -------------------- Storage helpers -------------------- #
_STATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS icodex_state (
    id INTEGER PRIMARY KEY,
    data JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

_ARTIFACTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS icodex_test_artifacts (
    test_id TEXT PRIMARY KEY,
    quiz_json JSONB,
    evidence_json JSONB,
    quiz_pdf BYTEA,
    source_pdf BYTEA,
    source_pdf_filename TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

_USERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS icodex_users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE,
    role TEXT,
    full_name TEXT,
    school TEXT,
    status TEXT,
    last_active_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
)
"""

_DB_POOL = None
_DB_POOL_LOCK = threading.Lock()
_DB_STATE_TABLE_READY = False


def _reset_db_pool() -> None:
    global _DB_POOL, _DB_STATE_TABLE_READY
    with _DB_POOL_LOCK:
        if _DB_POOL is not None:
            try:
                _DB_POOL.closeall()
            except Exception:
                pass
        _DB_POOL = None
        _DB_STATE_TABLE_READY = False


def _get_db_pool():
    global _DB_POOL, _DB_STATE_TABLE_READY
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured.")
    if _DB_POOL is not None and _DB_STATE_TABLE_READY:
        return _DB_POOL

    def _with_timeout(dsn: str) -> str:
        if "connect_timeout" in dsn:
            return dsn
        if "?" in dsn:
            return dsn + f"&connect_timeout={DEFAULT_DB_CONNECT_TIMEOUT}"
        return dsn + f"?connect_timeout={DEFAULT_DB_CONNECT_TIMEOUT}"

    with _DB_POOL_LOCK:
        if _DB_POOL is None:
            try:
                from psycopg2.pool import ThreadedConnectionPool  # type: ignore
            except Exception as exc:  # pragma: no cover
                raise RuntimeError(
                    "DATABASE_URL is set but psycopg2 is not available. "
                    "Install dependencies (psycopg2-binary) or remove DATABASE_URL."
                ) from exc

            maxconn_raw = os.environ.get("ICODEX_DB_POOL_MAX", "5")
            try:
                maxconn = int(maxconn_raw)
            except ValueError:
                maxconn = 5
            maxconn = max(1, min(maxconn, 20))
            _DB_POOL = ThreadedConnectionPool(minconn=1, maxconn=maxconn, dsn=_with_timeout(DATABASE_URL))

        if not _DB_STATE_TABLE_READY:
            conn = _DB_POOL.getconn()
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(_STATE_TABLE_SQL)
                        cur.execute(_ARTIFACTS_TABLE_SQL)
                        # Backward-compatible migration for existing DBs.
                        cur.execute(
                            "ALTER TABLE icodex_test_artifacts ADD COLUMN IF NOT EXISTS evidence_json JSONB"
                        )
                        cur.execute(_USERS_TABLE_SQL)
                _DB_STATE_TABLE_READY = True
            finally:
                _DB_POOL.putconn(conn)

    return _DB_POOL


def load_state() -> Dict[str, Any]:
    base = {
        "users": {},
        "sessions": {},
        "tests": {},
        "assignments": {},
        "classes": {},
        "audit_logs": [],
        "config": {"teacher_can_assign": False},
    }

    if DATABASE_URL and not FORCE_FILE_STATE:
        for attempt in range(2):
            try:
                pool = _get_db_pool()
                conn = pool.getconn()
                try:
                    with conn:
                        with conn.cursor() as cur:
                            cur.execute("SELECT data::text, updated_at FROM icodex_state WHERE id = 1")
                            row = cur.fetchone()
                finally:
                    pool.putconn(conn)

                if not row or not row[0]:
                    # One-time migration helper: if a legacy JSON file exists, seed the DB from it.
                    if STATE_FILE.exists():
                        try:
                            with open(STATE_FILE, "r", encoding="utf-8") as f:
                                data = json.load(f)
                            try:
                                save_state(data)
                            except Exception:
                                pass
                        except Exception:
                            return base
                    else:
                        return base
                else:
                    data = json.loads(row[0])
                    db_updated_at = row[1] if len(row) > 1 else None
                    if STATE_FILE.exists():
                        try:
                            file_mtime = datetime.fromtimestamp(STATE_FILE.stat().st_mtime, tz=timezone.utc)
                            if db_updated_at is not None and db_updated_at.tzinfo is None:
                                db_updated_at = db_updated_at.replace(tzinfo=timezone.utc)
                            if db_updated_at is None or file_mtime > db_updated_at + timedelta(seconds=2):
                                with open(STATE_FILE, "r", encoding="utf-8") as f:
                                    data = json.load(f)
                        except Exception:
                            pass
                break
            except Exception as exc:
                if attempt == 0:
                    _reset_db_pool()
                    continue
                # Fall back to local file if DB read fails.
                if STATE_FILE.exists():
                    try:
                        with open(STATE_FILE, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        break
                    except Exception:
                        return base
                return base
    else:
        if not STATE_FILE.exists():
            return base
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    # Ensure defaults for older state files
    for key, val in base.items():
        data.setdefault(key, val if isinstance(val, dict) else val)
    # Ensure nested config defaults
    data.setdefault("config", {})
    if not isinstance(data["config"], dict):
        data["config"] = {}
    cfg = data["config"]
    cfg.setdefault("teacher_can_assign", False)
    flags = cfg.get("feature_flags") or {}
    if not isinstance(flags, dict):
        flags = {}
    for key, value in DEFAULT_FEATURE_FLAGS.items():
        flags.setdefault(key, value)
    cfg["feature_flags"] = flags

    perms = cfg.get("admin_permissions") or {}
    if not isinstance(perms, dict):
        perms = {}
    for key, value in DEFAULT_ADMIN_PERMISSIONS.items():
        perms.setdefault(key, value)
    cfg["admin_permissions"] = perms

    model_meta = cfg.get("model_meta") or {}
    if not isinstance(model_meta, dict):
        model_meta = {}
    for key, value in DEFAULT_MODEL_META.items():
        model_meta.setdefault(key, value)
    cfg["model_meta"] = model_meta

    env_meta = cfg.get("environment") or {}
    if not isinstance(env_meta, dict):
        env_meta = {}
    for key, value in DEFAULT_ENVIRONMENT_META.items():
        env_meta.setdefault(key, value)
    cfg["environment"] = env_meta

    gam_cfg = cfg.get("gamification") or {}
    if not isinstance(gam_cfg, dict):
        gam_cfg = {}
    for key, value in DEFAULT_GAMIFICATION_CONFIG.items():
        gam_cfg.setdefault(key, value)
    cfg["gamification"] = gam_cfg

    data["config"] = cfg

    data.setdefault("gamification", {})
    gam = data["gamification"]
    if not isinstance(gam, dict):
        gam = {}
    gam.setdefault("xp", {})
    gam.setdefault("events", {})
    gam.setdefault("user_achievements", {})
    gam.setdefault("streaks", {})
    gam.setdefault("quest_progress", {})
    gam.setdefault("quests", {})
    gam.setdefault("leaderboards", {})
    data["gamification"] = gam

    data.setdefault("audit_logs", [])
    if not isinstance(data["audit_logs"], list):
        data["audit_logs"] = []
    return data


def save_state(state: Dict[str, Any]) -> None:
    """
    Persist state atomically to avoid transient JSON corruption while writing.

    We write to a temporary file and then replace the main state file so any
    concurrent readers either see the old valid JSON or the new one, but never
    a half-written file.
    """
    def _sync_users_table(conn, users: Dict[str, Any]) -> None:
        if not users:
            return
        ids = list(users.keys())
        values = [
            (
                u.get("id"),
                u.get("email"),
                u.get("role"),
                u.get("full_name"),
                u.get("school"),
                u.get("status"),
                u.get("last_active_at"),
                u.get("created_at"),
            )
            for u in users.values()
        ]
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO icodex_users (id, email, role, full_name, school, status, last_active_at, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE
                SET email = EXCLUDED.email,
                    role = EXCLUDED.role,
                    full_name = EXCLUDED.full_name,
                    school = EXCLUDED.school,
                    status = EXCLUDED.status,
                    last_active_at = EXCLUDED.last_active_at,
                    created_at = COALESCE(icodex_users.created_at, EXCLUDED.created_at)
                """,
                values,
            )
            cur.execute("DELETE FROM icodex_users WHERE id <> ALL(%s)", (ids,))

    if DATABASE_URL:
        payload = json.dumps(state, ensure_ascii=False)
        for attempt in range(2):
            try:
                pool = _get_db_pool()
                conn = pool.getconn()
                try:
                    with conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                """
                                INSERT INTO icodex_state (id, data)
                                VALUES (1, %s::jsonb)
                                ON CONFLICT (id) DO UPDATE
                                SET data = EXCLUDED.data, updated_at = now()
                                """,
                                (payload,),
                            )
                        _sync_users_table(conn, state.get("users") or {})
                finally:
                    pool.putconn(conn)
                return
            except Exception as exc:
                if attempt == 0:
                    _reset_db_pool()
                    continue
                print(f"Warning: Failed to write state to DATABASE_URL: {exc}. Falling back to file state.")
                break

    tmp_path = STATE_FILE.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp_path, STATE_FILE)


def _db_upsert_test_artifacts(
    test_id: str,
    *,
    quiz_json: Optional[Dict[str, Any]] = None,
    evidence_json: Optional[Dict[str, Any]] = None,
    quiz_pdf: Optional[bytes] = None,
    source_pdf: Optional[bytes] = None,
    source_pdf_filename: Optional[str] = None,
) -> None:
    if not DATABASE_URL:
        return

    payload_json = json.dumps(quiz_json, ensure_ascii=False) if quiz_json is not None else None
    evidence_payload = json.dumps(evidence_json, ensure_ascii=False) if evidence_json is not None else None

    try:
        from psycopg2 import Binary  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("psycopg2 is required when DATABASE_URL is set.") from exc

    pool = _get_db_pool()
    conn = pool.getconn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO icodex_test_artifacts (
                        test_id, quiz_json, evidence_json, quiz_pdf, source_pdf, source_pdf_filename
                    )
                    VALUES (%s, %s::jsonb, %s::jsonb, %s, %s, %s)
                    ON CONFLICT (test_id) DO UPDATE
                    SET quiz_json = COALESCE(EXCLUDED.quiz_json, icodex_test_artifacts.quiz_json),
                        evidence_json = COALESCE(EXCLUDED.evidence_json, icodex_test_artifacts.evidence_json),
                        quiz_pdf = COALESCE(EXCLUDED.quiz_pdf, icodex_test_artifacts.quiz_pdf),
                        source_pdf = COALESCE(EXCLUDED.source_pdf, icodex_test_artifacts.source_pdf),
                        source_pdf_filename = COALESCE(EXCLUDED.source_pdf_filename, icodex_test_artifacts.source_pdf_filename),
                        updated_at = now()
                    """,
                    (
                        str(test_id),
                        payload_json,
                        evidence_payload,
                        Binary(quiz_pdf) if quiz_pdf is not None else None,
                        Binary(source_pdf) if source_pdf is not None else None,
                        source_pdf_filename,
                    ),
                )
    finally:
        pool.putconn(conn)


def _db_fetch_test_artifacts(test_id: str) -> Dict[str, Any]:
    if not DATABASE_URL:
        return {}

    pool = _get_db_pool()
    conn = pool.getconn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        quiz_json::text,
                        evidence_json::text,
                        quiz_pdf,
                        source_pdf,
                        source_pdf_filename
                    FROM icodex_test_artifacts
                    WHERE test_id = %s
                    """,
                    (str(test_id),),
                )
                row = cur.fetchone()
    finally:
        pool.putconn(conn)

    if not row:
        return {}

    quiz_json_raw, evidence_json_raw, quiz_pdf_raw, source_pdf_raw, source_pdf_filename = row

    quiz_json = None
    if quiz_json_raw:
        try:
            quiz_json = json.loads(quiz_json_raw)
        except Exception:
            quiz_json = None

    evidence_json = None
    if evidence_json_raw:
        try:
            evidence_json = json.loads(evidence_json_raw)
        except Exception:
            evidence_json = None

    def to_bytes(value: Any) -> Optional[bytes]:
        if value is None:
            return None
        if isinstance(value, (bytes, bytearray)):
            return bytes(value)
        if isinstance(value, memoryview):
            return value.tobytes()
        try:
            return bytes(value)
        except Exception:
            return None

    return {
        "quiz_json": quiz_json,
        "evidence_json": evidence_json,
        "quiz_pdf": to_bytes(quiz_pdf_raw),
        "source_pdf": to_bytes(source_pdf_raw),
        "source_pdf_filename": source_pdf_filename,
    }


def _db_delete_test_artifacts(test_id: str) -> None:
    if not DATABASE_URL:
        return

    pool = _get_db_pool()
    conn = pool.getconn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM icodex_test_artifacts WHERE test_id = %s", (str(test_id),))
    finally:
        pool.putconn(conn)


def iso_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


_FILENAME_FORBIDDEN = '<>:"/\\\\|?*'


def sanitize_filename(value: str, default: str = "document") -> str:
    name = (value or "").strip()
    if not name:
        return default

    name = "".join("_" if ch in _FILENAME_FORBIDDEN else ch for ch in name)
    name = re.sub(r"\\s+", " ", name).strip().rstrip(". ")
    name = name[:80].strip().rstrip(". ")
    return name or default


def parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        val = value
        if val.endswith("Z"):
            val = val[:-1] + "+00:00"
        return datetime.fromisoformat(val)
    except Exception:
        return None


def infer_test_created_at(test: Dict[str, Any]) -> Optional[str]:
    # Prefer explicit timestamps when present
    created_at = test.get("created_at") or test.get("createdAt")
    if isinstance(created_at, str) and created_at.strip():
        return created_at

    # Infer from on-disk PDF/job directory timestamps
    job_id = test.get("job_id")
    if not job_id:
        return None
    job_dir = DATA_DIR / str(job_id)
    if not job_dir.exists():
        return None

    pdfs = list(job_dir.glob("*.pdf"))
    if not pdfs:
        return None
    latest_mtime = max(p.stat().st_mtime for p in pdfs)
    return datetime.fromtimestamp(latest_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def decorate_test_for_response(test: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    t = dict(test)
    owner = state.get("users", {}).get(t.get("owner_id") or "", {}) or {}
    t["ownerName"] = owner.get("full_name") or owner.get("fullName") or owner.get("email") or "Unknown"

    created_at = infer_test_created_at(t)
    if created_at and not t.get("created_at"):
        t["created_at"] = created_at

    # Optional alias for frontends that use questionLimit
    if "questionLimit" not in t and t.get("limit") is not None:
        t["questionLimit"] = t.get("limit")
    quality = t.get("quality")
    if quality is None:
        try:
            quiz = _get_test_quiz(t.get("id") or "", state)
            quality = _compute_test_quality(quiz)
        except Exception:
            quality = None
    t["quality"] = quality
    t["review"] = _build_test_review(t, quality)
    return t


def decorate_user_for_response(
    user: Dict[str, Any],
    state: Dict[str, Any],
    risk_lookup: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    u = dict(user)
    u.setdefault("status", "active")
    u.setdefault("created_at", "")
    u.setdefault("last_login_at", "")
    u.setdefault("last_active_at", "")
    if u.get("role") == "student":
        if risk_lookup is None:
            risk_lookup = _build_student_risk_lookup(state)
        u["risk"] = risk_lookup.get(u.get("id"), None)
    else:
        u["risk"] = None
    return u


def ensure_default_admin() -> None:
    """Guarantee a baseline admin account exists for management tasks."""
    state = load_state()
    if any(u.get("role") == "admin" for u in state.get("users", {}).values()):
        return
    admin_id = uuid.uuid4().hex
    state["users"][admin_id] = {
        "id": admin_id,
        "full_name": "ICodex Admin",
        "email": "admin@icodex.com",
        "password": "admin",
        "role": "admin",
        "status": "active",
        "school": "",
        "country": "",
        "classes": [],
        "teachers": [],
        "practice_tests": [],
        "created_at": iso_utc_now(),
        "last_login_at": "",
        "last_active_at": "",
        "learning_preferences": {
            "daily_goal_minutes": 15,
            "preferred_difficulty": "medium",
            "focus_topics": [],
        },
    }
    save_state(state)

# Ensure an admin exists at import time
ensure_default_admin()


def get_session_user(request: Request) -> Optional[Dict[str, Any]]:
    state = load_state()
    session_id = request.cookies.get("session_id")
    if not session_id:
        return None
    session = state["sessions"].get(session_id)
    if not session:
        return None
    user = state["users"].get(session["user_id"])
    return user


def create_session(response: JSONResponse, user_id: str, state: Dict[str, Any]) -> None:
    now = iso_utc_now()
    session_id = uuid.uuid4().hex
    state["sessions"][session_id] = {"user_id": user_id, "created_at": now}
    user = state.get("users", {}).get(user_id)
    if isinstance(user, dict):
        if user.get("status") == "invited":
            user["status"] = "active"
        user.setdefault("status", "active")
        user["last_login_at"] = now
        user["last_active_at"] = now
        state["users"][user_id] = user
    save_state(state)
    response.set_cookie(
        "session_id",
        session_id,
        httponly=True,
        samesite="lax",
        path="/",
    )


def append_test_log(test_id: str, message: str) -> None:
    state = load_state()
    test = state["tests"].get(test_id)
    if not test:
        return
    test.setdefault("log", []).append(message)
    state["tests"][test_id] = test
    save_state(state)


def append_audit_log(
    state: Dict[str, Any],
    *,
    actor_id: Optional[str],
    action: str,
    target_type: str,
    target_id: Optional[str],
    details: Optional[Dict[str, Any]] = None,
) -> None:
    entry = {
        "id": uuid.uuid4().hex,
        "actor_id": actor_id,
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "details": details or {},
        "created_at": iso_utc_now(),
    }
    logs = state.setdefault("audit_logs", [])
    if not isinstance(logs, list):
        logs = []
        state["audit_logs"] = logs
    logs.insert(0, entry)
    if len(logs) > 500:
        del logs[500:]


def update_model_meta(state: Dict[str, Any], model: str) -> None:
    cfg = state.get("config") or {}
    if not isinstance(cfg, dict):
        cfg = {}
    model_meta = cfg.get("model_meta") or {}
    if not isinstance(model_meta, dict):
        model_meta = {}
    model_meta["active_model"] = model
    model_meta["last_updated_at"] = iso_utc_now()
    cfg["model_meta"] = model_meta
    state["config"] = cfg


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot load module at {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


def _gather_source_files_for_test(test: Dict[str, Any]) -> Tuple[List[Path], Path]:
    """Return the job directory and existing source files for a test."""
    job_id = test.get("job_id")
    if not job_id:
        raise FileNotFoundError("Missing job_id for test.")
    job_dir = DATA_DIR / str(job_id)
    candidates: List[Path] = []
    if job_dir.exists():
        candidates = sorted(
            [p for p in job_dir.iterdir() if p.suffix.lower() in SUPPORTED_SOURCE_EXTENSIONS and p.is_file()],
            key=lambda p: p.name,
        )
    if candidates:
        return candidates, job_dir
    # Fallback: use legacy paths if available
    raw_text = test.get("paths", {}).get("raw_text")
    if raw_text:
        txt = Path(str(raw_text))
        if txt.exists():
            parent = txt.parent if txt.parent.exists() else job_dir
            return [txt], parent
    raise FileNotFoundError("No source files found for test.")


def require_user(request: Request) -> Dict[str, Any]:
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    if user.get("status") == "suspended":
        raise HTTPException(status_code=403, detail="Account suspended.")
    return user


def require_role(user: Dict[str, Any], role: str):
    if user.get("role") != role:
        raise HTTPException(status_code=403, detail="Forbidden")


# -------------------- Pipeline helpers -------------------- #
def derive_paths(job_dir: Path, stem: Optional[str] = None) -> Dict[str, Path]:
    base = (stem or job_dir.name).strip().replace(" ", "_")
    merged_raw = job_dir / f"{base}_merged_raw.txt"
    merged_cleaned = job_dir / f"{base}_merged_cleaned.txt"
    return {
        "raw_text": merged_raw,
        "cleaned_text": merged_cleaned,
        "text": merged_cleaned,
        "chunks": job_dir / f"{base}_extracted_chunks.json",
        "structure": job_dir / f"{base}_extracted_chunks_structure.json",
        "quiz_json": job_dir / f"{base}_extracted_chunks_structure_quiz.json",
        "quiz_pdf": job_dir / f"{base}_extracted_chunks_structure_quiz.pdf",
        # Sidecar evidence map (must NOT include "_quiz" to avoid being picked up by quiz JSON globbing).
        "evidence_json": job_dir / f"{base}_extracted_chunks_structure_evidence.json",
    }


def run_pipeline(
    job_dir: Path,
    source_files: List[Path],
    api_key: str,
    model: str,
    include_difficulty: bool = True,
    question_limit: int = 100,
    metrics_out: Optional[Dict[str, Any]] = None,
    log_fn=None,
) -> Dict[str, str]:
    if not source_files:
        raise ValueError("run_pipeline requires at least one source file.")
    env = os.environ.copy()
    env["CEREBRAS_API_KEY"] = api_key
    env["PYTHONIOENCODING"] = "utf-8"
    path_map = derive_paths(job_dir)
    paths = {key: str(value) for key, value in path_map.items()}
    state = create_pipeline_state(
        job_id=job_dir.name,
        job_dir=str(job_dir),
        source_files=[str(p) for p in source_files],
        api_key=api_key,
        model=model,
        include_difficulty=include_difficulty,
        question_limit=question_limit,
        raw_bank_questions=DEFAULT_RAW_BANK_QUESTIONS,
        paths=paths,
        env=env,
        cwd=str(REPO_ROOT),
    )
    try:
        final_state = run_pipeline_graph(state, log_fn=log_fn)
    except PipelineStepError as exc:
        failed_state = exc.state
        if not isinstance(failed_state, PipelineState):
            failed_state = PipelineState(**failed_state)
        if metrics_out is not None:
            metrics_out.update(model_dump_safe(failed_state.metrics))
        raise RuntimeError(str(exc)) from exc
    except Exception:
        if metrics_out is not None:
            metrics_out.update(model_dump_safe(state.metrics))
        raise
    if metrics_out is not None:
        metrics_out.update(model_dump_safe(final_state.metrics))
    return dict(final_state.paths)


def _persist_test_artifacts_from_paths(
    test_id: str,
    *,
    paths: Dict[str, str],
    source_pdf_path: Optional[Path] = None,
) -> None:
    """
    Persist quiz artifacts to the DB so they survive ephemeral deployments (e.g. Render).

    - Always stores quiz JSON (JSONB) when available.
    - Stores rendered quiz PDF (BYTEA) when available.
    - Optionally stores the original uploaded PDF when `ICODEX_STORE_SOURCE_PDF` is enabled.
    """
    if not DATABASE_URL:
        return

    quiz_json = None
    evidence_json = None
    quiz_pdf_bytes = None

    quiz_json_path_raw = (paths or {}).get("quiz_json")
    evidence_path_raw = (paths or {}).get("evidence_json")
    quiz_pdf_path_raw = (paths or {}).get("quiz_pdf")

    if quiz_json_path_raw:
        quiz_json_path = Path(str(quiz_json_path_raw))
        if quiz_json_path.exists():
            try:
                with open(quiz_json_path, "r", encoding="utf-8") as f:
                    quiz_json = json.load(f)
            except Exception:
                quiz_json = None

    if evidence_path_raw:
        evidence_path = Path(str(evidence_path_raw))
        if evidence_path.exists():
            try:
                with open(evidence_path, "r", encoding="utf-8") as f:
                    evidence_json = json.load(f)
            except Exception:
                evidence_json = None

    if quiz_pdf_path_raw:
        quiz_pdf_path = Path(str(quiz_pdf_path_raw))
        if quiz_pdf_path.exists():
            try:
                quiz_pdf_bytes = quiz_pdf_path.read_bytes()
            except Exception:
                quiz_pdf_bytes = None

    store_source_pdf = os.environ.get("ICODEX_STORE_SOURCE_PDF", "").strip().lower() in {"1", "true", "yes", "on"}
    source_pdf_bytes = None
    source_pdf_filename = None
    if store_source_pdf and source_pdf_path and source_pdf_path.exists():
        try:
            source_pdf_bytes = source_pdf_path.read_bytes()
            source_pdf_filename = source_pdf_path.name
        except Exception:
            source_pdf_bytes = None
            source_pdf_filename = None

    if quiz_json is None and evidence_json is None and quiz_pdf_bytes is None and source_pdf_bytes is None:
        return

    _db_upsert_test_artifacts(
        test_id,
        quiz_json=quiz_json,
        evidence_json=evidence_json,
        quiz_pdf=quiz_pdf_bytes,
        source_pdf=source_pdf_bytes,
        source_pdf_filename=source_pdf_filename,
    )


def _get_test_quiz(test_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
    """Load quiz JSON for a given test id with clear errors."""
    test = state["tests"].get(test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Test not found.")
    quiz_path = (_resolve_quiz_paths(test) or {}).get("quiz_json")
    if quiz_path and quiz_path.exists():
        try:
            with open(quiz_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:  # pragma: no cover
            raise HTTPException(status_code=500, detail=f"Unable to read quiz JSON: {exc}")

    if DATABASE_URL:
        artifacts = _db_fetch_test_artifacts(test_id)
        quiz_json = artifacts.get("quiz_json")
        if isinstance(quiz_json, dict):
            return quiz_json

    if not quiz_path:
        raise HTTPException(status_code=404, detail="Quiz JSON path missing.")
    raise HTTPException(status_code=404, detail="Quiz JSON not found.")


def _flatten_quiz_questions(quiz: Any) -> List[Dict[str, Any]]:
    flat: List[Dict[str, Any]] = []

    def walk(node, trail):
        if isinstance(node, dict):
            questions = node.get("questions")
            if questions:
                for q in questions:
                    flat.append(
                        {
                            "question": q.get("question", ""),
                            "options": q.get("options", []),
                            "correct_answer": q.get("correct_answer", ""),
                            "section": "/".join([s for s in trail if s]),
                        }
                    )
            for k, v in node.items():
                if k not in {"questions"}:
                    title = node.get("title") or node.get("name")
                    next_trail = trail + [title] if title else trail
                    walk(v, next_trail)
        elif isinstance(node, list):
            for item in node:
                walk(item, trail)

    walk(quiz, [])
    return flat


def _test_has_questions(test_id: str, state: Dict[str, Any]) -> bool:
    try:
        quiz = _get_test_quiz(test_id, state)
    except HTTPException:
        return False
    flat = _flatten_quiz_questions(quiz)
    if not flat:
        if test_id in state["tests"]:
            state["tests"][test_id]["status"] = "failed"
            state["tests"][test_id]["error"] = "No questions were generated for this quiz."
            save_state(state)
        return False
    return True


def _summarize_mastery_from_session(session: Optional[Dict[str, Any]]) -> Tuple[List[str], List[str]]:
    strengths: List[str] = []
    weaknesses: List[str] = []
    if not session:
        return strengths, weaknesses
    answered = session.get("answered", [])
    topic_scores: Dict[str, List[float]] = {}
    for entry in answered:
        mastery = entry.get("mastery") or {}
        score = mastery.get("mastery_score")
        if score is None:
            continue
        try:
            score_val = float(score)
        except (TypeError, ValueError):
            continue
        topic = mastery.get("position") or entry.get("evaluation", {}).get("position") or "General"
        topic_scores.setdefault(topic, []).append(score_val)
    for topic, vals in topic_scores.items():
        avg = sum(vals) / max(len(vals), 1)
        if avg >= 80.0:
            strengths.append(topic)
        elif avg <= 60.0:
            weaknesses.append(topic)
    return strengths[:5], weaknesses[:5]


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_concept_label(position: Optional[str]) -> str:
    if not position:
        return "General"
    segments = [seg.strip() for seg in re.split(r"[/>]+", position) if seg.strip()]
    if not segments:
        return "General"
    if len(segments) >= 2:
        return " / ".join(segments[-2:])
    return segments[-1]


def _entry_timestamp(entry: Dict[str, Any], session: Optional[Dict[str, Any]]) -> Optional[str]:
    for key in ("answered_at", "answeredAt"):
        value = entry.get(key)
        if isinstance(value, str) and value:
            return value
    if session:
        for key in ("completed_at", "started_at"):
            value = session.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def _extract_entry_metrics(entry: Dict[str, Any]) -> Dict[str, Any]:
    evaln = entry.get("evaluation") or {}
    metrics = evaln.get("metrics") or {}
    mastery = entry.get("mastery") or {}
    mastery_score = _to_float(mastery.get("mastery_score"))
    if mastery_score is None:
        normalized_accuracy = _to_float(metrics.get("normalized_accuracy"))
        if normalized_accuracy is not None:
            mastery_score = normalized_accuracy * 100.0
    return {
        "mastery_score": mastery_score,
        "is_correct": bool(metrics.get("is_correct", False)),
        "confidence": _to_float(metrics.get("confidence")),
        "time_ratio": _to_float(metrics.get("time_ratio")),
        "similarity": _to_float(metrics.get("text_similarity")),
        "position": mastery.get("position") or evaln.get("position") or "",
    }


def _iter_answer_events(state: Dict[str, Any], include_practice: bool = True) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for assignment_id, assignment in (state.get("assignments") or {}).items():
        test_id = assignment.get("test_id")
        class_id = assignment.get("class_id")
        sessions = assignment.get("sessions") or {}
        if not isinstance(sessions, dict):
            continue
        for student_id, session in sessions.items():
            for entry in session.get("answered", []) if isinstance(session, dict) else []:
                events.append(
                    {
                        "assignment_id": assignment_id,
                        "test_id": test_id,
                        "class_id": class_id,
                        "student_id": student_id,
                        "entry": entry,
                        "session": session,
                        "kind": "assignment",
                    }
                )

    if include_practice:
        for student_id, tests in (state.get("practice_results") or {}).items():
            for test_id, session in (tests or {}).items():
                if not isinstance(session, dict):
                    continue
                for entry in session.get("answered", []):
                    events.append(
                        {
                            "assignment_id": None,
                            "test_id": test_id,
                            "class_id": None,
                            "student_id": student_id,
                            "entry": entry,
                            "session": session,
                            "kind": "practice",
                        }
                    )
    return events


def _build_student_risk_lookup(state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    stats: Dict[str, Dict[str, float]] = {}
    for event in _iter_answer_events(state, include_practice=True):
        student_id = event.get("student_id")
        entry = event.get("entry") or {}
        metrics = _extract_entry_metrics(entry)
        mastery_score = metrics.get("mastery_score")
        if mastery_score is None or student_id is None:
            continue
        row = stats.setdefault(
            student_id,
            {"mastery_sum": 0.0, "count": 0.0, "correct": 0.0, "confidence_sum": 0.0, "confidence_count": 0.0},
        )
        row["mastery_sum"] += float(mastery_score)
        row["count"] += 1.0
        if metrics.get("is_correct"):
            row["correct"] += 1.0
        confidence = metrics.get("confidence")
        if confidence is not None:
            row["confidence_sum"] += confidence
            row["confidence_count"] += 1.0

    risk_lookup: Dict[str, Dict[str, Any]] = {}
    for student_id, row in stats.items():
        count = row.get("count", 0.0) or 0.0
        if count <= 0:
            continue
        avg_mastery = row["mastery_sum"] / count
        accuracy = row.get("correct", 0.0) / count
        confidence = None
        if row.get("confidence_count"):
            confidence = row["confidence_sum"] / row["confidence_count"]
        if avg_mastery < 60.0:
            label = "high"
        elif avg_mastery < 75.0:
            label = "medium"
        else:
            label = "low"
        risk_lookup[student_id] = {
            "score": round(100.0 - avg_mastery, 1),
            "label": label,
            "avg_mastery": round(avg_mastery, 1),
            "accuracy": round(accuracy * 100.0, 1),
            "confidence": round(confidence, 2) if confidence is not None else None,
            "attempts": int(count),
        }
    return risk_lookup


def _get_student_events(state: Dict[str, Any], student_id: str, include_practice: bool = True) -> List[Dict[str, Any]]:
    return [e for e in _iter_answer_events(state, include_practice=include_practice) if e.get("student_id") == student_id]


def _build_student_concept_stats(state: Dict[str, Any], student_id: str) -> Dict[str, Any]:
    events = _get_student_events(state, student_id, include_practice=True)
    concept_stats: Dict[str, Dict[str, Any]] = {}
    mastery_scores: List[float] = []
    confidence_scores: List[float] = []
    last_active_at = None

    for event in events:
        entry = event.get("entry") or {}
        session = event.get("session") or {}
        metrics = _extract_entry_metrics(entry)
        mastery_score = metrics.get("mastery_score")
        confidence = metrics.get("confidence")
        concept = _normalize_concept_label(metrics.get("position"))
        timestamp = _entry_timestamp(entry, session)
        dt = parse_iso_datetime(timestamp) if timestamp else None
        if dt and (last_active_at is None or dt > last_active_at):
            last_active_at = dt

        row = concept_stats.setdefault(
            concept,
            {"mastery_sum": 0.0, "count": 0, "correct": 0, "confidence_sum": 0.0, "confidence_count": 0},
        )
        if mastery_score is not None:
            row["mastery_sum"] += float(mastery_score)
            row["count"] += 1
            mastery_scores.append(float(mastery_score))
        if metrics.get("is_correct"):
            row["correct"] += 1
        if confidence is not None:
            row["confidence_sum"] += float(confidence)
            row["confidence_count"] += 1
            confidence_scores.append(float(confidence))

    per_concept = []
    for concept, row in concept_stats.items():
        count = row.get("count", 0) or 0
        if count == 0:
            continue
        avg_mastery = row["mastery_sum"] / count
        accuracy = row["correct"] / count
        avg_confidence = (
            row["confidence_sum"] / row["confidence_count"] if row.get("confidence_count") else None
        )
        per_concept.append(
            {
                "concept": concept,
                "avg_mastery": round(avg_mastery, 1),
                "accuracy": round(accuracy * 100.0, 1),
                "confidence": round(avg_confidence, 2) if avg_confidence is not None else None,
                "attempts": int(count),
            }
        )

    per_concept.sort(key=lambda row: row["avg_mastery"])
    overall_mastery = round(sum(mastery_scores) / len(mastery_scores), 1) if mastery_scores else None
    overall_confidence = round(sum(confidence_scores) / len(confidence_scores), 2) if confidence_scores else None

    return {
        "per_concept": per_concept,
        "overall_mastery": overall_mastery,
        "overall_confidence": overall_confidence,
        "last_active_at": last_active_at.isoformat().replace("+00:00", "Z") if last_active_at else None,
    }


def _build_student_progress(state: Dict[str, Any], student_id: str, days: int = 7) -> List[Dict[str, Any]]:
    events = _get_student_events(state, student_id, include_practice=True)
    now = datetime.now(timezone.utc)
    day_buckets: Dict[str, List[float]] = {}

    for event in events:
        entry = event.get("entry") or {}
        session = event.get("session") or {}
        metrics = _extract_entry_metrics(entry)
        mastery_score = metrics.get("mastery_score")
        if mastery_score is None:
            continue
        timestamp = _entry_timestamp(entry, session)
        dt = parse_iso_datetime(timestamp) if timestamp else None
        if not dt:
            continue
        if (now - dt).days >= days:
            continue
        day_key = dt.date().isoformat()
        day_buckets.setdefault(day_key, []).append(float(mastery_score))

    progress = []
    for offset in range(days - 1, -1, -1):
        day = (now - timedelta(days=offset)).date().isoformat()
        scores = day_buckets.get(day, [])
        avg = round(sum(scores) / len(scores), 1) if scores else None
        progress.append({"date": day, "mastery": avg})
    return progress


def _build_student_streak(state: Dict[str, Any], student_id: str) -> Dict[str, Any]:
    events = _get_student_events(state, student_id, include_practice=True)
    active_dates = set()
    for event in events:
        entry = event.get("entry") or {}
        session = event.get("session") or {}
        timestamp = _entry_timestamp(entry, session)
        dt = parse_iso_datetime(timestamp) if timestamp else None
        if dt:
            active_dates.add(dt.date().isoformat())

    today = datetime.now(timezone.utc).date()
    streak = 0
    for offset in range(0, 365):
        day = (today - timedelta(days=offset)).isoformat()
        if day in active_dates:
            streak += 1
        else:
            break
    return {
        "days": streak,
        "last_active_at": max(active_dates) if active_dates else None,
    }


def _find_student_continue_item(state: Dict[str, Any], student_id: str) -> Optional[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for aid, assignment in (state.get("assignments") or {}).items():
        test_id = assignment.get("test_id")
        test = state.get("tests", {}).get(test_id) if test_id else None
        if not test:
            continue
        class_id = assignment.get("class_id")
        cls = state.get("classes", {}).get(class_id) if class_id else None
        in_class = bool(cls and student_id in (cls.get("students") or []))
        in_students_list = student_id in (assignment.get("students") or [])
        if not (in_class or in_students_list):
            continue
        status_map = assignment.get("status") if isinstance(assignment.get("status"), dict) else {}
        status = (status_map.get(student_id) or "pending").lower()
        if status == "completed":
            continue
        session = (assignment.get("sessions") or {}).get(student_id) if isinstance(assignment.get("sessions"), dict) else {}
        answered = len((session or {}).get("answered") or []) if session else 0
        limit = int((session or {}).get("limit") or test.get("limit") or 0)
        progress = int(round(100.0 * answered / limit)) if limit else 0
        last = session.get("last_answered_at") or session.get("current_started_at") or session.get("started_at")
        candidates.append(
            {
                "type": "assignment",
                "assignment_id": aid,
                "test_id": test_id,
                "title": test.get("title") or "Assigned Test",
                "progress": progress,
                "status": status,
                "last_active_at": last,
            }
        )

    for key, session in (state.get("practice_sessions") or {}).items():
        if not isinstance(session, dict):
            continue
        if not key.startswith(f"{student_id}:"):
            continue
        test_id = key.split(":", 1)[1]
        test = state.get("tests", {}).get(test_id, {})
        answered = len(session.get("answered") or [])
        limit = int(session.get("limit") or test.get("limit") or 0)
        progress = int(round(100.0 * answered / limit)) if limit else 0
        last = session.get("last_answered_at") or session.get("current_started_at") or session.get("started_at")
        candidates.append(
            {
                "type": "practice",
                "assignment_id": None,
                "test_id": test_id,
                "title": test.get("title") or "Practice Quiz",
                "progress": progress,
                "status": "in_progress",
                "last_active_at": last,
            }
        )

    if not candidates:
        return None

    def _candidate_key(item: Dict[str, Any]) -> float:
        dt = parse_iso_datetime(item.get("last_active_at"))
        return dt.timestamp() if dt else 0.0

    candidates.sort(key=_candidate_key, reverse=True)
    return candidates[0]


def _build_student_plan(state: Dict[str, Any], student_id: str) -> List[Dict[str, Any]]:
    plan: List[Dict[str, Any]] = []
    concept_stats = _build_student_concept_stats(state, student_id)
    per_concept = concept_stats.get("per_concept") or []
    continue_item = _find_student_continue_item(state, student_id)
    streak = _build_student_streak(state, student_id)
    user = state.get("users", {}).get(student_id, {}) if isinstance(state.get("users"), dict) else {}
    prefs = user.get("learning_preferences") if isinstance(user.get("learning_preferences"), dict) else {}
    try:
        goal_minutes = max(5, min(60, int(prefs.get("daily_goal_minutes") or 15)))
    except (TypeError, ValueError):
        goal_minutes = 15
    focus_topics = prefs.get("focus_topics") if isinstance(prefs.get("focus_topics"), list) else []
    focus_topics = [str(t).strip() for t in focus_topics if str(t).strip()]

    if continue_item:
        label = f"Continue {continue_item.get('title')} ({max(1, 10 - int(continue_item.get('progress') or 0) // 10)} mins)"
        cta = (
            f"resume_assignment:{continue_item['assignment_id']}"
            if continue_item.get("type") == "assignment"
            else f"resume_practice:{continue_item['test_id']}"
        )
        plan.append(
            {
                "id": "resume",
                "label": label,
                "reason": "Pick up where you left off.",
                "cta": cta,
            }
        )

    weak_concepts = [c for c in per_concept if c.get("avg_mastery") is not None]
    weak_concepts.sort(key=lambda row: row["avg_mastery"])
    if weak_concepts:
        concept = weak_concepts[0]
        if focus_topics:
            for candidate in weak_concepts:
                if any(ft.lower() in str(candidate.get("concept", "")).lower() for ft in focus_topics):
                    concept = candidate
                    break
        plan.append(
            {
                "id": "weak_concept",
                "label": f"Practice {concept['concept']} ({goal_minutes} mins)",
                "reason": f"{concept['avg_mastery']}% mastery this week.",
                "cta": f"practice_concept:{concept['concept']}",
            }
        )
    elif focus_topics:
        plan.append(
            {
                "id": "focus_topic",
                "label": f"Practice {focus_topics[0]} ({goal_minutes} mins)",
                "reason": "Based on your learning preferences.",
                "cta": f"practice_concept:{focus_topics[0]}",
            }
        )

    if streak.get("days", 0) == 0:
        plan.append(
            {
                "id": "warmup",
                "label": "Quick warm-up (5 mins)",
                "reason": "Start a new streak today.",
                "cta": "start_practice",
            }
        )

    return plan[:3]


def _calculate_level(xp_total: float) -> int:
    return max(1, int(xp_total // 100) + 1)


def _get_gamification_config(state: Dict[str, Any]) -> Dict[str, Any]:
    cfg = state.get("config") or {}
    gam_cfg = cfg.get("gamification") or {}
    if not isinstance(gam_cfg, dict):
        gam_cfg = {}
    return gam_cfg


def _award_xp(state: Dict[str, Any], user_id: str, event_key: str, xp_amount: float, metadata: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    gam = state.setdefault("gamification", {})
    events = gam.setdefault("events", {})
    if event_key in events:
        return None
    cfg = _get_gamification_config(state)
    if not cfg.get("enabled", True):
        return None
    gam["events"] = events

    today = metadata.get("date") if isinstance(metadata, dict) and metadata.get("date") else iso_utc_now()
    date_key = today[:10]
    user_xp = gam.setdefault("xp", {}).setdefault(user_id, {"xp_total": 0.0, "level": 1, "last_updated": "", "daily_questions": {}, "xp_history": []})
    daily = user_xp.setdefault("daily_questions", {})
    daily_count = daily.get(date_key, 0)
    cap = int(cfg.get("daily_question_cap", 60) or 60)
    if daily_count >= cap:
        xp_amount *= 0.6
    daily[date_key] = daily_count + 1
    events[event_key] = {
        "user_id": user_id,
        "event_key": event_key,
        "xp_awarded": xp_amount,
        "metadata": metadata or {},
        "created_at": iso_utc_now(),
    }
    user_xp["xp_total"] = user_xp.get("xp_total", 0.0) + xp_amount
    user_xp["level"] = _calculate_level(user_xp["xp_total"])
    user_xp["last_updated"] = iso_utc_now()
    history = user_xp.setdefault("xp_history", [])
    history.append({"xp": xp_amount, "date": iso_utc_now(), "event": event_key})
    gam.setdefault("xp", {})[user_id] = user_xp
    completed_quests = []
    if metadata:
        completed = _update_quests_progress(state, user_id, metadata)
        for quest_id in completed:
            quest = gam.setdefault("quests", {}).get(quest_id)
            if quest and quest.get("reward_xp"):
                reward_event = f"questComplete:{quest_id}:{user_id}"
                reward_metadata = {
                    "quest_id": quest_id,
                    "reward": quest.get("reward_xp"),
                    "date": today,
                    "source_type": "quest_complete",
                    "event_type": "quest_reward",
                }
                reward = _award_xp(state, user_id, reward_event, float(quest["reward_xp"]), metadata=reward_metadata)
                if reward:
                    completed_quests.append(quest_id)
    return {"xp_total": user_xp["xp_total"], "level": user_xp["level"], "xp_awarded": xp_amount}
    return {"xp_total": user_xp["xp_total"], "level": user_xp["level"], "xp_awarded": xp_amount}


def _update_streak(state: Dict[str, Any], user_id: str, current_date: str) -> Dict[str, Any]:
    gam = state.setdefault("gamification", {})
    streaks = gam.setdefault("streaks", {})
    row = streaks.setdefault(
        user_id,
        {
            "current_streak": 0,
            "longest_streak": 0,
            "last_active_date": None,
            "freeze_tokens": 1,
            "last_freeze_week": None,
        },
    )
    cfg = _get_gamification_config(state)
    today = parse_iso_datetime(current_date) or parse_iso_datetime(iso_utc_now())
    if not today:
        return row
    week = today.isocalendar()[1]
    if row.get("last_freeze_week") != week:
        row["freeze_tokens"] = 1
        row["last_freeze_week"] = week
    last_date = parse_iso_datetime(row.get("last_active_date"))
    if last_date:
        delta = (today.date() - last_date.date()).days
    else:
        delta = 0
    if delta == 0:
        return row
    if delta == 1:
        row["current_streak"] += 1
    elif delta <= 2 and row.get("freeze_tokens", 0) > 0:
        row["freeze_tokens"] = max(0, row.get("freeze_tokens", 0) - 1)
        row["current_streak"] += 1
    else:
        row["current_streak"] = 1
    if row["current_streak"] > row.get("longest_streak", 0):
        row["longest_streak"] = row["current_streak"]
    row["last_active_date"] = today.isoformat().replace("+00:00", "Z")
    return row


def _unlock_achievement(state: Dict[str, Any], user_id: str, achievement_key: str) -> bool:
    gam = state.setdefault("gamification", {})
    achievements = gam.setdefault("user_achievements", {})
    user_unlocks = achievements.setdefault(user_id, [])
    if any(a.get("achievement_id") == achievement_key for a in user_unlocks):
        return False
    user_unlocks.append({"achievement_id": achievement_key, "unlocked_at": iso_utc_now()})
    achievements[user_id] = user_unlocks
    return True


def _evaluate_achievements(state: Dict[str, Any], user_id: str, context: Dict[str, Any]) -> List[str]:
    unlocked = []
    for definition in ACHIEVEMENT_DEFS:
        key = definition["key"]
        already = any(a.get("achievement_id") == key for a in state.get("gamification", {}).get("user_achievements", {}).get(user_id, []))
        if already:
            continue
        if definition["type"] == "streak" and context.get("streak", 0) >= definition["threshold"]:
            if _unlock_achievement(state, user_id, key):
                unlocked.append(key)
        elif definition["type"] == "practice" and context.get("practice_questions", 0) >= definition["threshold"]:
            if _unlock_achievement(state, user_id, key):
                unlocked.append(key)
        elif definition["type"] == "test_accuracy" and context.get("percent", 0) >= definition["threshold"] and context.get("difficulty") in {"medium", "hard"}:
            if _unlock_achievement(state, user_id, key):
                unlocked.append(key)
        elif definition["type"] == "mastery" and context.get("max_mastery", 0) >= definition["threshold"]:
            if _unlock_achievement(state, user_id, key):
                unlocked.append(key)
        elif definition["type"] == "improvement" and context.get("improvement", 0) >= definition["threshold"]:
            if _unlock_achievement(state, user_id, key):
                unlocked.append(key)
    return unlocked


def _match_quest_event(metadata: Dict[str, Any], quest: Dict[str, Any]) -> bool:
    if not metadata:
        return False
    if metadata.get("event_type") == "quest_reward":
        return False
    criteria = quest.get("criteria", {}) or {}
    ctype = criteria.get("type")
    if ctype == "question_count":
        return metadata.get("event_type") == "question"
    if ctype == "concept":
        return metadata.get("concept") == criteria.get("concept")
    return False


def _increment_quest_progress(state: Dict[str, Any], quest_id: str, user_id: str, amount: float = 1.0) -> Optional[Dict[str, Any]]:
    gam = state.setdefault("gamification", {})
    progress_table = gam.setdefault("quest_progress", {})
    user_progress = progress_table.setdefault(quest_id, {})
    row = user_progress.setdefault(user_id, {"progress": 0.0, "completed_at": None})
    row["progress"] += amount
    criteria = gam.get("quests", {}).get(quest_id, {}).get("criteria", {}) or {}
    target = criteria.get("target") or 1
    if row["progress"] >= target and not row.get("completed_at"):
        row["completed_at"] = iso_utc_now()
        progress_table[quest_id][user_id] = row
        return row
    progress_table[quest_id][user_id] = row
    return None


def _update_quests_progress(state: Dict[str, Any], user_id: str, metadata: Dict[str, Any]) -> List[str]:
    gam = state.setdefault("gamification", {})
    quests = gam.setdefault("quests", {})
    completed = []
    for quest_id, quest in quests.items():
        if quest.get("status") == "completed":
            continue
        if quest.get("user_id") and quest["user_id"] != user_id:
            continue
        if quest.get("class_id"):
            cls = state.get("classes", {}).get(quest["class_id"]) or {}
            if user_id not in (cls.get("students") or []):
                continue
        if not _match_quest_event(metadata, quest):
            continue
        progress_complete = _increment_quest_progress(state, quest_id, user_id)
        if progress_complete:
            quest["status"] = "completed"
            gam["quests"][quest_id] = quest
        completed.append(quest_id)
    return completed


def _get_user_class_ids(state: Dict[str, Any], user_id: str) -> List[str]:
    class_ids: List[str] = []
    for cid, cls in (state.get("classes") or {}).items():
        if user_id in (cls.get("students") or []):
            class_ids.append(cid)
    return class_ids


def _get_class_students(state: Dict[str, Any], class_id: str) -> List[str]:
    cls = (state.get("classes") or {}).get(class_id, {})
    students = cls.get("students")
    if not isinstance(students, list):
        return []
    return [sid for sid in students if isinstance(sid, str)]


def _get_class_name(state: Dict[str, Any], class_id: str) -> str:
    cls = (state.get("classes") or {}).get(class_id)
    if not cls:
        return class_id
    return cls.get("name") or cls.get("id") or class_id


def _class_concept_stats(state: Dict[str, Any], class_id: str) -> List[Dict[str, Any]]:
    events = [
        e
        for e in _iter_answer_events(state, include_practice=False)
        if e.get("class_id") == class_id
    ]
    concept_rows: Dict[str, Dict[str, Any]] = {}
    for event in events:
        entry = event.get("entry") or {}
        session = event.get("session")
        metrics = _extract_entry_metrics(entry)
        mastery = _to_float(metrics.get("mastery_score"))
        if mastery is None:
            continue
        concept = _normalize_concept_label(metrics.get("position"))
        row = concept_rows.setdefault(
            concept,
            {"mastery_sum": 0.0, "count": 0, "last_attempt_at": None},
        )
        row["mastery_sum"] += mastery
        row["count"] += 1
        timestamp = _entry_timestamp(entry, session)
        dt = parse_iso_datetime(timestamp) if timestamp else None
        if dt:
            current = row.get("last_attempt_at")
            if not current or dt > current:
                row["last_attempt_at"] = dt

    per_concept = []
    for concept, row in concept_rows.items():
        cnt = row.get("count", 0)
        if cnt == 0:
            continue
        avg = row["mastery_sum"] / cnt
        per_concept.append(
            {
                "concept": concept,
                "avg_mastery": round(avg, 1),
                "attempts": int(cnt),
                "last_attempt_at": row.get("last_attempt_at"),
            }
        )

    per_concept.sort(key=lambda row: row["avg_mastery"])
    return per_concept


def _create_class_quest(
    state: Dict[str, Any],
    *,
    class_id: str,
    title: str,
    description: str,
    criteria: Dict[str, Any],
    reward_xp: float,
    created_by: Optional[str],
    auto: bool = False,
) -> Dict[str, Any]:
    gam = state.setdefault("gamification", {})
    quests = gam.setdefault("quests", {})
    quest_id = uuid.uuid4().hex
    quest = {
        "id": quest_id,
        "class_id": class_id,
        "class_name": _get_class_name(state, class_id),
        "title": title,
        "description": description,
        "criteria": criteria,
        "reward_xp": float(reward_xp),
        "status": "active",
        "created_at": iso_utc_now(),
        "updated_at": iso_utc_now(),
        "created_by": created_by,
        "auto": auto,
    }
    quests[quest_id] = quest
    gam["quests"] = quests
    return quest


def _ensure_auto_quests_for_class(state: Dict[str, Any], class_id: str) -> bool:
    cfg = _get_gamification_config(state)
    if not cfg.get("quests_enabled", True) or not cfg.get("auto_generate_quests", True):
        return False
    students = _get_class_students(state, class_id)
    if not students:
        return False
    concepts = _class_concept_stats(state, class_id)
    if not concepts:
        return False
    gam = state.setdefault("gamification", {})
    quests = gam.setdefault("quests", {})
    auto_target = int(cfg.get("auto_quest_target", 5) or 5)
    reward = float(cfg.get("auto_quest_reward", 30) or 30)
    created_any = False

    for concept in concepts:
        if concept.get("avg_mastery", 100) >= 85.0:
            continue
        if concept.get("attempts", 0) < 3:
            continue
        key = concept["concept"]
        duplicate = next(
            (
                q
                for q in quests.values()
                if q.get("class_id") == class_id
                and q.get("auto")
                and q.get("status") != "completed"
                and (q.get("criteria") or {}).get("concept") == key
            ),
            None,
        )
        if duplicate:
            continue
        title = f"Reinforce {key}"
        description = f"Answer {auto_target} questions on {key} to boost class mastery."
        _create_class_quest(
            state,
            class_id=class_id,
            title=title,
            description=description,
            criteria={"type": "concept", "concept": key, "target": auto_target},
            reward_xp=reward,
            created_by=None,
            auto=True,
        )
        created_any = True
        if created_any and len([q for q in quests.values() if q.get("class_id") == class_id and q.get("auto")]) >= 2:
            break
    return created_any


def _sum_xp_history(entries: List[Dict[str, Any]], start: datetime, end: datetime) -> float:
    total = 0.0
    for entry in entries:
        date_str = entry.get("date")
        dt = parse_iso_datetime(date_str) if isinstance(date_str, str) else None
        if not dt:
            continue
        if start <= dt < end:
            total += float(entry.get("xp", 0.0) or 0.0)
    return total


def _normalize_quest_for_response(state: Dict[str, Any], quest: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    gam = state.get("gamification", {})
    progress_table = (gam.get("quest_progress") or {}).get(quest.get("id"), {})
    progress_entry = progress_table.get(user_id) or {}
    progress = float(progress_entry.get("progress", 0) or 0)
    criteria = quest.get("criteria") or {}
    target = float(criteria.get("target") or 1)
    completed = bool(progress_entry.get("completed_at"))
    percent = 100 if completed else (min(100, round((progress / target) * 100)) if target else 0)
    return {
        "id": quest.get("id"),
        "title": quest.get("title"),
        "description": quest.get("description"),
        "criteria": criteria,
        "class_id": quest.get("class_id"),
        "class_name": quest.get("class_name"),
        "reward_xp": quest.get("reward_xp"),
        "status": quest.get("status"),
        "auto": bool(quest.get("auto")),
        "progress": progress,
        "target": target,
        "progress_percent": percent,
        "completed_at": progress_entry.get("completed_at"),
        "created_at": quest.get("created_at"),
    }


def _count_quest_completions(
    state: Dict[str, Any],
    class_ids: Optional[Set[str]] = None,
    since: Optional[datetime] = None,
) -> int:
    count = 0
    gam = state.get("gamification", {})
    quests = gam.get("quests") or {}
    progress = gam.get("quest_progress") or {}
    for quest_id, quest in quests.items():
        if class_ids and quest.get("class_id") not in class_ids:
            continue
        user_progress = progress.get(quest_id) or {}
        for entry in user_progress.values():
            completed_at = entry.get("completed_at")
            if not completed_at:
                continue
            dt = parse_iso_datetime(completed_at)
            if since and dt and dt < since:
                continue
            if class_ids and quest.get("class_id") not in class_ids:
                continue
            count += 1
    return count


def _collect_user_quests(state: Dict[str, Any], user: Dict[str, Any], class_id: Optional[str] = None) -> List[Dict[str, Any]]:
    gam = state.setdefault("gamification", {})
    quests = gam.setdefault("quests", {})
    allowed_classes: Set[str] = set()
    if class_id:
        allowed_classes.add(class_id)
    elif user.get("role") == "student":
        allowed_classes.update(_get_user_class_ids(state, user["id"]))
    elif user.get("role") == "teacher":
        # teachers must request a specific class to view quests
        if class_id:
            allowed_classes.add(class_id)
    elif user.get("role") == "admin":
        allowed_classes.update((state.get("classes") or {}).keys())

    filtered: List[Dict[str, Any]] = []
    for quest in quests.values():
        if quest.get("status") == "completed":
            continue
        quest_class = quest.get("class_id")
        if quest.get("user_id") and quest.get("user_id") != user.get("id"):
            continue
        if quest_class:
            if allowed_classes and quest_class not in allowed_classes:
                continue
        else:
            continue
        filtered.append(_normalize_quest_for_response(state, quest, user.get("id")))
    filtered.sort(key=lambda row: (row.get("progress_percent") or 0, row.get("reward_xp") or 0), reverse=True)
    return filtered


def _get_user_display_name(state: Dict[str, Any], user_id: str) -> str:
    user = (state.get("users") or {}).get(user_id) or {}
    if not user:
        return "Student"
    return (
        user.get("full_name")
        or user.get("fullName")
        or user.get("email")
        or user.get("id")
        or "Student"
    )


def _anonymize_label(label: str) -> str:
    if not label:
        return "Learner"
    parts = label.split()
    first = parts[0][0] if parts[0] else "L"
    return f"Student {first.upper()}"


def _ensure_class_leaderboard_config(cls: Dict[str, Any]) -> Dict[str, Any]:
    config = cls.setdefault("leaderboard_config", {})
    if not isinstance(config, dict):
        config = {}
    config.setdefault("enabled", True)
    config.setdefault("anonymous", False)
    config.setdefault("focus", "xp")
    config.setdefault("show_top_improvers", False)
    config.setdefault("limit", 6)
    cls["leaderboard_config"] = config
    return config


def _student_mastery_trend(state: Dict[str, Any], student_id: str) -> Dict[str, Optional[float]]:
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    prev_week = now - timedelta(days=14)
    events = _get_student_events(state, student_id, include_practice=True)
    recent_scores: List[float] = []
    previous_scores: List[float] = []
    for event in events:
        entry = event.get("entry") or {}
        metrics = _extract_entry_metrics(entry)
        mastery_score = metrics.get("mastery_score")
        if mastery_score is None:
            continue
        timestamp = _entry_timestamp(entry, event.get("session"))
        dt = parse_iso_datetime(timestamp) if timestamp else None
        if not dt:
            continue
        if dt >= week_ago:
            recent_scores.append(float(mastery_score))
        elif prev_week <= dt < week_ago:
            previous_scores.append(float(mastery_score))
    recent_avg = round(sum(recent_scores) / len(recent_scores), 1) if recent_scores else None
    previous_avg = round(sum(previous_scores) / len(previous_scores), 1) if previous_scores else None
    delta = None
    if recent_avg is not None and previous_avg is not None:
        delta = round(recent_avg - previous_avg, 1)
    return {"recent": recent_avg, "previous": previous_avg, "delta": delta}


def _student_weekly_xp(state: Dict[str, Any], user_id: str, start: datetime, end: datetime) -> float:
    xp_rows = state.get("gamification", {}).get("xp", {})
    row = xp_rows.get(user_id) or {}
    history = row.get("xp_history") or []
    return _sum_xp_history(history, start, end)


def _class_leaderboard_entries(
    state: Dict[str, Any],
    class_id: str,
    config: Dict[str, Any],
) -> List[Dict[str, Any]]:
    students = _get_class_students(state, class_id)
    gam = state.get("gamification", {}) or {}
    week_end = datetime.now(timezone.utc)
    week_start = week_end - timedelta(days=7)
    prev_week_start = week_start - timedelta(days=7)
    entries: List[Dict[str, Any]] = []

    for sid in students:
        xp_row = (gam.get("xp") or {}).get(sid) or {}
        weekly_xp = _student_weekly_xp(state, sid, week_start, week_end)
        prev_week_xp = _student_weekly_xp(state, sid, prev_week_start, week_start)
        mastery = _student_mastery_trend(state, sid)
        streak_info = (gam.get("streaks") or {}).get(sid) or {}
        name = _get_user_display_name(state, sid)
        label = _anonymize_label(name) if config.get("anonymous") else name
        entries.append(
            {
                "student_id": sid,
                "name": name,
                "label": label,
                "xp_total": float(xp_row.get("xp_total", 0.0) or 0.0),
                "level": int(xp_row.get("level", 1) or 1),
                "weekly_xp": round(weekly_xp, 1),
                "weekly_delta": round(weekly_xp - prev_week_xp, 1),
                "mastery_recent": mastery.get("recent"),
                "mastery_previous": mastery.get("previous"),
                "mastery_delta": mastery.get("delta"),
                "streak": int(streak_info.get("current_streak", 0) or 0),
            }
        )

    focus = config.get("focus") if config.get("focus") in {"xp", "improvement"} else "xp"
    if focus == "improvement":
        entries.sort(key=lambda row: (row.get("mastery_delta") or 0, row.get("weekly_xp") or 0), reverse=True)
    else:
        entries.sort(key=lambda row: row.get("xp_total") or 0, reverse=True)

    if config.get("show_top_improvers") and focus == "improvement":
        entries = [row for row in entries if (row.get("mastery_delta") or 0) > 0]

    limit = int(config.get("limit") or 0) or 6
    entries = entries[:limit]
    for idx, row in enumerate(entries, start=1):
        row["rank"] = idx
    return entries


def _get_gamification_status(state: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    gam = state.get("gamification", {})
    xp_data = gam.get("xp", {}).get(user_id, {})
    streak = gam.get("streaks", {}).get(user_id, {})
    achievements = gam.get("user_achievements", {}).get(user_id, [])
    unlocked_keys = [a.get("achievement_id") for a in achievements]
    next_badge = next((defn for defn in ACHIEVEMENT_DEFS if defn["key"] not in unlocked_keys), None)
    unlocked_list = []
    for entry in achievements:
        key = entry.get("achievement_id")
        meta = next((d for d in ACHIEVEMENT_DEFS if d["key"] == key), {})
        unlocked_list.append(
            {
                "achievement_id": key,
                "name": meta.get("name", key),
                "description": meta.get("description"),
                "unlocked_at": entry.get("unlocked_at"),
            }
        )
    return {
        "xp_total": xp_data.get("xp_total", 0),
        "level": xp_data.get("level", 1),
        "next_badge": next_badge,
        "achievements": unlocked_list,
        "streak": streak,
    }


BLOOM_KEYWORDS = {
    "remember": ["define", "list", "identify", "name", "recall", "state"],
    "understand": ["explain", "describe", "summarize", "interpret", "paraphrase"],
    "apply": ["apply", "use", "solve", "calculate", "implement", "demonstrate"],
    "analyze": ["compare", "contrast", "analyze", "differentiate", "examine", "why"],
    "evaluate": ["evaluate", "justify", "critique", "assess", "argue"],
    "create": ["design", "create", "build", "compose", "develop"],
}


def _infer_bloom_level(question: str) -> str:
    text = (question or "").lower()
    for level, keywords in BLOOM_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                return level
    return "unknown"


def _compute_test_quality(quiz: Dict[str, Any]) -> Dict[str, Any]:
    flat = _flatten_quiz_for_adaptive(quiz)
    difficulty_counts: Dict[str, int] = {"easy": 0, "medium": 0, "hard": 0, "very_hard": 0, "unknown": 0}
    bloom_counts: Dict[str, int] = {k: 0 for k in BLOOM_KEYWORDS}
    bloom_counts["unknown"] = 0
    concept_counts: Dict[str, int] = {}

    for q in flat:
        difficulty = (q.get("difficulty") or "unknown").lower()
        if difficulty not in difficulty_counts:
            difficulty = "unknown"
        difficulty_counts[difficulty] += 1

        bloom = _infer_bloom_level(q.get("question", ""))
        bloom_counts[bloom] = bloom_counts.get(bloom, 0) + 1

        concept = _normalize_concept_label(q.get("position") or "")
        concept_counts[concept] = concept_counts.get(concept, 0) + 1

    difficulty_levels = len([k for k, v in difficulty_counts.items() if k != "unknown" and v > 0])
    bloom_levels = len([k for k, v in bloom_counts.items() if k != "unknown" and v > 0])
    concept_total = len([k for k, v in concept_counts.items() if v > 0 and k != "General"])

    diversity_score = 0.0
    diversity_score += (difficulty_levels / 3.0) * 35.0
    diversity_score += (bloom_levels / 6.0) * 35.0
    diversity_score += (min(concept_total, 8) / 8.0) * 30.0

    return {
        "question_count": len(flat),
        "difficulty_distribution": difficulty_counts,
        "bloom_distribution": bloom_counts,
        "concept_distribution": concept_counts,
        "coverage": {
            "concepts": concept_total,
            "difficulty_levels": difficulty_levels,
            "bloom_levels": bloom_levels,
        },
        "quality_score": round(min(diversity_score, 100.0), 1),
    }


def _build_test_review(test: Dict[str, Any], quality: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    status = str(test.get("status") or "")
    notes: List[str] = []
    actions: List[str] = []
    severity = "info"

    if status.startswith("failed"):
        severity = "critical"
        notes.append(test.get("error") or "Pipeline failed. Review logs and re-run.")
        actions.append("Re-run with a smaller question limit or a different model.")
    elif status.startswith("pending"):
        severity = "warning"
        actions.append("Preview quiz and validate structure before approval.")

    if quality:
        if quality.get("question_count", 0) < 5:
            notes.append("Low question count. Consider regenerating for better coverage.")
        coverage = quality.get("coverage") or {}
        if coverage.get("difficulty_levels", 0) < 2:
            notes.append("Difficulty skew detected. Add more easy/hard questions.")
        if coverage.get("bloom_levels", 0) < 3:
            notes.append("Bloom coverage is narrow. Include more higher-order questions.")
        if coverage.get("concepts", 0) < 3:
            notes.append("Low concept coverage. Verify the source material or rerun.")

    if not notes:
        notes.append("Quality signals look healthy. Ready for approval review.")

    return {
        "severity": severity,
        "summary": "Auto review complete",
        "notes": notes[:4],
        "actions": actions[:2],
    }


def _find_assignment_session_for_student(test_id: str, student_id: str, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return (session, test, assignment id) for a given test/student if any."""
    for aid, a in state["assignments"].items():
        if a.get("test_id") != test_id:
            continue
        session = a.get("sessions", {}).get(student_id)
        if session:
            test = state["tests"].get(test_id)
            return {"session": session, "test": test, "assignment_id": aid, "assignment": a}
    return None


def _build_mastery_report(test_id: str, student_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
    """Collect mastery details for a given test and student (from assignment sessions)."""
    test = state["tests"].get(test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Test not found.")

    # Find the assignment that pairs this test with the student
    session = None
    assignment_info = None
    for aid, a in state.get("assignments", {}).items():
        if a.get("test_id") != test_id:
            continue
        if student_id in a.get("students", []):
            sess = a.get("sessions", {}).get(student_id)
            if sess:
                session = sess
                cls = state["classes"].get(a.get("class_id"), {})
                assignment_info = {"assignment_id": aid, "class": {"id": cls.get("id"), "name": cls.get("name")}}
                break
    if session is None:
        raise HTTPException(status_code=404, detail="No session found for this student/test.")

    strengths, weaknesses = _summarize_mastery_from_session(session)
    answered = session.get("answered", [])
    total = int(session.get("limit") or len(answered) or 0)
    correct = int(session.get("correct", 0))
    percent = round((100.0 * correct / total), 1) if total else None

    details = []
    for entry in answered:
        qtext = entry.get("question") or entry.get("evaluation", {}).get("question", "")
        mastery = entry.get("mastery") or {}
        evaln = entry.get("evaluation") or {}
        details.append(
            {
                "question": qtext,
                "mastery_score": mastery.get("mastery_score"),
                "position": mastery.get("position") or evaln.get("position"),
                "is_correct": bool(evaln.get("metrics", {}).get("is_correct", False)),
            }
        )

    student = state["users"].get(student_id, {})
    return {
        "test": {"id": test_id, "title": test.get("title")},
        "student": {
            "id": student_id,
            "name": student.get("full_name") or student.get("fullName") or student.get("email"),
        },
        "assignment": assignment_info,
        "score": correct,
        "total": total,
        "percent": percent,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "answered": details,
    }


# -------------------- Routes -------------------- #
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    index_path = FRONTEND_BUILD / "index.html"
    has_assets = False
    try:
        has_assets = FRONTEND_ASSETS.exists() and any(FRONTEND_ASSETS.iterdir())
    except Exception:
        has_assets = False

    if index_path.exists() and has_assets:
        # Avoid stale UI bundles during development by disabling caching of the SPA shell.
        return FileResponse(index_path, headers={"Cache-Control": "no-store"})

    return templates.TemplateResponse("home.html", {"request": request})


@app.get("/icodex_logo.svg")
async def frontend_logo_svg():
    candidates = [
        FRONTEND_BUILD / "icodex_logo.svg",
        REPO_ROOT / "interface" / "icodex_figma_interface" / "public" / "icodex_logo.svg",
        BASE_DIR / "static" / "icodex_logo.svg",
        REPO_ROOT / "icodex_logo.svg",
    ]
    for logo_path in candidates:
        try:
            if logo_path.exists():
                return FileResponse(logo_path, headers={"Cache-Control": "public, max-age=604800"})
        except Exception:
            continue
    raise HTTPException(status_code=404, detail="Logo not found.")


@app.get("/favicon.ico")
async def favicon_ico():
    return RedirectResponse(url="/icodex_logo.svg?v=2")


@app.get("/favicon.svg")
async def favicon_svg():
    return RedirectResponse(url="/icodex_logo.svg?v=2")


@app.get("/icodex_logo_full.svg")
async def frontend_logo_full_svg():
    candidates = [
        FRONTEND_BUILD / "icodex_logo_full.svg",
        REPO_ROOT / "interface" / "icodex_figma_interface" / "public" / "icodex_logo_full.svg",
        BASE_DIR / "static" / "icodex_logo_full.svg",
        REPO_ROOT / "icodex_logo_full.svg",
    ]
    for logo_path in candidates:
        try:
            if logo_path.exists():
                return FileResponse(logo_path, headers={"Cache-Control": "public, max-age=604800"})
        except Exception:
            continue
    raise HTTPException(status_code=404, detail="Full logo not found.")


@app.get("/api/health")
async def api_health():
    payload: Dict[str, Any] = {
        "status": "ok",
        "storage": "postgres" if DATABASE_URL else "json",
        "render": {
            "service_name": os.environ.get("RENDER_SERVICE_NAME") or None,
            "git_commit": os.environ.get("RENDER_GIT_COMMIT") or None,
        },
    }
    if DATABASE_URL and not HEALTH_SKIP_DB:
        try:
            pool = _get_db_pool()
            conn = pool.getconn()
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1")
                        cur.fetchone()
                        cur.execute("SELECT to_regclass('public.icodex_state')")
                        payload["db_table_exists"] = bool((cur.fetchone() or [None])[0])
                        cur.execute("SELECT 1 FROM icodex_state WHERE id = 1")
                        payload["db_state_present"] = cur.fetchone() is not None
            finally:
                pool.putconn(conn)
            payload["db_ok"] = True
        except Exception as exc:
            payload["db_ok"] = False
            payload["db_error"] = str(exc)[:300]
    elif DATABASE_URL and HEALTH_SKIP_DB:
        payload["db_ok"] = False
        payload["db_error"] = "Skipped DB health check (ICODEX_SKIP_DB_HEALTH=on)"
    return payload


# ---------- JSON Auth ----------
@app.post("/api/auth/signup")
async def api_signup(payload: Dict[str, Any] = Body(...)):
    full_name = payload.get("fullName") or payload.get("full_name")
    email = payload.get("email")
    password = payload.get("password")
    role = payload.get("role", "student")
    school = payload.get("school", "")
    country = payload.get("country", "")
    if not all([full_name, email, password]):
        raise HTTPException(status_code=400, detail="Missing fields.")
    state = load_state()
    if role not in {"student", "teacher", "admin"}:
        raise HTTPException(status_code=400, detail="Invalid role.")
    for u in state["users"].values():
        if u["email"].lower() == email.lower():
            raise HTTPException(status_code=400, detail="Email already registered.")
    user_id = uuid.uuid4().hex
    state["users"][user_id] = {
        "id": user_id,
        "full_name": full_name,
        "email": email,
        "password": password,  # plaintext for demo
        "role": role,
        "status": "active",
        "school": school,
        "country": country,
        "classes": [],
        "teachers": [],
        "practice_tests": [],
        "created_at": iso_utc_now(),
        "last_login_at": "",
        "last_active_at": "",
        "learning_preferences": {
            "daily_goal_minutes": 15,
            "preferred_difficulty": "medium",
            "focus_topics": [],
        },
    }
    save_state(state)
    resp = JSONResponse({"success": True, "user": state["users"][user_id]})
    create_session(resp, user_id, state)
    return resp


@app.post("/api/auth/login")
async def api_login(payload: Dict[str, Any] = Body(...)):
    email = payload.get("email")
    password = payload.get("password")
    if not email or not password:
        raise HTTPException(status_code=400, detail="Missing credentials.")
    state = load_state()
    user = next((u for u in state["users"].values() if u["email"].lower() == email.lower() and u["password"] == password), None)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid credentials.")
    if user.get("status") == "suspended":
        raise HTTPException(status_code=403, detail="Account suspended.")
    resp = JSONResponse({"success": True, "user": user})
    create_session(resp, user["id"], state)
    return resp


@app.post("/api/auth/logout")
async def api_logout(request: Request):
    state = load_state()
    session_id = request.cookies.get("session_id")
    if session_id and session_id in state["sessions"]:
        state["sessions"].pop(session_id, None)
        save_state(state)
    resp = JSONResponse({"success": True})
    resp.delete_cookie("session_id")
    return resp


@app.get("/api/auth/me")
async def api_me(request: Request):
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    state = load_state()
    stored = state.get("users", {}).get(user.get("id"))
    if isinstance(stored, dict):
        stored.setdefault("status", "active")
        prefs = stored.get("learning_preferences")
        if not isinstance(prefs, dict):
            prefs = {}
        prefs.setdefault("daily_goal_minutes", 15)
        prefs.setdefault("preferred_difficulty", "medium")
        prefs.setdefault("focus_topics", [])
        stored["learning_preferences"] = prefs
        stored["last_active_at"] = iso_utc_now()
        state["users"][stored["id"]] = stored
        save_state(state)
        user = stored
    return {"user": user}


@app.get("/api/config")
async def api_get_config(request: Request):
    """
    Global app configuration.

    Readable by any authenticated user so the frontend can gate features.
    Writable only by admins via PUT /api/config.
    """
    require_user(request)
    state = load_state()
    cfg = state.get("config") or {}
    if not isinstance(cfg, dict):
        cfg = {}
    return {
        "config": {
            "teacher_can_assign": bool(cfg.get("teacher_can_assign", False)),
            "feature_flags": cfg.get("feature_flags") or {},
            "admin_permissions": cfg.get("admin_permissions") or {},
            "model_meta": cfg.get("model_meta") or {},
            "environment": cfg.get("environment") or {},
        }
    }


@app.put("/api/config")
async def api_update_config(request: Request, payload: Dict[str, Any] = Body(...)):
    admin = require_user(request)
    require_role(admin, "admin")
    state = load_state()
    cfg = state.get("config") or {}
    if not isinstance(cfg, dict):
        cfg = {}

    if "teacher_can_assign" in payload or "teacherCanAssign" in payload:
        cfg["teacher_can_assign"] = bool(payload.get("teacher_can_assign", payload.get("teacherCanAssign")))

    if "feature_flags" in payload or "featureFlags" in payload:
        flags = payload.get("feature_flags") or payload.get("featureFlags") or {}
        if isinstance(flags, dict):
            cfg["feature_flags"] = flags

    if "admin_permissions" in payload or "adminPermissions" in payload:
        perms = payload.get("admin_permissions") or payload.get("adminPermissions") or {}
        if isinstance(perms, dict):
            cfg["admin_permissions"] = perms

    if "model_meta" in payload or "modelMeta" in payload:
        model_meta = payload.get("model_meta") or payload.get("modelMeta") or {}
        if isinstance(model_meta, dict):
            cfg["model_meta"] = model_meta

    if "gamification" in payload:
        gam_cfg = payload.get("gamification") or {}
        if isinstance(gam_cfg, dict):
            cfg["gamification"] = {**cfg.get("gamification", {}), **gam_cfg}

    if "environment" in payload:
        env_meta = payload.get("environment") or {}
        if isinstance(env_meta, dict):
            cfg["environment"] = env_meta

    state["config"] = cfg
    save_state(state)
    return {
        "success": True,
        "config": {
            "teacher_can_assign": bool(cfg.get("teacher_can_assign", False)),
            "feature_flags": cfg.get("feature_flags") or {},
            "admin_permissions": cfg.get("admin_permissions") or {},
            "model_meta": cfg.get("model_meta") or {},
            "environment": cfg.get("environment") or {},
        },
    }


@app.get("/api/system/meta")
async def api_system_meta(request: Request):
    require_user(request)
    state = load_state()
    cfg = state.get("config") or {}
    return {
        "environment": cfg.get("environment") or DEFAULT_ENVIRONMENT_META,
        "model_meta": cfg.get("model_meta") or DEFAULT_MODEL_META,
        "feature_flags": cfg.get("feature_flags") or DEFAULT_FEATURE_FLAGS,
        "admin_permissions": cfg.get("admin_permissions") or DEFAULT_ADMIN_PERMISSIONS,
        "db": _db_health_payload(),
    }


@app.put("/api/auth/me")
async def api_update_me(request: Request, payload: Dict[str, Any] = Body(...)):
    """
    Update basic profile information for the current user.

    Allows changing full name, school, country and optionally password.
    Role and email are not editable from the Settings screen.
    """
    user = require_user(request)
    state = load_state()
    stored = state["users"].get(user["id"])
    if not stored:
        raise HTTPException(status_code=404, detail="User not found.")

    full_name = payload.get("full_name") or payload.get("fullName") or stored.get("full_name", "")
    school = payload.get("school", stored.get("school", ""))
    country = payload.get("country", stored.get("country", ""))
    password = payload.get("password")
    prefs = stored.get("learning_preferences") if isinstance(stored.get("learning_preferences"), dict) else {}
    if payload.get("daily_goal_minutes") is not None:
        try:
            prefs["daily_goal_minutes"] = max(5, min(180, int(payload.get("daily_goal_minutes"))))
        except (TypeError, ValueError):
            pass
    if payload.get("preferred_difficulty"):
        prefs["preferred_difficulty"] = str(payload.get("preferred_difficulty"))
    if payload.get("focus_topics") is not None:
        topics = payload.get("focus_topics")
        if isinstance(topics, str):
            prefs["focus_topics"] = [t.strip() for t in topics.split(",") if t.strip()]
        elif isinstance(topics, list):
            prefs["focus_topics"] = [str(t).strip() for t in topics if str(t).strip()]
    stored["learning_preferences"] = prefs

    stored["full_name"] = full_name
    stored["school"] = school
    stored["country"] = country
    if password:
        stored["password"] = password

    state["users"][user["id"]] = stored
    save_state(state)
    return {"success": True, "user": stored}


@app.post("/signup")
async def signup(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    school: str = Form(""),
    country: str = Form(""),
):
    state = load_state()
    if role not in {"student", "teacher", "admin"}:
        raise HTTPException(status_code=400, detail="Invalid role.")
    # simple uniqueness check
    for u in state["users"].values():
        if u["email"].lower() == email.lower():
            raise HTTPException(status_code=400, detail="Email already registered.")
    user_id = uuid.uuid4().hex
    state["users"][user_id] = {
        "id": user_id,
        "full_name": full_name,
        "email": email,
        "password": password,  # note: plaintext for demo; replace with hashing in production
        "role": role,
        "school": school,
        "country": country,
        "classes": [],  # for teachers and students (assigned by admin)
        "teachers": [],  # deprecated; kept for backward compat
        "practice_tests": [],
    }
    session_id = uuid.uuid4().hex
    state["sessions"][session_id] = {"user_id": user_id}
    save_state(state)
    resp = RedirectResponse("/dashboard", status_code=303)
    resp.set_cookie("session_id", session_id)
    return resp


@app.post("/login")
async def login(request: Request, email: str = Form(...), password: str = Form(...)):
    state = load_state()
    user = next((u for u in state["users"].values() if u["email"].lower() == email.lower() and u["password"] == password), None)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid credentials.")
    session_id = uuid.uuid4().hex
    state["sessions"][session_id] = {"user_id": user["id"]}
    save_state(state)
    resp = RedirectResponse("/dashboard", status_code=303)
    resp.set_cookie("session_id", session_id)
    return resp


@app.get("/logout")
async def logout(request: Request):
    state = load_state()
    session_id = request.cookies.get("session_id")
    if session_id and session_id in state["sessions"]:
        state["sessions"].pop(session_id, None)
        save_state(state)
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie("session_id")
    return resp


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = get_session_user(request)
    if not user:
        return RedirectResponse("/", status_code=303)
    state = load_state()
    if user["role"] == "teacher":
        tests = [t for t in state["tests"].values() if t["owner_id"] == user["id"] and t.get("kind") == "class_test"]
        return templates.TemplateResponse(
            "dashboard_teacher.html",
            {"request": request, "user": user, "tests": tests},
        )
    if user["role"] == "student":
        assignments = state["assignments"]
        my_tests = []
        for aid, a in assignments.items():
            class_id = a.get("class_id")
            if class_id and user["id"] in state["classes"].get(class_id, {}).get("students", []):
                test = state["tests"].get(a["test_id"])
                if test:
                    my_tests.append({"assignment_id": aid, "test": test, "status": a.get("status", {}).get(user["id"], "pending")})
        # practice tests owned by student
        practice_tests = [t for t in state["tests"].values() if t["owner_id"] == user["id"] and t.get("kind") == "practice"]
        return templates.TemplateResponse(
            "dashboard_student.html",
            {"request": request, "user": user, "assignments": my_tests, "practice_tests": practice_tests},
        )
    # admin view
    classes = state["classes"]
    teachers = [u for u in state["users"].values() if u["role"] == "teacher"]
    students = [u for u in state["users"].values() if u["role"] == "student"]
    users = list(state["users"].values())
    pending_tests = [t for t in state["tests"].values() if t.get("status", "").startswith("pending")]
    ready_tests = [t for t in state["tests"].values() if t.get("status") == "ready"]
    return templates.TemplateResponse(
        "dashboard_admin.html",
        {
            "request": request,
            "user": user,
            "classes": classes,
            "teachers": teachers,
            "students": students,
            "users": users,
            "pending_tests": pending_tests,
            "ready_tests": ready_tests,
        },
    )


# ---------- JSON Users ----------
@app.get("/api/users")
async def api_list_users(request: Request):
    user = require_user(request)
    require_role(user, "admin")
    state = load_state()
    risk_lookup = _build_student_risk_lookup(state)
    return {"users": [decorate_user_for_response(u, state, risk_lookup) for u in state["users"].values()]}


@app.post("/api/users")
async def api_create_user(request: Request, payload: Dict[str, Any] = Body(...)):
    user = require_user(request)
    require_role(user, "admin")
    full_name = payload.get("full_name") or payload.get("fullName")
    email = payload.get("email")
    password = payload.get("password")
    role = payload.get("role", "student")
    school = payload.get("school", "")
    country = payload.get("country", "")
    if not all([full_name, email, password]):
        raise HTTPException(status_code=400, detail="Missing fields.")
    state = load_state()
    if role not in {"student", "teacher", "admin"}:
        raise HTTPException(status_code=400, detail="Invalid role.")
    for u in state["users"].values():
        if u["email"].lower() == email.lower():
            raise HTTPException(status_code=400, detail="Email already registered.")
    user_id = uuid.uuid4().hex
    state["users"][user_id] = {
        "id": user_id,
        "full_name": full_name,
        "email": email,
        "password": password,
        "role": role,
        "status": "active",
        "school": school,
        "country": country,
        "classes": [],
        "teachers": [],
        "practice_tests": [],
        "created_at": iso_utc_now(),
        "last_login_at": "",
        "last_active_at": "",
        "learning_preferences": {
            "daily_goal_minutes": 15,
            "preferred_difficulty": "medium",
            "focus_topics": [],
        },
    }
    append_audit_log(
        state,
        actor_id=user.get("id"),
        action="user_created",
        target_type="user",
        target_id=user_id,
        details={"role": role, "email": email},
    )
    save_state(state)
    return {"success": True, "user": state["users"][user_id]}


@app.put("/api/users/{user_id}")
async def api_update_user(request: Request, user_id: str, payload: Dict[str, Any] = Body(...)):
    admin = require_user(request)
    require_role(admin, "admin")
    state = load_state()
    user = state["users"].get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    updated = False
    prev_role = user.get("role")
    prev_status = user.get("status", "active")

    if "role" in payload:
        next_role = payload.get("role")
        if next_role not in {"student", "teacher", "admin"}:
            raise HTTPException(status_code=400, detail="Invalid role.")
        if next_role != prev_role:
            user["role"] = next_role
            updated = True
            append_audit_log(
                state,
                actor_id=admin.get("id"),
                action="role_changed",
                target_type="user",
                target_id=user_id,
                details={"from": prev_role, "to": next_role},
            )

    if "status" in payload:
        next_status = payload.get("status")
        if next_status not in {"active", "invited", "suspended"}:
            raise HTTPException(status_code=400, detail="Invalid status.")
        if next_status != prev_status:
            user["status"] = next_status
            updated = True
            if next_status == "suspended":
                # remove active sessions
                for sid, sess in list(state.get("sessions", {}).items()):
                    if sess.get("user_id") == user_id:
                        state["sessions"].pop(sid, None)
            if next_status == "invited":
                user["invited_at"] = iso_utc_now()
            append_audit_log(
                state,
                actor_id=admin.get("id"),
                action="status_changed",
                target_type="user",
                target_id=user_id,
                details={"from": prev_status, "to": next_status},
            )

    for field in ("full_name", "school", "country"):
        if field in payload:
            user[field] = payload.get(field) or ""
            updated = True

    user.setdefault("status", "active")
    state["users"][user_id] = user
    if updated:
        save_state(state)
    return {"success": True, "user": user}


@app.delete("/api/users/{user_id}")
async def api_delete_user(request: Request, user_id: str):
    user = require_user(request)
    require_role(user, "admin")
    state = load_state()
    state["users"].pop(user_id, None)
    for sid, sess in list(state.get("sessions", {}).items()):
        if sess.get("user_id") == user_id:
            state["sessions"].pop(sid, None)
    for cls in state["classes"].values():
        cls["students"] = [s for s in cls.get("students", []) if s != user_id]
        cls["teachers"] = [t for t in cls.get("teachers", []) if t != user_id]
    append_audit_log(
        state,
        actor_id=user.get("id"),
        action="user_deleted",
        target_type="user",
        target_id=user_id,
        details={},
    )
    save_state(state)
    return {"success": True}


@app.post("/api/users/bulk")
async def api_bulk_users(request: Request, payload: Dict[str, Any] = Body(...)):
    admin = require_user(request)
    require_role(admin, "admin")
    action = payload.get("action")
    user_ids = payload.get("user_ids") or payload.get("userIds") or []
    if not isinstance(user_ids, list) or not user_ids:
        raise HTTPException(status_code=400, detail="No user_ids provided.")

    state = load_state()
    updated = 0
    errors: List[str] = []

    for uid in user_ids:
        user = state["users"].get(uid)
        if not user:
            errors.append(f"{uid}: not found")
            continue

        if action == "suspend":
            prev_status = user.get("status", "active")
            if prev_status != "suspended":
                user["status"] = "suspended"
                append_audit_log(
                    state,
                    actor_id=admin.get("id"),
                    action="status_changed",
                    target_type="user",
                    target_id=uid,
                    details={"from": prev_status, "to": "suspended"},
                )
            for sid, sess in list(state.get("sessions", {}).items()):
                if sess.get("user_id") == uid:
                    state["sessions"].pop(sid, None)
            updated += 1
        elif action == "invite":
            prev_status = user.get("status", "active")
            if prev_status != "invited":
                user["status"] = "invited"
                user["invited_at"] = iso_utc_now()
                append_audit_log(
                    state,
                    actor_id=admin.get("id"),
                    action="status_changed",
                    target_type="user",
                    target_id=uid,
                    details={"from": prev_status, "to": "invited"},
                )
            updated += 1
        elif action == "activate":
            if user.get("status") != "active":
                prev = user.get("status", "active")
                user["status"] = "active"
                append_audit_log(
                    state,
                    actor_id=admin.get("id"),
                    action="status_changed",
                    target_type="user",
                    target_id=uid,
                    details={"from": prev, "to": "active"},
                )
            updated += 1
        elif action == "delete":
            state["users"].pop(uid, None)
            for sid, sess in list(state.get("sessions", {}).items()):
                if sess.get("user_id") == uid:
                    state["sessions"].pop(sid, None)
            for cls in state["classes"].values():
                cls["students"] = [s for s in cls.get("students", []) if s != uid]
                cls["teachers"] = [t for t in cls.get("teachers", []) if t != uid]
            append_audit_log(
                state,
                actor_id=admin.get("id"),
                action="user_deleted",
                target_type="user",
                target_id=uid,
                details={},
            )
            updated += 1
        elif action == "role":
            next_role = payload.get("role")
            if next_role not in {"student", "teacher", "admin"}:
                errors.append(f"{uid}: invalid role")
                continue
            prev_role = user.get("role")
            if prev_role != next_role:
                user["role"] = next_role
                append_audit_log(
                    state,
                    actor_id=admin.get("id"),
                    action="role_changed",
                    target_type="user",
                    target_id=uid,
                    details={"from": prev_role, "to": next_role},
                )
            updated += 1
        else:
            raise HTTPException(status_code=400, detail="Unknown action.")

        if action != "delete":
            state["users"][uid] = user

    save_state(state)
    return {"success": True, "updated": updated, "errors": errors}


@app.get("/api/audit")
async def api_audit_logs(
    request: Request,
    limit: int = 50,
    action: Optional[str] = None,
    target_type: Optional[str] = None,
):
    admin = require_user(request)
    require_role(admin, "admin")
    state = load_state()
    logs = state.get("audit_logs") or []
    if action:
        logs = [l for l in logs if l.get("action") == action]
    if target_type:
        logs = [l for l in logs if l.get("target_type") == target_type]
    limit = max(1, min(int(limit or 50), 200))

    def decorate(entry: Dict[str, Any]) -> Dict[str, Any]:
        actor_id = entry.get("actor_id")
        actor = state.get("users", {}).get(actor_id or "", {})
        entry = dict(entry)
        entry["actor_name"] = actor.get("full_name") or actor.get("email") or "System"
        return entry

    return {"logs": [decorate(l) for l in logs[:limit]]}


# ---------- JSON Classes ----------
@app.get("/api/classes")
async def api_list_classes(request: Request):
    require_user(request)
    state = load_state()
    return {"classes": list(state["classes"].values())}


@app.post("/api/classes")
async def api_create_class(request: Request, payload: Dict[str, Any] = Body(...)):
    admin = require_user(request)
    require_role(admin, "admin")
    name = payload.get("name")
    description = payload.get("description") or ""
    if not name:
        raise HTTPException(status_code=400, detail="Missing class name.")
    state = load_state()
    class_id = uuid.uuid4().hex
    state["classes"][class_id] = {
        "id": class_id,
        "name": name,
        "description": description,
        "teachers": [],
        "students": [],
        "created_at": iso_utc_now(),
    }
    save_state(state)
    return {"success": True, "class": state["classes"][class_id]}


@app.post("/api/classes/assign-teacher")
async def api_assign_teacher(request: Request, payload: Dict[str, Any] = Body(...)):
    admin = require_user(request)
    require_role(admin, "admin")
    class_id = payload.get("class_id")
    teacher_id = payload.get("teacher_id")
    state = load_state()
    cls = state["classes"].get(class_id)
    if not cls:
        raise HTTPException(status_code=400, detail="Class not found.")
    if teacher_id not in state["users"]:
        raise HTTPException(status_code=400, detail="Teacher not found.")
    if teacher_id not in cls["teachers"]:
        cls["teachers"].append(teacher_id)
    state["classes"][class_id] = cls
    save_state(state)
    return {"success": True}


@app.post("/api/classes/assign-student")
async def api_assign_student(request: Request, payload: Dict[str, Any] = Body(...)):
    admin = require_user(request)
    require_role(admin, "admin")
    class_id = payload.get("class_id")
    student_id = payload.get("student_id")
    state = load_state()
    cls = state["classes"].get(class_id)
    if not cls:
        raise HTTPException(status_code=400, detail="Class not found.")
    if student_id not in state["users"]:
        raise HTTPException(status_code=400, detail="Student not found.")
    if student_id not in cls["students"]:
        cls["students"].append(student_id)
    state["users"][student_id]["classes"] = list(set(state["users"][student_id].get("classes", [])) | {class_id})
    state["classes"][class_id] = cls
    save_state(state)
    return {"success": True}


@app.post("/api/classes/remove-teacher")
async def api_remove_teacher(request: Request, payload: Dict[str, Any] = Body(...)):
    admin = require_user(request)
    require_role(admin, "admin")
    class_id = payload.get("class_id")
    teacher_id = payload.get("teacher_id")
    state = load_state()
    cls = state["classes"].get(class_id)
    if not cls:
        raise HTTPException(status_code=400, detail="Class not found.")
    cls["teachers"] = [t for t in cls.get("teachers", []) if t != teacher_id]
    state["classes"][class_id] = cls
    save_state(state)
    return {"success": True}


@app.post("/api/classes/remove-student")
async def api_remove_student(request: Request, payload: Dict[str, Any] = Body(...)):
    admin = require_user(request)
    require_role(admin, "admin")
    class_id = payload.get("class_id")
    student_id = payload.get("student_id")
    state = load_state()
    cls = state["classes"].get(class_id)
    if not cls:
        raise HTTPException(status_code=400, detail="Class not found.")
    cls["students"] = [s for s in cls.get("students", []) if s != student_id]
    if student_id in state["users"]:
        state["users"][student_id]["classes"] = [c for c in state["users"][student_id].get("classes", []) if c != class_id]
    state["classes"][class_id] = cls
    save_state(state)
    return {"success": True}


@app.delete("/api/classes/{class_id}")
async def api_delete_class(class_id: str, request: Request):
    admin = require_user(request)
    require_role(admin, "admin")
    state = load_state()
    cls = state["classes"].get(class_id)
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found.")

    # Remove assignments tied to this class
    assignments = state.get("assignments", {})
    to_delete = [aid for aid, a in assignments.items() if a.get("class_id") == class_id]
    for aid in to_delete:
        assignments.pop(aid, None)

    # Remove class membership references from users
    for uid, u in state.get("users", {}).items():
        if isinstance(u.get("classes"), list) and class_id in u.get("classes", []):
            u["classes"] = [c for c in u.get("classes", []) if c != class_id]
            state["users"][uid] = u

    state["classes"].pop(class_id, None)
    save_state(state)
    return {"success": True, "deleted_class_id": class_id, "deleted_assignments": to_delete}


# ---------- Admin analytics ----------
@app.get("/api/admin/overview")
async def api_admin_overview(request: Request):
    admin = require_user(request)
    require_role(admin, "admin")
    state = load_state()

    users = list(state.get("users", {}).values())
    classes = list(state.get("classes", {}).values())
    tests = list(state.get("tests", {}).values())
    class_tests = [t for t in tests if t.get("kind") == "class_test"]

    pending_tests = [t for t in class_tests if str(t.get("status") or "").startswith("pending")]
    failed_tests = [t for t in class_tests if str(t.get("status") or "").startswith("failed")]
    ready_tests = [t for t in class_tests if str(t.get("status") or "") in {"ready", "approved"}]

    events = _iter_answer_events(state, include_practice=False)
    mastery_scores: List[float] = []
    confidence_scores: List[float] = []
    failed_concepts: Dict[str, int] = {}
    active_students: Set[str] = set()

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    for event in events:
        entry = event.get("entry") or {}
        metrics = _extract_entry_metrics(entry)
        mastery_score = metrics.get("mastery_score")
        if mastery_score is not None:
            mastery_scores.append(float(mastery_score))
        confidence = metrics.get("confidence")
        if confidence is not None:
            confidence_scores.append(float(confidence))

        timestamp = _entry_timestamp(entry, event.get("session"))
        if timestamp:
            ts = parse_iso_datetime(timestamp)
            if ts and (now - ts).total_seconds() <= 86400:
                student_id = event.get("student_id")
                if student_id:
                    active_students.add(student_id)

        if metrics.get("is_correct") is False:
            timestamp = _entry_timestamp(entry, event.get("session"))
            if timestamp:
                dt = parse_iso_datetime(timestamp)
                if dt and dt < week_ago:
                    continue
            concept = _normalize_concept_label(metrics.get("position"))
            failed_concepts[concept] = failed_concepts.get(concept, 0) + 1

    avg_mastery = round(sum(mastery_scores) / len(mastery_scores), 1) if mastery_scores else None
    avg_conf = round(sum(confidence_scores) / len(confidence_scores), 2) if confidence_scores else None
    if avg_conf is None:
        conf_label = "Unknown"
    elif avg_conf >= 0.75:
        conf_label = "High"
    elif avg_conf >= 0.55:
        conf_label = "Moderate"
    else:
        conf_label = "Low"

    risk_lookup = _build_student_risk_lookup(state)
    total_students = len([u for u in users if u.get("role") == "student"])
    at_risk = len([r for r in risk_lookup.values() if r.get("label") == "high"])
    at_risk_pct = round((at_risk / total_students) * 100.0, 1) if total_students else 0.0

    failed_concepts_sorted = [
        {"concept": concept, "failed": count}
        for concept, count in sorted(failed_concepts.items(), key=lambda item: item[1], reverse=True)
    ][:5]

    durations = []
    pipeline_issues = []
    for test in class_tests:
        pipeline = test.get("pipeline") or {}
        duration = _to_float(pipeline.get("duration_seconds"))
        if duration is not None:
            durations.append(duration)
        status = str(test.get("status") or "")
        if status.startswith("failed") or status.startswith("pending"):
            pipeline_issues.append(
                {
                    "test_id": test.get("id"),
                    "title": test.get("title") or "Untitled",
                    "status": status,
                    "error": test.get("error") or "",
                    "stage": (pipeline.get("steps") or [{}])[-1].get("name") if pipeline.get("steps") else "",
                }
            )

    avg_duration = round(sum(durations) / len(durations), 1) if durations else None

    logs = state.get("audit_logs") or []
    recent_activity = []
    for entry in logs[:5]:
        actor = state.get("users", {}).get(entry.get("actor_id") or "", {})
        recent_activity.append(
            {
                "id": entry.get("id"),
                "actor": actor.get("full_name") or actor.get("email") or "System",
                "action": entry.get("action"),
                "target_type": entry.get("target_type"),
                "target_id": entry.get("target_id"),
                "created_at": entry.get("created_at"),
                "details": entry.get("details") or {},
            }
        )

    gamification_state = state.get("gamification", {})
    xp_rows = gamification_state.get("xp", {}) or {}
    total_xp_week = 0.0
    for row in xp_rows.values():
        history = row.get("xp_history") or []
        total_xp_week += _sum_xp_history(history, week_ago, now)
    streaks = gamification_state.get("streaks") or {}
    streak_distribution = {"0": 0, "1-3": 0, "4-7": 0, "8+": 0}
    for streak in streaks.values():
        days = int(streak.get("current_streak", 0) or 0)
        if days == 0:
            streak_distribution["0"] += 1
        elif days <= 3:
            streak_distribution["1-3"] += 1
        elif days <= 7:
            streak_distribution["4-7"] += 1
        else:
            streak_distribution["8+"] += 1
    quests_completed_last_week = _count_quest_completions(state, since=week_ago)

    return {
        "totals": {
            "users": len(users),
            "classes": len(classes),
            "tests": len(class_tests),
            "ready_tests": len(ready_tests),
        },
        "mastery": {
            "average": avg_mastery,
            "at_risk_students": at_risk,
            "at_risk_percent": at_risk_pct,
        },
        "most_failed_concepts": failed_concepts_sorted,
        "ai_confidence": {"score": avg_conf, "label": conf_label, "samples": len(confidence_scores)},
        "pipeline": {
            "pending": len(pending_tests),
            "failed": len(failed_tests),
            "avg_duration_seconds": avg_duration,
            "issues": pipeline_issues[:5],
        },
        "gamification_metrics": {
            "daily_active_students": len(active_students),
            "avg_xp_per_day": round(total_xp_week / 7.0, 1),
            "streak_distribution": streak_distribution,
            "quests_completed_last_week": quests_completed_last_week,
        },
        "recent_activity": recent_activity,
    }


@app.get("/api/classes/{class_id}/analytics")
async def api_class_analytics(class_id: str, request: Request):
    user = require_user(request)
    state = load_state()
    cls = state.get("classes", {}).get(class_id)
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found.")
    if user.get("role") == "teacher" and user.get("id") not in (cls.get("teachers") or []):
        raise HTTPException(status_code=403, detail="Forbidden")
    if user.get("role") not in {"admin", "teacher"}:
        raise HTTPException(status_code=403, detail="Forbidden")

    assignments = [a for a in (state.get("assignments") or {}).values() if a.get("class_id") == class_id]
    events = [e for e in _iter_answer_events(state, include_practice=False) if e.get("class_id") == class_id]

    per_student: Dict[str, Dict[str, float]] = {}
    concept_mastery: Dict[str, List[float]] = {}
    for event in events:
        student_id = event.get("student_id")
        entry = event.get("entry") or {}
        metrics = _extract_entry_metrics(entry)
        mastery_score = metrics.get("mastery_score")
        if student_id and mastery_score is not None:
            row = per_student.setdefault(student_id, {"mastery_sum": 0.0, "count": 0.0})
            row["mastery_sum"] += float(mastery_score)
            row["count"] += 1.0
        concept = _normalize_concept_label(metrics.get("position"))
        if mastery_score is not None:
            concept_mastery.setdefault(concept, []).append(float(mastery_score))

    student_mastery = []
    for sid, row in per_student.items():
        count = row.get("count", 0.0) or 0.0
        if count:
            student_mastery.append(row["mastery_sum"] / count)

    avg_mastery = round(sum(student_mastery) / len(student_mastery), 1) if student_mastery else None
    struggling = len([m for m in student_mastery if m < 60.0])
    total_students = len(cls.get("students") or [])
    struggling_pct = round((struggling / total_students) * 100.0, 1) if total_students else 0.0

    mastery_distribution = {"0-40": 0, "40-60": 0, "60-80": 0, "80-100": 0}
    for score in student_mastery:
        if score < 40:
            mastery_distribution["0-40"] += 1
        elif score < 60:
            mastery_distribution["40-60"] += 1
        elif score < 80:
            mastery_distribution["60-80"] += 1
        else:
            mastery_distribution["80-100"] += 1

    concept_coverage: Dict[str, int] = {}
    for assignment in assignments:
        test_id = assignment.get("test_id")
        test = state.get("tests", {}).get(test_id or "")
        if not test:
            continue
        quality = test.get("quality")
        if not quality:
            try:
                quiz = _get_test_quiz(test_id, state)
                quality = _compute_test_quality(quiz)
            except Exception:
                quality = None
        concept_dist = (quality or {}).get("concept_distribution") or {}
        for concept, count in concept_dist.items():
            concept_coverage[concept] = concept_coverage.get(concept, 0) + int(count)

    concept_mastery_payload = [
        {
            "concept": concept,
            "avg_mastery": round(sum(scores) / len(scores), 1),
            "attempts": len(scores),
        }
        for concept, scores in concept_mastery.items()
        if scores
    ]
    concept_mastery_payload.sort(key=lambda row: row["avg_mastery"])

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    recent_answers = 0
    last_activity_at = None
    for event in events:
        timestamp = _entry_timestamp(event.get("entry") or {}, event.get("session"))
        dt = parse_iso_datetime(timestamp) if timestamp else None
        if dt:
            if last_activity_at is None or dt > last_activity_at:
                last_activity_at = dt
            if dt >= week_ago:
                recent_answers += 1

    last_assignment_at = None
    for assignment in assignments:
        ts = assignment.get("created_at") or assignment.get("createdAt")
        dt = parse_iso_datetime(ts) if isinstance(ts, str) else None
        if dt and (last_assignment_at is None or dt > last_assignment_at):
            last_assignment_at = dt

    return {
        "class": {"id": cls.get("id"), "name": cls.get("name")},
        "health": {
            "avg_mastery": avg_mastery,
            "struggling_percent": struggling_pct,
            "students": total_students,
        },
        "activity": {
            "recent_answers": recent_answers,
            "last_activity_at": last_activity_at.isoformat().replace("+00:00", "Z") if last_activity_at else None,
            "last_assignment_at": last_assignment_at.isoformat().replace("+00:00", "Z") if last_assignment_at else None,
        },
        "concepts": {
            "coverage": [{"concept": c, "questions": q} for c, q in concept_coverage.items()],
            "mastery": concept_mastery_payload[:12],
        },
        "mastery_distribution": mastery_distribution,
    }


@app.get("/api/classes/health")
async def api_classes_health(request: Request):
    admin = require_user(request)
    require_role(admin, "admin")
    state = load_state()
    classes = state.get("classes") or {}
    events = _iter_answer_events(state, include_practice=False)
    per_class_scores: Dict[str, List[float]] = {}
    per_class_students: Dict[str, set] = {}
    per_class_last_activity: Dict[str, datetime] = {}
    per_class_recent_answers: Dict[str, int] = {}
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    for event in events:
        cid = event.get("class_id")
        if not cid:
            continue
        entry = event.get("entry") or {}
        metrics = _extract_entry_metrics(entry)
        mastery_score = metrics.get("mastery_score")
        if mastery_score is None:
            continue
        per_class_scores.setdefault(cid, []).append(float(mastery_score))
        per_class_students.setdefault(cid, set()).add(event.get("student_id"))
        timestamp = _entry_timestamp(entry, event.get("session"))
        dt = parse_iso_datetime(timestamp) if timestamp else None
        if dt:
            if (cid not in per_class_last_activity) or dt > per_class_last_activity[cid]:
                per_class_last_activity[cid] = dt
            if dt >= week_ago:
                per_class_recent_answers[cid] = per_class_recent_answers.get(cid, 0) + 1

    payload = {}
    for cid, cls in classes.items():
        scores = per_class_scores.get(cid, [])
        avg_mastery = round(sum(scores) / len(scores), 1) if scores else None
        student_ids = list(cls.get("students") or [])
        total_students = len(student_ids)
        struggling = 0
        if scores and total_students:
            # approximate: count students below threshold using per student scores
            per_student: Dict[str, List[float]] = {}
            for event in events:
                if event.get("class_id") != cid:
                    continue
                metrics = _extract_entry_metrics(event.get("entry") or {})
                score = metrics.get("mastery_score")
                if score is None:
                    continue
                per_student.setdefault(event.get("student_id"), []).append(float(score))
            for sid in student_ids:
                s_scores = per_student.get(sid) or []
                if s_scores and (sum(s_scores) / len(s_scores)) < 60.0:
                    struggling += 1
        struggling_pct = round((struggling / total_students) * 100.0, 1) if total_students else 0.0
        payload[cid] = {
            "avg_mastery": avg_mastery,
            "struggling_percent": struggling_pct,
            "students": total_students,
            "recent_answers": per_class_recent_answers.get(cid, 0),
            "last_activity_at": per_class_last_activity.get(cid).isoformat().replace("+00:00", "Z")
            if per_class_last_activity.get(cid)
            else None,
        }

    return {"classes": payload}

# ---------- JSON Tests ----------
@app.get("/api/tests")
async def api_list_tests(request: Request):
    user = require_user(request)
    state = load_state()
    tests = list(state["tests"].values())
    if user["role"] == "teacher":
        tests = [t for t in tests if t["owner_id"] == user["id"]]
    return {"tests": [decorate_test_for_response(t, state) for t in tests]}


@app.get("/api/tests/my-tests")
async def api_my_tests(request: Request):
    user = require_user(request)
    state = load_state()
    tests = []
    for t in state["tests"].values():
        # Always restrict to tests owned by the current user
        if t.get("owner_id") != user["id"]:
            continue
        # For students, only expose their own practice tests (any status)
        # so they can see processing / failed items in the Practice UI.
        if user.get("role") == "student" and t.get("kind") != "practice":
            continue
        tests.append(decorate_test_for_response(t, state))
    return {"tests": tests}


@app.get("/api/teacher/engagement")
async def api_teacher_engagement(request: Request):
    user = require_user(request)
    if user.get("role") not in {"teacher", "admin"}:
        raise HTTPException(status_code=403, detail="Forbidden")
    state = load_state()
    classes = [
        cls for cls in (state.get("classes") or {}).values() if user["id"] in (cls.get("teachers") or [])
    ]
    students = {sid for cls in classes for sid in (cls.get("students") or [])}
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    xp_rows = state.get("gamification", {}).get("xp", {}) if isinstance(state.get("gamification"), dict) else {}
    total_xp = 0.0
    for sid in students:
        row = xp_rows.get(sid, {})
        for entry in row.get("xp_history", []):
            entry_date = parse_iso_datetime(entry.get("date"))
            if entry_date and entry_date >= week_ago:
                total_xp += float(entry.get("xp", 0.0) or 0.0)
    avg_xp_per_day = round(total_xp / 7.0, 1)
    streaks = state.get("gamification", {}).get("streaks", {})
    streak_participation = sum(1 for sid in students if streaks.get(sid, {}).get("current_streak", 0) >= 3)
    total_students = len(students)
    generated = False
    for cls in classes:
        if _ensure_auto_quests_for_class(state, cls.get("id") or cls.get("name") or ""):
            generated = True
    if generated:
        save_state(state)
        state = load_state()
    quest_completions = _count_quest_completions(state, set(students), since=week_ago) if students else 0
    return {
        "students": total_students,
        "avg_xp_per_day": avg_xp_per_day,
        "streak_participation": streak_participation,
        "quests_completed": quest_completions,
    }


def _class_leaderboard_payload(state: Dict[str, Any], class_id: str) -> Dict[str, Any]:
    cls = state.get("classes", {}).get(class_id) or {}
    config = _ensure_class_leaderboard_config(cls)
    gam_cfg = _get_gamification_config(state)
    enabled = bool(gam_cfg.get("leaderboards_enabled", True)) and bool(config.get("enabled", True))
    entries: List[Dict[str, Any]] = []
    if enabled:
        entries = _class_leaderboard_entries(state, class_id, config)
    return {"config": config, "entries": entries, "enabled": enabled}


def _class_leaderboard_auth(user: Dict[str, Any], cls: Dict[str, Any]) -> None:
    if user.get("role") == "teacher":
        if user.get("id") not in (cls.get("teachers") or []):
            raise HTTPException(status_code=403, detail="Forbidden")
    elif user.get("role") == "student":
        if user.get("id") not in (cls.get("students") or []):
            raise HTTPException(status_code=403, detail="Forbidden")
    elif user.get("role") not in {"admin", "teacher", "student"}:
        raise HTTPException(status_code=403, detail="Forbidden")


@app.get("/api/classes/{class_id}/leaderboard")
async def api_get_class_leaderboard(class_id: str, request: Request):
    user = require_user(request)
    state = load_state()
    cls = state.get("classes", {}).get(class_id)
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found.")

    _class_leaderboard_auth(user, cls)
    payload = _class_leaderboard_payload(state, class_id)
    state["classes"][class_id] = state.get("classes", {}).get(class_id) or cls
    save_state(state)
    return payload


@app.put("/api/classes/{class_id}/leaderboard")
async def api_update_class_leaderboard(class_id: str, request: Request, payload: Dict[str, Any] = Body(...)):
    user = require_user(request)
    state = load_state()
    cls = state.get("classes", {}).get(class_id)
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found.")

    _class_leaderboard_auth(user, cls)
    config = _ensure_class_leaderboard_config(cls)
    if "enabled" in payload:
        config["enabled"] = bool(payload.get("enabled"))
    if "anonymous" in payload:
        config["anonymous"] = bool(payload.get("anonymous"))
    if "focus" in payload and payload.get("focus") in {"xp", "improvement"}:
        config["focus"] = payload.get("focus")
    if "show_top_improvers" in payload:
        config["show_top_improvers"] = bool(payload.get("show_top_improvers"))
    if "limit" in payload and isinstance(payload.get("limit"), (int, float)):
        config["limit"] = max(1, int(payload.get("limit")))

    state["classes"][class_id] = cls
    save_state(state)
    payload = _class_leaderboard_payload(state, class_id)
    return payload

@app.get("/api/tests/{test_id}/mastery-report")
async def api_get_mastery_report(
    test_id: str,
    student_id: str,
    format: str = "html",
    request: Request = None,
):
    """Per-student mastery summary for a given test."""
    user = require_user(request)
    state = load_state()
    # Access control
    if user["role"] not in {"teacher", "admin"} and user["id"] != student_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    found = _find_assignment_session_for_student(test_id, student_id, state)
    session = {}
    assignment = {}
    test = state["tests"].get(test_id, {})

    if found:
        session = found["session"]
        test = found["test"] or test
        assignment = found["assignment"] or {}
    # fallback to practice history if this is a practice test owned by student
    if not session and test.get("kind") == "practice":
        practice_hist = state.get("practice_results", {}).get(student_id, {})
        session = practice_hist.get(test_id) or {}

    strengths, weaknesses = _summarize_mastery_from_session(session)
    answered = session.get("answered", [])
    correct = int(session.get("correct", 0))
    limit = int(session.get("limit") or len(answered) or 0)
    percent = round(100.0 * correct / limit, 1) if limit else None

    report = {
        "test": {"id": test.get("id"), "title": test.get("title") or "Untitled"},
        "student": {
            "id": student_id,
            "name": state["users"].get(student_id, {}).get("full_name") or state["users"].get(student_id, {}).get("email"),
        },
        "assignment_id": assignment.get("id"),
        "score": correct,
        "limit": limit,
        "percent": percent,
        "strengths": strengths,
        "weaknesses": weaknesses,
    }

    if format == "json":
        return JSONResponse(content=report)

    # Styled HTML to match app identity
    strengths_html = "".join([f"<span class='chip chip-good'>{s}</span>" for s in strengths]) or "<span class='muted'>None</span>"
    weaknesses_html = "".join([f"<span class='chip chip-warn'>{w}</span>" for w in weaknesses]) or "<span class='muted'>None</span>"
    html = f"""
    <html>
      <head>
        <title>Mastery Report</title>
        <style>
          body {{
            font-family: 'Inter', system-ui, -apple-system, sans-serif;
            background: radial-gradient(circle at 10% 20%, #E3EBFF 25%, transparent 25%), linear-gradient(135deg, #F5F7FB, #FFFFFF);
            color: #0F172A;
            padding: 32px;
          }}
          .card {{
            background: #FFFFFF;
            border-radius: 20px;
            padding: 24px;
            box-shadow: 0 10px 40px rgba(65,105,225,0.08);
            max-width: 720px;
            margin: 0 auto;
          }}
          h1 {{ margin: 0 0 8px 0; font-size: 26px; }}
          h2 {{ margin: 16px 0 8px 0; font-size: 18px; color: #475569; }}
          .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin: 16px 0; }}
          .stat {{ background: #F8FAFF; border-radius: 14px; padding: 14px; }}
          .label {{ font-size: 12px; color: #9CA3AF; margin: 0 0 4px 0; }}
          .value {{ font-size: 20px; margin: 0; }}
          .chips {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }}
          .chip {{ padding: 6px 10px; border-radius: 999px; font-size: 12px; }}
          .chip-good {{ background: rgba(34,197,94,0.12); color: #16A34A; }}
          .chip-warn {{ background: rgba(249,115,22,0.12); color: #F97316; }}
          .muted {{ color: #9CA3AF; font-size: 12px; }}
        </style>
      </head>
      <body>
        <div class="card">
          <h1>Mastery Report</h1>
          <p class="muted">Test: {report['test']['title']}</p>
          <p class="muted">Student: {report['student']['name']}</p>

          <div class="grid">
            <div class="stat">
              <p class="label">Score</p>
              <p class="value">{correct} / {limit or '--'}</p>
            </div>
            <div class="stat">
              <p class="label">Percent</p>
              <p class="value">{percent if percent is not None else '--'}%</p>
            </div>
          </div>

          <h2>Strengths</h2>
          <div class="chips">{strengths_html}</div>

          <h2>Areas to Improve</h2>
          <div class="chips">{weaknesses_html}</div>
        </div>
      </body>
    </html>
    """
    headers = {"Content-Disposition": "attachment; filename=mastery_report.html"} if format == "pdf" else None
    return HTMLResponse(content=html, headers=headers)


@app.post("/api/tests")
async def api_create_test(request: Request, payload: Dict[str, Any] = Body(...)):
    user = require_user(request)
    state = load_state()
    title = payload.get("title") or "Untitled"
    comment = payload.get("comment", "")
    question_limit = min(100, max(1, int(payload.get("questionLimit", 5) or 5)))
    pdf_b64 = payload.get("pdfBase64")
    api_key = payload.get("apiKey") or os.environ.get("CEREBRAS_API_KEY")
    model = payload.get("model", "llama3.1-8b")
    kind = payload.get("kind", "class_test")
    include_difficulty_raw = payload.get("includeDifficulty", payload.get("include_difficulty", True))
    include_difficulty = bool(include_difficulty_raw) if not isinstance(include_difficulty_raw, str) else include_difficulty_raw.strip().lower() not in {"0", "false", "no", "off"}
    goals = payload.get("goals") or payload.get("practice_goals") or {}

    if not pdf_b64:
        raise HTTPException(status_code=400, detail="Missing PDF.")
    if not api_key:
        raise HTTPException(status_code=400, detail="Missing Cerebras API key (apiKey or CEREBRAS_API_KEY env var).")

    job_id = uuid.uuid4().hex
    job_dir = DATA_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    safe_name = sanitize_filename(title, default="quiz")
    pdf_filename = safe_name if safe_name.lower().endswith(".pdf") else f"{safe_name}.pdf"
    pdf_path = job_dir / pdf_filename
    try:
        pdf_path.write_bytes(base64.b64decode(pdf_b64))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid PDF data.")
    source_files: List[Path] = [pdf_path]

    test_id = uuid.uuid4().hex
    state["tests"][test_id] = {
        "id": test_id,
        "owner_id": user["id"],
        "title": title,
        "comment": comment,
        "job_id": job_id,
        "pdf_filename": pdf_filename,
        "source_files": [pdf_filename],
        "created_at": iso_utc_now(),
        # Treat class_test like practice for processing so it flows immediately to ready
        "status": "processing",
        "paths": {},
        "log": [],
        "kind": kind,
        "limit": question_limit,
        "include_difficulty": include_difficulty,
        "model": model,
        "pipeline": {"status": "running", "started_at": iso_utc_now(), "steps": []},
        "practice_goals": goals if isinstance(goals, dict) else {},
        "artifacts_persisted": False,
    }
    save_state(state)

    def worker():
        try:
            log_fn = lambda msg: append_test_log(test_id, msg)
            append_test_log(test_id, "Starting pipeline...")
            pipeline_metrics: Dict[str, Any] = {}
            paths = run_pipeline(
                job_dir,
                source_files,
                api_key,
                model,
                include_difficulty=include_difficulty,
                question_limit=question_limit,
                metrics_out=pipeline_metrics,
                log_fn=log_fn,
            )
            st = load_state()
            test = st["tests"][test_id]
            test["paths"] = paths
            pipeline_metrics.setdefault("model", model)
            test["pipeline"] = pipeline_metrics
            # verify artifacts exist on disk
            quiz_json_path = paths.get("quiz_json")
            quiz_pdf_path = paths.get("quiz_pdf")
            if not quiz_json_path or not Path(quiz_json_path).exists():
                test["status"] = "failed"
                test["error"] = "Quiz JSON missing after pipeline."
                append_test_log(test_id, "Error: Quiz JSON missing after pipeline.")
                st["tests"][test_id] = test
                save_state(st)
                return
            # verify questions were generated; if not, mark as failed to avoid stuck pending_review with empty quiz
            has_questions = _test_has_questions(test_id, st)
            if not has_questions:
                test["status"] = "failed"
                test["error"] = "No questions generated (LLM quota or content issue)."
                append_test_log(test_id, "Error: No questions generated.")
            else:
                if DATABASE_URL:
                    try:
                        _persist_test_artifacts_from_paths(test_id, paths=paths, source_pdf_path=pdf_path)
                        append_test_log(test_id, "Saved quiz artifacts to database.")
                        test["artifacts_persisted"] = True
                    except Exception as exc:
                        append_test_log(test_id, f"Warning: Failed to persist quiz artifacts to database: {exc}")

                test_kind = (st["tests"].get(test_id) or {}).get("kind") or "class_test"
                if test_kind == "class_test":
                    test["status"] = "pending_review"
                    test["error"] = ""
                    append_test_log(test_id, "Pipeline complete. Awaiting admin approval.")
                else:
                    test["status"] = "ready"
                    test["error"] = ""
                    append_test_log(test_id, "Pipeline complete.")
            # attach quality metrics if quiz is readable
            try:
                quiz_data = _get_test_quiz(test_id, st)
                test["quality"] = _compute_test_quality(quiz_data)
            except Exception:
                test["quality"] = None
            st["tests"][test_id] = test
            update_model_meta(st, model)
            save_state(st)
        except Exception as exc:
            st = load_state()
            test = st["tests"].get(test_id, {})
            test["status"] = "failed"
            test["error"] = str(exc)
            pipeline = test.get("pipeline") or {}
            pipeline.setdefault("status", "failed")
            pipeline.setdefault("completed_at", iso_utc_now())
            test["pipeline"] = pipeline
            st["tests"][test_id] = test
            append_test_log(test_id, f"Error: {exc}")
            save_state(st)

    threading.Thread(target=worker, daemon=True).start()
    # Return the newly created test metadata immediately so the UI can track it.
    st = load_state()
    test = st["tests"][test_id]
    return {"test": decorate_test_for_response(test, st), "success": True, "log": test.get("log", [])}
    
@app.post("/api/tests/approve")
async def api_approve_test(request: Request, payload: Dict[str, Any] = Body(...)):
    admin = require_user(request)
    require_role(admin, "admin")
    test_id = payload.get("test_id")
    class_id = payload.get("class_id")
    state = load_state()
    test = state["tests"].get(test_id)
    if not test:
        raise HTTPException(status_code=400, detail="Test not found.")
    cls = state["classes"].get(class_id)
    if not cls:
        raise HTTPException(status_code=400, detail="Class not found.")
    assignment_id = uuid.uuid4().hex
    state["assignments"][assignment_id] = {
        "id": assignment_id,
        "test_id": test_id,
        "class_id": class_id,
        "students": list(cls.get("students", [])),
        "status": {},
        "created_at": iso_utc_now(),
        "sessions": {},
        "completed_at": {},
    }
    test["status"] = "ready"
    state["tests"][test_id] = test
    append_audit_log(
        state,
        actor_id=admin.get("id"),
        action="test_approved",
        target_type="test",
        target_id=test_id,
        details={"class_id": class_id},
    )
    save_state(state)
    return {"success": True, "assignment_id": assignment_id}


@app.post("/api/tests/assign")
async def api_assign_test_to_class(request: Request, payload: Dict[str, Any] = Body(...)):
    """
    Assign an existing READY class test to a class.

    - Admins can always assign.
    - Teachers can assign only if `config.teacher_can_assign` is enabled and they teach the class.
    """
    user = require_user(request)
    test_id = payload.get("test_id")
    class_id = payload.get("class_id")
    if not test_id or not class_id:
        raise HTTPException(status_code=400, detail="Missing test_id or class_id.")

    state = load_state()
    test = state["tests"].get(test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Test not found.")
    if test.get("kind") != "class_test":
        raise HTTPException(status_code=400, detail="Only class tests can be assigned to classes.")
    if test.get("status") != "ready":
        raise HTTPException(status_code=400, detail="Test is not ready.")

    cls = state["classes"].get(class_id)
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found.")

    # Idempotency: don't create duplicate assignments for the same test/class.
    assignments = state.get("assignments", {})
    existing_id = next(
        (
            aid
            for aid, a in assignments.items()
            if a.get("test_id") == test_id and a.get("class_id") == class_id
        ),
        None,
    )
    if existing_id:
        existing = assignments.get(existing_id) or {}
        # Keep roster up-to-date by unioning current class students.
        existing_students = set(existing.get("students") or [])
        current_students = set(cls.get("students") or [])
        merged = list(existing_students | current_students)
        if merged != (existing.get("students") or []):
            existing["students"] = merged
            assignments[existing_id] = existing
            state["assignments"] = assignments
            save_state(state)
        return {"success": True, "assignment_id": existing_id, "already_assigned": True}

    if user.get("role") == "teacher":
        cfg = state.get("config") or {}
        if not isinstance(cfg, dict) or not cfg.get("teacher_can_assign", False):
            raise HTTPException(status_code=403, detail="Teacher assignment is disabled by admin.")
        if test.get("owner_id") != user.get("id"):
            raise HTTPException(status_code=403, detail="You can only assign tests you created.")
        if user.get("id") not in (cls.get("teachers") or []):
            raise HTTPException(status_code=403, detail="You are not assigned to this class.")
    elif user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")

    assignment_id = uuid.uuid4().hex
    state["assignments"][assignment_id] = {
        "id": assignment_id,
        "test_id": test_id,
        "class_id": class_id,
        "students": list(cls.get("students", [])),
        "status": {},
        "created_at": iso_utc_now(),
        "sessions": {},
        "completed_at": {},
    }
    append_audit_log(
        state,
        actor_id=user.get("id"),
        action="test_assigned",
        target_type="test",
        target_id=test_id,
        details={"class_id": class_id},
    )
    save_state(state)
    return {"success": True, "assignment_id": assignment_id}


@app.get("/api/tests/{test_id}/assigned-classes")
async def api_get_test_assigned_classes(test_id: str, request: Request):
    """
    Return the list of classes this test is currently assigned to (via assignments).

    - Admin can view any test.
    - Teacher can view tests they own.
    """
    user = require_user(request)
    state = load_state()
    test = state["tests"].get(test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Test not found.")

    if user.get("role") == "teacher" and test.get("owner_id") != user.get("id"):
        raise HTTPException(status_code=403, detail="Forbidden")
    if user.get("role") not in {"admin", "teacher"}:
        raise HTTPException(status_code=403, detail="Forbidden")

    results: List[Dict[str, Any]] = []
    seen = set()
    for aid, a in (state.get("assignments") or {}).items():
        if a.get("test_id") != test_id:
            continue
        cid = a.get("class_id")
        if cid:
            cls = state.get("classes", {}).get(cid, {}) or {}
            name = cls.get("name") or cid
            key = ("id", cid)
            if key in seen:
                continue
            seen.add(key)
            results.append(
                {
                    "assignment_id": aid,
                    "class_id": cid,
                    "class_name": name,
                    "student_count": len(cls.get("students") or []),
                }
            )
        else:
            cname = a.get("class_name")
            if not cname:
                continue
            key = ("name", cname)
            if key in seen:
                continue
            seen.add(key)
            results.append(
                {
                    "assignment_id": aid,
                    "class_id": None,
                    "class_name": cname,
                    "student_count": len(a.get("students") or []),
                }
            )

    return {"classes": results}


# ---------- JSON Assignments ----------
@app.get("/api/assignments/my-assignments")
async def api_my_assignments(request: Request):
    user = require_user(request)
    state = load_state()
    results: List[Dict[str, Any]] = []

    for aid, a in (state.get("assignments") or {}).items():
        test_id = a.get("test_id")
        test = state.get("tests", {}).get(test_id) if test_id else None
        if not test:
            continue

        class_id = a.get("class_id")
        cls = state.get("classes", {}).get(class_id) if class_id else None

        in_class = bool(cls and user["id"] in (cls.get("students") or []))
        in_students_list = user["id"] in (a.get("students") or [])
        if not (in_class or in_students_list):
            continue

        # Human-friendly class / teacher labels
        class_name = (cls.get("name") if cls else None) or a.get("class_name") or class_id or "Class"
        teacher_id = None
        if cls and (cls.get("teachers") or []):
            teacher_id = (cls.get("teachers") or [None])[0]
        teacher_id = teacher_id or test.get("owner_id")
        teacher_user = state.get("users", {}).get(teacher_id, {}) if teacher_id else {}
        teacher_name = (
            teacher_user.get("full_name")
            or teacher_user.get("fullName")
            or teacher_user.get("email")
            or "Teacher"
        )

        # Quiz readiness
        ready = True
        error = ""
        try:
            quiz = _get_assignment_quiz(aid, state)
            if not _flatten_quiz_questions(quiz):
                ready = False
                error = "Quiz has no questions yet."
        except HTTPException as exc:
            ready = False
            error = exc.detail if isinstance(exc.detail, str) else "Quiz not ready."

        session = (a.get("sessions") or {}).get(user["id"]) if isinstance(a.get("sessions"), dict) else None
        strengths, weaknesses = _summarize_mastery_from_session(session)

        status_map = a.get("status") if isinstance(a.get("status"), dict) else {}
        status = (status_map.get(user["id"]) or "pending").lower()
        if session and status != "completed":
            status = "in_progress"

        total_questions = None
        try:
            total_questions = int((session or {}).get("limit") or test.get("limit") or 0)
        except Exception:
            total_questions = 0

        answered_count = len((session or {}).get("answered") or []) if session else 0
        progress = None
        if session and total_questions:
            progress = int(round(100.0 * answered_count / total_questions))

        final_score = None
        if session and total_questions and status == "completed":
            correct = int((session or {}).get("correct") or 0)
            final_score = round(100.0 * correct / total_questions, 1)

        created_at = a.get("created_at") or a.get("createdAt") or infer_test_created_at(test) or ""
        due_at = a.get("due_at") or a.get("dueDate") or created_at
        completed_at = None
        if session and session.get("completed_at"):
            completed_at = session.get("completed_at")
        elif isinstance(a.get("completed_at"), dict):
            completed_at = a.get("completed_at", {}).get(user["id"])

        # timeSpent (minutes) from started_at/completed_at if available
        time_spent = None
        started_dt = parse_iso_datetime((session or {}).get("started_at")) if session else None
        ended_dt = parse_iso_datetime((session or {}).get("completed_at")) if session else None
        if started_dt and ended_dt:
            time_spent = round((ended_dt - started_dt).total_seconds() / 60.0, 1)
        elif started_dt and status == "in_progress":
            time_spent = round((datetime.now(timezone.utc) - started_dt).total_seconds() / 60.0, 1)

        test_payload = decorate_test_for_response(test, state)
        # Keep teacher name visible even if test owner isn't the class teacher.
        test_payload.setdefault("ownerName", teacher_name)
        quality = test_payload.get("quality") or {}
        concept_dist = quality.get("concept_distribution") or {}
        top_concepts = [c for c, _ in sorted(concept_dist.items(), key=lambda item: item[1], reverse=True)[:5]]

        results.append(
            {
                "id": a.get("id") or aid,
                "assignment_id": a.get("id") or aid,
                "test_id": test_id,
                "class_id": class_id,
                "class_name": class_name,
                "teacher_name": teacher_name,
                "createdAt": created_at,
                "dueDate": due_at,
                "completedAt": completed_at,
                "status": status,
                "ready": ready,
                "error": error,
                "progress": progress,
                "finalScore": final_score,
                "timeSpent": time_spent,
                "totalQuestions": total_questions,
                "strengths": strengths,
                "weaknesses": weaknesses,
                "concepts": top_concepts,
                "test": test_payload,
            }
        )

    return {"assignments": results}


@app.get("/api/assignments/results")
async def api_assignment_results(request: Request):
    """Per-student assignment results (for teachers/admin only)."""
    user = require_user(request)
    state = load_state()
    if user.get("role") not in {"teacher", "admin"}:
        raise HTTPException(status_code=403, detail="Forbidden")

    is_admin = user["role"] == "admin"
    results: List[Dict[str, Any]] = []

    for aid, a in state["assignments"].items():
        test = state["tests"].get(a.get("test_id"))
        cls = state["classes"].get(a.get("class_id"))
        if not test:
            continue
        if not is_admin:
            # Teacher can see assignments for tests they own or classes they teach
            owns_test = test.get("owner_id") == user["id"]
            teaches_class = cls and user["id"] in cls.get("teachers", [])
            if not (owns_test or teaches_class):
                continue

        sessions = a.get("sessions", {})
        status_map = a.get("status", {})
        students = list(cls.get("students", [])) if cls else list(sessions.keys())
        per_students: List[Dict[str, Any]] = []
        for sid in students:
            stu = state["users"].get(sid, {})
            session = sessions.get(sid)
            strengths, weaknesses = _summarize_mastery_from_session(session)
            score = None
            limit = None
            percent = None
            if session:
                score = int(session.get("correct", 0))
                limit = int(session.get("limit") or len(session.get("answered", [])) or 0)
                if limit:
                    percent = round(100.0 * score / limit, 1)
            per_students.append(
                {
                    "student_id": sid,
                    "student_name": stu.get("full_name") or stu.get("fullName") or stu.get("email", ""),
                    "status": status_map.get(sid, "pending"),
                    "score": score,
                    "limit": limit,
                    "percent": percent,
                    "strengths": strengths,
                    "weaknesses": weaknesses,
                }
            )
        results.append(
            {
                "assignment_id": aid,
                "test": {"id": test.get("id"), "title": test.get("title")},
                "class": {"id": cls.get("id") if cls else None, "name": cls.get("name") if cls else None},
                "results": per_students,
            }
        )

    return {"assignments": results}


# ---------- Student insights ----------
@app.get("/api/student/overview")
async def api_student_overview(request: Request):
    user = require_user(request)
    if user.get("role") != "student":
        raise HTTPException(status_code=403, detail="Forbidden")
    state = load_state()

    concept_stats = _build_student_concept_stats(state, user["id"])
    per_concept = concept_stats.get("per_concept") or []
    strong = [c for c in per_concept if c.get("avg_mastery") is not None and c.get("avg_mastery") >= 80][:3]
    weak = [c for c in per_concept if c.get("avg_mastery") is not None and c.get("avg_mastery") <= 65][:3]

    progress = _build_student_progress(state, user["id"], days=7)
    streak = _build_student_streak(state, user["id"])
    continue_item = _find_student_continue_item(state, user["id"])

    conf = concept_stats.get("overall_confidence")
    if conf is None:
        conf_label = "Unknown"
    elif conf >= 0.75:
        conf_label = "High"
    elif conf >= 0.55:
        conf_label = "Moderate"
    else:
        conf_label = "Low"

    return {
        "mastery": {
            "overall": concept_stats.get("overall_mastery"),
            "strong": strong,
            "weak": weak,
        },
        "confidence": {
            "score": conf,
            "label": conf_label,
        },
        "streak": streak,
        "continue": continue_item,
        "progress": progress,
        "last_active_at": concept_stats.get("last_active_at"),
        "gamification": _get_gamification_status(state, user["id"]),
    }


@app.get("/api/student/plan")
async def api_student_plan(request: Request):
    user = require_user(request)
    if user.get("role") != "student":
        raise HTTPException(status_code=403, detail="Forbidden")
    state = load_state()
    return {"actions": _build_student_plan(state, user["id"])}


@app.get("/api/quests")
async def api_list_quests(request: Request, class_id: Optional[str] = None):
    user = require_user(request)
    state = load_state()
    classes_to_seed: List[str] = []
    if class_id:
        cls = (state.get("classes") or {}).get(class_id)
        if not cls:
            raise HTTPException(status_code=404, detail="Class not found.")
        if user.get("role") == "student":
            if user["id"] not in (cls.get("students") or []):
                raise HTTPException(status_code=403, detail="Forbidden")
        if user.get("role") == "teacher" and user["id"] not in (cls.get("teachers") or []):
            raise HTTPException(status_code=403, detail="Forbidden")
        if user.get("role") not in {"student", "teacher", "admin"}:
            raise HTTPException(status_code=403, detail="Forbidden")
        classes_to_seed.append(class_id)
    elif user.get("role") == "student":
        classes_to_seed.extend(_get_user_class_ids(state, user["id"]))

    created = False
    for cls_id in classes_to_seed:
        if _ensure_auto_quests_for_class(state, cls_id):
            created = True
    if created:
        save_state(state)

    quests = _collect_user_quests(state, user, class_id)
    return {"quests": quests}


@app.get("/api/gamification/status")
async def api_gamification_status(request: Request):
    user = require_user(request)
    state = load_state()
    return _get_gamification_status(state, user["id"])


@app.get("/api/student/practice/history")
async def api_student_practice_history(request: Request):
    user = require_user(request)
    if user.get("role") != "student":
        raise HTTPException(status_code=403, detail="Forbidden")
    state = load_state()
    results: List[Dict[str, Any]] = []
    history = (state.get("practice_results") or {}).get(user["id"], {}) if isinstance(state.get("practice_results"), dict) else {}

    for test_id, session in history.items():
        if not isinstance(session, dict):
            continue
        completed_at = session.get("completed_at")
        if not completed_at:
            continue
        test = state.get("tests", {}).get(test_id, {})
        strengths, weaknesses = _summarize_mastery_from_session(session)
        answered = session.get("answered", [])
        correct = int(session.get("correct", 0))
        limit = int(session.get("limit") or len(answered) or 0)
        score = round(100.0 * correct / limit, 1) if limit else None
        started_at = session.get("started_at")
        time_spent = None
        started_dt = parse_iso_datetime(started_at) if started_at else None
        completed_dt = parse_iso_datetime(completed_at) if completed_at else None
        if started_dt and completed_dt:
            time_spent = round((completed_dt - started_dt).total_seconds() / 60.0, 1)

        results.append(
            {
                "test_id": test_id,
                "title": test.get("title") or "Practice Quiz",
                "completed_at": completed_at,
                "score": score,
                "time_spent": time_spent,
                "strengths": strengths,
                "weaknesses": weaknesses,
                "question_count": limit,
            }
        )

    results.sort(key=lambda row: row.get("completed_at") or "", reverse=True)
    return {"sessions": results}


@app.get("/api/reports/insights")
async def api_reports_insights(request: Request, class_id: Optional[str] = None, test_id: Optional[str] = None):
    user = require_user(request)
    state = load_state()
    events = _iter_answer_events(state, include_practice=True)

    if user.get("role") == "teacher":
        teacher_classes = {
            cid for cid, cls in (state.get("classes") or {}).items() if user.get("id") in (cls.get("teachers") or [])
        }
        owned_tests = {t.get("id") for t in (state.get("tests") or {}).values() if t.get("owner_id") == user.get("id")}
        events = [
            e for e in events if (e.get("test_id") in owned_tests) or (e.get("class_id") in teacher_classes)
        ]
    elif user.get("role") == "student":
        events = [e for e in events if e.get("student_id") == user.get("id")]

    if class_id:
        events = [e for e in events if e.get("class_id") == class_id]
    if test_id:
        events = [e for e in events if e.get("test_id") == test_id]

    concept_stats: Dict[str, Dict[str, float]] = {}
    behavior = {"guessing": 0, "confusion": 0, "steady": 0, "fast_correct": 0, "slow_correct": 0}
    misconception_counts: Dict[str, int] = {}

    for event in events:
        entry = event.get("entry") or {}
        metrics = _extract_entry_metrics(entry)
        concept = _normalize_concept_label(metrics.get("position"))
        mastery_score = metrics.get("mastery_score")
        stat = concept_stats.setdefault(concept, {"mastery_sum": 0.0, "count": 0.0, "correct": 0.0})
        if mastery_score is not None:
            stat["mastery_sum"] += float(mastery_score)
            stat["count"] += 1.0
        if metrics.get("is_correct"):
            stat["correct"] += 1.0

        time_ratio = metrics.get("time_ratio")
        similarity = metrics.get("similarity")
        if metrics.get("is_correct"):
            if time_ratio is not None and time_ratio < 0.8:
                behavior["fast_correct"] += 1
            elif time_ratio is not None and time_ratio > 1.3:
                behavior["slow_correct"] += 1
            else:
                behavior["steady"] += 1
        else:
            if time_ratio is not None and similarity is not None and time_ratio < 0.7 and similarity < 0.3:
                behavior["guessing"] += 1
                misconception_counts[concept] = misconception_counts.get(concept, 0) + 1
            elif time_ratio is not None and time_ratio > 1.3:
                behavior["confusion"] += 1
                misconception_counts[concept] = misconception_counts.get(concept, 0) + 1
            else:
                behavior["confusion"] += 1
                misconception_counts[concept] = misconception_counts.get(concept, 0) + 1

    concept_payload = []
    for concept, stat in concept_stats.items():
        count = stat.get("count", 0.0) or 0.0
        if count <= 0:
            continue
        avg_mastery = stat["mastery_sum"] / count
        accuracy = stat["correct"] / count
        concept_payload.append(
            {
                "concept": concept,
                "avg_mastery": round(avg_mastery, 1),
                "accuracy": round(accuracy * 100.0, 1),
                "attempts": int(count),
            }
        )

    concept_payload.sort(key=lambda row: row["avg_mastery"])
    misconceptions = [
        {"concept": concept, "count": count}
        for concept, count in sorted(misconception_counts.items(), key=lambda item: item[1], reverse=True)
    ][:8]

    return {
        "concept_mastery": concept_payload[:12],
        "misconceptions": misconceptions,
        "behavior": behavior,
        "total_events": len(events),
    }


# ---------- JSON Sessions (adaptive) ----------
@app.post("/api/sessions/start")
async def api_sessions_start(payload: Dict[str, Any] = Body(...), request: Request = None):
    user = require_user(request)
    if user["role"] != "student":
        raise HTTPException(status_code=403, detail="Forbidden")
    assignment_id = payload.get("assignment_id")
    state = load_state()
    assignment = state["assignments"].get(assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    class_id = assignment.get("class_id")
    if class_id and user["id"] not in state["classes"].get(class_id, {}).get("students", []):
        raise HTTPException(status_code=403, detail="Not part of this class.")
    quiz = _get_assignment_quiz(assignment_id, state)
    flat: List[Dict[str, Any]] = []

    def collect(node, trail):
        if isinstance(node, dict):
            t = node.get("title")
            new = trail + [t] if t else trail
            if "questions" in node and node["questions"]:
                for q in node["questions"]:
                    flat.append(
                        {
                            "id": q.get("id") or q.get("question", ""),
                            "question": q.get("question", ""),
                            "options": q.get("options", []),
                            "correct_answer": q.get("correct_answer", ""),
                            "difficulty": q.get("difficulty", "medium"),
                            "position": "/".join([s for s in new if s]),
                        }
                    )
            for k, v in node.items():
                if k not in {"title", "questions"}:
                    collect(v, new + [k])
        elif isinstance(node, list):
            for item in node:
                collect(item, trail)

    collect(quiz, [])
    if not flat:
        raise HTTPException(status_code=400, detail="No questions in quiz.")
    import random

    first = random.choice(flat)
    test = state["tests"].get(assignment["test_id"], {})
    requested_limit_raw = test.get("limit", test.get("questionLimit", 5))
    try:
        requested_limit = int(requested_limit_raw or 5)
    except (TypeError, ValueError):
        requested_limit = 5
    q_limit = max(1, min(requested_limit, len(flat)))
    session = {
        "asked": [first.get("id") or first.get("question", "")],
        "answered": [],
        "limit": q_limit,
        "correct": 0,
        "current": first,
        "started_at": iso_utc_now(),
        "current_started_at": iso_utc_now(),
    }
    assignment.setdefault("created_at", iso_utc_now())
    assignment.setdefault("status", {})[user["id"]] = "in_progress"
    assignment.setdefault("sessions", {})[user["id"]] = session
    state["assignments"][assignment_id] = assignment
    save_state(state)
    return {
        "success": True,
        "session": {"id": assignment_id, "score": 0},
        "test_id": assignment.get("test_id"),
        "question": first,
        "questionNumber": 1,
        "totalQuestions": q_limit,
    }


@app.post("/api/sessions/submit-answer")
async def api_sessions_submit(payload: Dict[str, Any] = Body(...), request: Request = None):
    user = require_user(request)
    if user["role"] != "student":
        raise HTTPException(status_code=403, detail="Forbidden")
    assignment_id = payload.get("assignment_id")
    student_answer = payload.get("student_answer", "")
    state = load_state()
    assignment = state["assignments"].get(assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    session = assignment.get("sessions", {}).get(user["id"])
    if not session or not session.get("current"):
        raise HTTPException(status_code=400, detail="Session not started.")

    quiz = _get_assignment_quiz(assignment_id, state)
    evaluator = _load_module(EVALUATOR_PATH, "answer_evaluator")
    mastery_mod = _load_module(MASTERY_PATH, "mastery_scorer")
    recommender_mod = _load_module(RECOMMENDER_PATH, "question_recommender")

    current = session["current"]
    current_id = current.get("id") or current.get("question", "")
    time_taken = _to_float(payload.get("time_taken") or payload.get("time_taken_seconds"))
    if time_taken is None:
        started_at = parse_iso_datetime(session.get("current_started_at"))
        if started_at:
            time_taken = (datetime.now(timezone.utc) - started_at).total_seconds()
        else:
            time_taken = 0.0
    expected_time = _to_float(payload.get("expected_time")) or 20.0
    evaluation = evaluator.evaluate_answer(
        question=current["question"],
        correct_answer=current.get("correct_answer", ""),
        student_answer=student_answer,
        time_taken=time_taken,
        expected_time=expected_time,
        difficulty=current.get("difficulty", "medium"),
        position=current.get("position", ""),
    )
    evaluation["question_id"] = current_id
    mastery = mastery_mod.calculate_mastery(evaluation)

    if evaluation["metrics"]["is_correct"]:
        session["correct"] += 1
    answered_at = iso_utc_now()
    session["answered"].append(
        {
            "id": current_id,
            "question": current["question"],
            "evaluation": evaluation,
            "mastery": mastery,
            "answered_at": answered_at,
            "time_taken": time_taken,
            "expected_time": expected_time,
        }
    )
    session["last_answered_at"] = answered_at

    xp_response = None
    gam_cfg = _get_gamification_config(state)
    if gam_cfg.get("enabled", True):
        difficulty = (current.get("difficulty") or "medium").lower()
        multiplier = gam_cfg.get("difficulty_multipliers", {}).get(difficulty, 1.0)
        correct = bool(evaluation["metrics"].get("is_correct"))
        base = float(gam_cfg.get("xp_base", 10))
        xp_base = base * multiplier * (1.0 if correct else 0.3)
        event_key = f"testQuestion:{assignment_id}:{user['id']}:{current_id}:{len(session['answered'])}"
        xp_response = _award_xp(
            state,
            user["id"],
            event_key,
            xp_base,
            metadata={
                "difficulty": difficulty,
                "correct": correct,
                "date": answered_at,
                "source_type": "test_question",
                "event_type": "question",
                "concept": _normalize_concept_label(current.get("position")),
            },
        )
        if xp_response:
            _update_streak(state, user["id"], answered_at)
        save_state(state)

    # stop if limit reached
    if len(session["answered"]) >= session["limit"]:
        session["completed_at"] = iso_utc_now()
        assignment["sessions"][user["id"]] = session
        assignment.setdefault("status", {})[user["id"]] = "completed"
        assignment.setdefault("completed_at", {})[user["id"]] = session["completed_at"]
        state["assignments"][assignment_id] = assignment
        gam = state.setdefault("gamification", {})
        xp_data = gam.setdefault("xp", {}).get(user["id"], {})
        best_scores = xp_data.setdefault("best_scores", {})
        percent = None
        if session.get("limit"):
            percent = round(100.0 * session.get("correct", 0) / session.get("limit"), 1)
        prev_best = best_scores.get(assignment_id, 0.0)
        improvement = percent - prev_best if percent is not None else 0.0
        bonus_awarded = 0.0
        cfg = _get_gamification_config(state)
        if percent is not None and percent > prev_best:
            delta = percent - prev_best
            bonus_multiplier = float(cfg.get("improvement_bonus_multiplier", 2.0) or 2.0)
            bonus_amount = delta * bonus_multiplier
            bonus_event = f"testImprovement:{assignment_id}:{user['id']}:{session['completed_at']}"
            bonus_result = _award_xp(
                state,
                user["id"],
                bonus_event,
                bonus_amount,
                metadata={"type": "improvement", "percent": percent, "date": session["completed_at"], "source_type": "test_completion", "event_type": "improvement"},
            )
            if bonus_result:
                bonus_awarded = bonus_result["xp_awarded"]
                best_scores[assignment_id] = percent
        streak_info = state.get("gamification", {}).get("streaks", {}).get(user["id"], {})
        context = {
            "streak": streak_info.get("current_streak", 0),
            "practice_questions": session.get("limit", 0),
            "percent": percent or 0,
            "difficulty": current.get("difficulty", "medium"),
            "max_mastery": max(
                (
                    _to_float(entry.get("mastery", {}).get("mastery_score"))
                    for entry in session.get("answered", [])
                    if _to_float(entry.get("mastery", {}).get("mastery_score")) is not None
                ),
                default=0,
            ),
            "improvement": improvement,
        }
        achievements_unlocked = _evaluate_achievements(state, user["id"], context)
        save_state(state)
        xp_response_final = gam.get("xp", {}).get(user["id"], {})
        return {
            "success": True,
            "done": True,
            "test_id": assignment.get("test_id"),
            "evaluation": evaluation,
            "mastery": mastery,
            "score": session["correct"],
            "answered": len(session["answered"]),
            "limit": session["limit"],
            "xp_awarded": xp_response["xp_awarded"] if xp_response else 0,
            "xp_total": xp_response_final.get("xp_total"),
            "level": xp_response_final.get("level"),
            "bonus_xp": bonus_awarded,
            "achievements_unlocked": achievements_unlocked,
        }

    exclude = [(a.get("id") or a.get("question") or "") for a in session.get("answered", [])] + (session.get("asked", []) or [])
    try:
        recommendation = recommender_mod.recommend_question(
            quiz=quiz,
            evaluation=evaluation,
            mastery=mastery,
            override_score=None,
            exclude_questions=exclude,
        )
    except Exception:
        recommendation = {}
    next_q = recommendation.get("selected_question")
    if not next_q:
        # Fallback: pick the first available question in the quiz by id.
        exclude_set = set(exclude)
        flat_all = _flatten_quiz_for_adaptive(quiz)
        candidate = next((q for q in flat_all if (q.get("id") or q.get("question", "")) not in exclude_set), None)
        if candidate:
            session["current"] = candidate
            session["current_started_at"] = iso_utc_now()
            session.setdefault("asked", []).append(session["current"].get("id") or session["current"].get("question", ""))
            assignment.setdefault("status", {})[user["id"]] = "in_progress"
            assignment["sessions"][user["id"]] = session
            state["assignments"][assignment_id] = assignment
            save_state(state)
            xp_info = state.get("gamification", {}).get("xp", {}).get(user["id"], {})
            return {
                "success": True,
                "done": False,
                "test_id": assignment.get("test_id"),
                "evaluation": evaluation,
                "mastery": mastery,
                "next_question": session["current"],
                "remaining": session["limit"] - len(session["answered"]),
                "answered": len(session["answered"]),
                "score": session["correct"],
                "limit": session["limit"],
                "note": "Fallback selection used",
                "xp_awarded": xp_response["xp_awarded"] if xp_response else 0,
                "xp_total": xp_info.get("xp_total"),
                "level": xp_info.get("level"),
            }
        assignment.setdefault("status", {})[user["id"]] = "in_progress"
        assignment["sessions"][user["id"]] = session
        state["assignments"][assignment_id] = assignment
        save_state(state)
        xp_info = state.get("gamification", {}).get("xp", {}).get(user["id"], {})
        return {
            "success": True,
            "done": True,
            "test_id": assignment.get("test_id"),
            "evaluation": evaluation,
            "mastery": mastery,
            "score": session["correct"],
            "answered": len(session["answered"]),
            "limit": session["limit"],
            "note": "No more questions available",
            "xp_awarded": xp_response["xp_awarded"] if xp_response else 0,
            "xp_total": xp_info.get("xp_total"),
            "level": xp_info.get("level"),
        }

    session["current"] = {
        "id": next_q.get("id") or next_q.get("question", ""),
        "question": next_q.get("question", ""),
        "options": next_q.get("options", []),
        "correct_answer": next_q.get("correct_answer", ""),
        "difficulty": next_q.get("difficulty", "medium"),
        "position": recommendation.get("position", ""),
    }
    session["current_started_at"] = iso_utc_now()
    session.setdefault("asked", []).append(session["current"].get("id") or session["current"]["question"])
    assignment.setdefault("status", {})[user["id"]] = "in_progress"
    assignment["sessions"][user["id"]] = session
    state["assignments"][assignment_id] = assignment
    save_state(state)

    xp_info = state.get("gamification", {}).get("xp", {}).get(user["id"], {})
    return {
        "success": True,
        "done": False,
        "test_id": assignment.get("test_id"),
        "evaluation": evaluation,
        "mastery": mastery,
        "next_question": session["current"],
        "remaining": session["limit"] - len(session["answered"]),
        "answered": len(session["answered"]),
        "score": session["correct"],
        "limit": session["limit"],
        "xp_awarded": xp_response["xp_awarded"] if xp_response else 0,
        "xp_total": xp_info.get("xp_total"),
        "level": xp_info.get("level"),
    }


def _flatten_quiz_for_adaptive(quiz: Dict[str, Any]) -> List[Dict[str, Any]]:
    flat: List[Dict[str, Any]] = []

    def collect(node, trail):
        if isinstance(node, dict):
            title = node.get("title") or node.get("name")
            new_trail = trail + [title] if title else trail
            if "questions" in node and node["questions"]:
                for q in node["questions"]:
                    flat.append(
                        {
                            "id": q.get("id") or q.get("question", ""),
                            "question": q.get("question", ""),
                            "options": q.get("options", []),
                            "correct_answer": q.get("correct_answer", ""),
                            "difficulty": q.get("difficulty", "medium"),
                            "position": "/".join([s for s in new_trail if s]),
                        }
                    )
            for k, v in node.items():
                if k not in {"title", "name", "questions"}:
                    collect(v, new_trail + [k])
        elif isinstance(node, list):
            for item in node:
                collect(item, trail)

    collect(quiz, [])
    return flat


@app.post("/api/practice/start")
async def api_practice_start(payload: Dict[str, Any] = Body(...), request: Request = None):
    user = require_user(request)
    if user["role"] != "student":
        raise HTTPException(status_code=403, detail="Forbidden")
    test_id = payload.get("test_id") or payload.get("testId")
    state = load_state()
    test = state["tests"].get(str(test_id))
    if not test or test.get("kind") != "practice" or test.get("owner_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Practice test not found.")
    quiz = _get_test_quiz(str(test_id), state)
    flat = _flatten_quiz_for_adaptive(quiz)
    if not flat:
        raise HTTPException(status_code=400, detail="No questions in quiz.")
    import random

    first = random.choice(flat)
    requested_limit_raw = test.get("limit", test.get("questionLimit", 5))
    try:
        requested_limit = int(requested_limit_raw or 5)
    except (TypeError, ValueError):
        requested_limit = 5
    q_limit = max(1, min(requested_limit, len(flat)))
    session = {
        "asked": [first.get("id") or first.get("question", "")],
        "answered": [],
        "limit": q_limit,
        "correct": 0,
        "current": first,
        "started_at": iso_utc_now(),
        "current_started_at": iso_utc_now(),
    }
    state.setdefault("practice_sessions", {})
    state["practice_sessions"][f"{user['id']}:{test_id}"] = session
    # reset any previous practice history for this test/user
    state.setdefault("practice_results", {}).setdefault(user["id"], {}).pop(str(test_id), None)
    save_state(state)
    return {
        "success": True,
        "question": first,
        "questionNumber": 1,
        "totalQuestions": q_limit,
    }


@app.post("/api/practice/answer")
async def api_practice_answer(payload: Dict[str, Any] = Body(...), request: Request = None):
    user = require_user(request)
    if user["role"] != "student":
        raise HTTPException(status_code=403, detail="Forbidden")
    test_id = str(payload.get("test_id") or payload.get("testId"))
    student_answer = payload.get("student_answer", "") or payload.get("answer", "")
    state = load_state()
    key = f"{user['id']}:{test_id}"
    session = state.get("practice_sessions", {}).get(key)
    if not session or not session.get("current"):
        raise HTTPException(status_code=400, detail="Practice session not started.")

    quiz = _get_test_quiz(test_id, state)
    evaluator = _load_module(EVALUATOR_PATH, "answer_evaluator")
    mastery_mod = _load_module(MASTERY_PATH, "mastery_scorer")
    recommender_mod = _load_module(RECOMMENDER_PATH, "question_recommender")

    current = session["current"]
    current_id = current.get("id") or current.get("question", "")
    time_taken = _to_float(payload.get("time_taken") or payload.get("time_taken_seconds"))
    if time_taken is None:
        started_at = parse_iso_datetime(session.get("current_started_at"))
        if started_at:
            time_taken = (datetime.now(timezone.utc) - started_at).total_seconds()
        else:
            time_taken = 0.0
    expected_time = _to_float(payload.get("expected_time")) or 20.0
    evaluation = evaluator.evaluate_answer(
        question=current["question"],
        correct_answer=current.get("correct_answer", ""),
        student_answer=student_answer,
        time_taken=time_taken,
        expected_time=expected_time,
        difficulty=current.get("difficulty", "medium"),
        position=current.get("position", ""),
    )
    evaluation["question_id"] = current_id
    mastery = mastery_mod.calculate_mastery(evaluation)

    evidence: List[str] = []
    try:
        test = state.get("tests", {}).get(test_id) or {}
        if (
            str(test.get("kind") or "").lower() == "practice"
            and test.get("owner_id") == user["id"]
        ):
            paths = _resolve_quiz_paths(test)
            sidecar = _load_evidence_sidecar(paths.get("evidence_json"))
            if sidecar is None and DATABASE_URL:
                artifacts = _db_fetch_test_artifacts(test_id)
                sidecar_db = artifacts.get("evidence_json")
                if isinstance(sidecar_db, dict):
                    sidecar = sidecar_db
            evidence = _lookup_question_evidence(
                sidecar,
                question_id=str(current_id or ""),
                question_text=str(current.get("question") or ""),
            )
    except Exception:
        evidence = []

    if evaluation["metrics"]["is_correct"]:
        session["correct"] += 1
    answered_at = iso_utc_now()
    session["answered"].append(
        {
            "id": current_id,
            "question": current["question"],
            "evaluation": evaluation,
            "mastery": mastery,
            "answered_at": answered_at,
            "time_taken": time_taken,
            "expected_time": expected_time,
        }
    )
    session["last_answered_at"] = answered_at

    xp_response = None
    gam_cfg = _get_gamification_config(state)
    if gam_cfg.get("enabled", True):
        difficulty = (current.get("difficulty") or "medium").lower()
        multiplier = gam_cfg.get("difficulty_multipliers", {}).get(difficulty, 1.0)
        correct = bool(evaluation["metrics"].get("is_correct"))
        base = float(gam_cfg.get("xp_base", 10))
        xp_base = base * multiplier * (1.0 if correct else 0.3)
        event_key = f"practiceQuestion:{test_id}:{user['id']}:{current_id}:{len(session['answered'])}"
        xp_response = _award_xp(
            state,
            user["id"],
            event_key,
            xp_base,
            metadata={
                "difficulty": difficulty,
                "correct": correct,
                "date": answered_at,
                "source_type": "practice_question",
                "event_type": "question",
                "concept": _normalize_concept_label(current.get("position")),
            },
        )
        if xp_response:
            _update_streak(state, user["id"], answered_at)
        save_state(state)

    # helper to persist practice history
    def _persist():
        state.setdefault("practice_sessions", {})[key] = session
        state.setdefault("practice_results", {}).setdefault(user["id"], {})[test_id] = session
        save_state(state)

    # stop if limit reached
    if len(session["answered"]) >= session["limit"]:
        session["completed_at"] = iso_utc_now()
        _persist()
        gam = state.setdefault("gamification", {})
        xp_data = gam.setdefault("xp", {}).get(user["id"], {})
        best_scores = xp_data.setdefault("best_scores", {})
        percent = round(100.0 * session.get("correct", 0) / session.get("limit", 1), 1) if session.get("limit") else 0
        prev_best = best_scores.get(test_id, 0.0)
        improvement = percent - prev_best
        bonus_awarded = 0.0
        cfg = _get_gamification_config(state)
        if percent > prev_best:
            delta = percent - prev_best
            bonus_amount = delta * float(cfg.get("improvement_bonus_multiplier", 2.0) or 2.0)
            bonus_event = f"practiceImprovement:{test_id}:{user['id']}:{session['completed_at']}"
            bonus_result = _award_xp(
                state,
                user["id"],
                bonus_event,
                bonus_amount,
                metadata={"type": "improvement", "percent": percent, "date": session["completed_at"], "source_type": "practice_completion", "event_type": "improvement"},
            )
            if bonus_result:
                bonus_awarded = bonus_result["xp_awarded"]
            best_scores[test_id] = percent
        streak_info = state.get("gamification", {}).get("streaks", {}).get(user["id"], {})
        context = {
            "streak": streak_info.get("current_streak", 0),
            "practice_questions": session.get("limit", 0),
            "percent": percent,
            "difficulty": current.get("difficulty", "medium"),
            "max_mastery": max(
                (
                    _to_float(entry.get("mastery", {}).get("mastery_score"))
                    for entry in session.get("answered", [])
                    if _to_float(entry.get("mastery", {}).get("mastery_score")) is not None
                ),
                default=0,
            ),
            "improvement": improvement,
        }
        achievements_unlocked = _evaluate_achievements(state, user["id"], context)
        save_state(state)
        xp_final = state.get("gamification", {}).get("xp", {}).get(user["id"], {})
        return {
            "success": True,
            "done": True,
            "evaluation": evaluation,
            "mastery": mastery,
            "evidence": evidence,
            "score": session["correct"],
            "answered": len(session["answered"]),
            "limit": session["limit"],
            "xp_awarded": xp_response["xp_awarded"] if xp_response else 0,
            "xp_total": xp_final.get("xp_total"),
            "level": xp_final.get("level"),
            "bonus_xp": bonus_awarded,
            "achievements_unlocked": achievements_unlocked,
        }

    exclude = [(a.get("id") or a.get("question") or "") for a in session.get("answered", [])] + (session.get("asked", []) or [])
    try:
        recommendation = recommender_mod.recommend_question(
            quiz=quiz,
            evaluation=evaluation,
            mastery=mastery,
            override_score=None,
            exclude_questions=exclude,
        )
    except Exception:
        recommendation = {}
    next_q = recommendation.get("selected_question")
    if not next_q:
        # Fallback: pick the first available question in the quiz by id.
        exclude_set = set(exclude)
        flat_all = _flatten_quiz_for_adaptive(quiz)
        candidate = next((q for q in flat_all if (q.get("id") or q.get("question", "")) not in exclude_set), None)
        if candidate:
            session["current"] = candidate
            session["current_started_at"] = iso_utc_now()
            session.setdefault("asked", []).append(session["current"].get("id") or session["current"].get("question", ""))
            _persist()
        return {
            "success": True,
            "done": False,
            "evaluation": evaluation,
            "mastery": mastery,
            "evidence": evidence,
            "next_question": session["current"],
            "remaining": session["limit"] - len(session["answered"]),
            "answered": len(session["answered"]),
            "score": session["correct"],
            "limit": session["limit"],
            "note": "Fallback selection used",
            "xp_awarded": xp_response["xp_awarded"] if xp_response else 0,
            "xp_total": xp_response["xp_total"] if xp_response else None,
            "level": xp_response["level"] if xp_response else None,
        }
        _persist()
        return {
            "success": True,
            "done": True,
            "evaluation": evaluation,
            "mastery": mastery,
            "evidence": evidence,
            "score": session["correct"],
            "answered": len(session["answered"]),
            "limit": session["limit"],
            "note": "No more questions available",
            "xp_awarded": xp_response["xp_awarded"] if xp_response else 0,
            "xp_total": xp_response["xp_total"] if xp_response else None,
            "level": xp_response["level"] if xp_response else None,
        }

    session["current"] = {
        "id": next_q.get("id") or next_q.get("question", ""),
        "question": next_q.get("question", ""),
        "options": next_q.get("options", []),
        "correct_answer": next_q.get("correct_answer", ""),
        "difficulty": next_q.get("difficulty", "medium"),
        "position": recommendation.get("position", ""),
    }
    session["current_started_at"] = iso_utc_now()
    session.setdefault("asked", []).append(session["current"].get("id") or session["current"]["question"])
    _persist()

    return {
        "success": True,
        "done": False,
        "evaluation": evaluation,
        "mastery": mastery,
        "evidence": evidence,
        "next_question": session["current"],
        "remaining": session["limit"] - len(session["answered"]),
        "answered": len(session["answered"]),
        "score": session["correct"],
        "limit": session["limit"],
    }


@app.post("/admin/create_class")
async def admin_create_class(request: Request, class_name: str = Form(...)):
    user = get_session_user(request)
    if not user or user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    state = load_state()
    class_id = uuid.uuid4().hex
    state["classes"][class_id] = {"id": class_id, "name": class_name, "teachers": [], "students": []}
    save_state(state)
    return RedirectResponse("/dashboard", status_code=303)


@app.post("/admin/assign_teacher")
async def admin_assign_teacher(request: Request, class_id: str = Form(...), teacher_id: str = Form(...)):
    user = get_session_user(request)
    if not user or user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    state = load_state()
    cls = state["classes"].get(class_id)
    if not cls:
        raise HTTPException(status_code=400, detail="Class not found.")
    if teacher_id not in cls["teachers"]:
        cls["teachers"].append(teacher_id)
    state["classes"][class_id] = cls
    save_state(state)
    return RedirectResponse("/dashboard", status_code=303)


@app.post("/admin/assign_student")
async def admin_assign_student(request: Request, class_id: str = Form(...), student_id: str = Form(...)):
    user = get_session_user(request)
    if not user or user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    state = load_state()
    cls = state["classes"].get(class_id)
    if not cls:
        raise HTTPException(status_code=400, detail="Class not found.")
    if student_id not in cls["students"]:
        cls["students"].append(student_id)
    # also reflect on user record
    if student_id in state["users"]:
        state["users"][student_id]["classes"] = list(set(state["users"][student_id].get("classes", [])) | {class_id})
    state["classes"][class_id] = cls
    save_state(state)
    return RedirectResponse("/dashboard", status_code=303)


@app.post("/teacher/upload_pdf")
async def upload_pdf(
    request: Request,
    pdf: UploadFile = File(...),
    files: List[UploadFile] | None = File(None),
    test_name: str = Form(...),
    test_comment: str = Form(""),
    question_limit: int = Form(5),
    api_key: str = Form(...),
    model: str = Form("llama3.1-8b"),
):
    user = get_session_user(request)
    if not user or user["role"] != "teacher":
        raise HTTPException(status_code=403, detail="Forbidden")

    state = load_state()
    uploads: List[UploadFile] = [pdf]
    if files:
        uploads.extend(files)
    job_id = uuid.uuid4().hex
    job_dir = DATA_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    saved_paths: List[Path] = []
    for upload in uploads:
        sanitized_name = Path(upload.filename or "upload").name
        target_path = job_dir / sanitized_name
        target_path.write_bytes(await upload.read())
        saved_paths.append(target_path)

    if not saved_paths:
        raise HTTPException(status_code=400, detail="No files were uploaded.")

    source_paths: List[Path] = list(saved_paths)

    filename = saved_paths[0].name

    test_id = uuid.uuid4().hex
    state["tests"][test_id] = {
        "id": test_id,
        "owner_id": user["id"],
        "title": test_name,
        "comment": test_comment,
        "job_id": job_id,
        "pdf_filename": filename,
        "source_files": [p.name for p in saved_paths],
        "created_at": iso_utc_now(),
        "status": "pending_review",
        "paths": {},
        "log": [],
        "kind": "class_test",
        "limit": min(100, max(1, int(question_limit))),
        "model": model,
        "pipeline": {"status": "running", "started_at": iso_utc_now(), "steps": []},
        "artifacts_persisted": False,
    }
    save_state(state)

    first_pdf_path: Optional[Path] = next((p for p in source_paths if p.suffix.lower() == ".pdf"), None)

    def worker():
        try:
            log_fn = lambda msg: append_test_log(test_id, msg)
            append_test_log(test_id, "Starting pipeline...")
            pipeline_metrics: Dict[str, Any] = {}
            paths = run_pipeline(
                job_dir,
                source_paths,
                api_key,
                model,
                question_limit=min(100, max(1, int(question_limit or 5))),
                metrics_out=pipeline_metrics,
                log_fn=log_fn,
            )
            st = load_state()
            test = st["tests"][test_id]
            test_kind = test.get("kind") or "class_test"
            if test_kind == "class_test":
                test["status"] = "pending_review"
            else:
                test["status"] = "ready"
            test["paths"] = paths
            pipeline_metrics.setdefault("model", model)
            test["pipeline"] = pipeline_metrics
            if DATABASE_URL:
                try:
                    _persist_test_artifacts_from_paths(test_id, paths=paths, source_pdf_path=first_pdf_path)
                    append_test_log(test_id, "Saved quiz artifacts to database.")
                    test["artifacts_persisted"] = True
                except Exception as exc:
                    append_test_log(test_id, f"Warning: Failed to persist quiz artifacts to database: {exc}")
            append_test_log(test_id, "Pipeline complete.")
            try:
                quiz_data = _get_test_quiz(test_id, st)
                test["quality"] = _compute_test_quality(quiz_data)
            except Exception:
                test["quality"] = None
            st["tests"][test_id] = test
            update_model_meta(st, model)
            save_state(st)
        except Exception as exc:  # pragma: no cover
            st = load_state()
            test = st["tests"].get(test_id, {})
            test["status"] = f"failed: {exc}"
            pipeline = test.get("pipeline") or {}
            pipeline.setdefault("status", "failed")
            pipeline.setdefault("completed_at", iso_utc_now())
            test["pipeline"] = pipeline
            st["tests"][test_id] = test
            append_test_log(test_id, f"Error: {exc}")
            save_state(st)

    threading.Thread(target=worker, daemon=True).start()
    return {"success": True, "test": state["tests"][test_id]}
    return RedirectResponse("/dashboard", status_code=303)


@app.post("/api/tests/{test_id}/rerun")
async def api_rerun_test(test_id: str, payload: Dict[str, Any] = Body(None), request: Request = None):
    """Re-run the quiz generation pipeline for a failed test (admin only)."""
    user = require_user(request)
    require_role(user, "admin")
    state = load_state()
    test = state["tests"].get(test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Test not found.")
    try:
        source_files, job_dir = _gather_source_files_for_test(test)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    api_key = payload.get("apiKey") if payload else None
    model = payload.get("model") if payload else None
    api_key = api_key or os.environ.get("CEREBRAS_API_KEY")
    model = model or "llama3.1-8b"
    if not api_key:
        raise HTTPException(status_code=400, detail="Missing Cerebras API key.")

    def worker():
        try:
            log_fn = lambda msg: append_test_log(test_id, msg)
            append_test_log(test_id, "Re-run: starting pipeline...")
            limit = int(test.get("questionLimit") or test.get("limit") or 100)
            include_difficulty = bool(test.get("include_difficulty", True))
            pipeline_metrics: Dict[str, Any] = {}
            paths = run_pipeline(
                job_dir,
                list(source_files),
                api_key,
                model,
                include_difficulty=include_difficulty,
                question_limit=limit,
                metrics_out=pipeline_metrics,
                log_fn=log_fn,
            )
            st = load_state()
            test = st["tests"][test_id]
            test["status"] = "ready"
            test["paths"] = paths
            test["model"] = model
            pipeline_metrics.setdefault("model", model)
            test["pipeline"] = pipeline_metrics
            if DATABASE_URL:
                try:
                    first_pdf = next((p for p in source_files if p.suffix.lower() == ".pdf"), None)
                    _persist_test_artifacts_from_paths(test_id, paths=paths, source_pdf_path=first_pdf)
                    append_test_log(test_id, "Saved quiz artifacts to database.")
                    test["artifacts_persisted"] = True
                except Exception as exc:
                    append_test_log(test_id, f"Warning: Failed to persist quiz artifacts to database: {exc}")
            append_test_log(test_id, "Re-run complete.")
            try:
                quiz_data = _get_test_quiz(test_id, st)
                test["quality"] = _compute_test_quality(quiz_data)
            except Exception:
                test["quality"] = None
            st["tests"][test_id] = test
            update_model_meta(st, model)
            save_state(st)
        except Exception as exc:  # pragma: no cover
            st = load_state()
            test = st["tests"].get(test_id, {})
            test["status"] = f"failed: {exc}"
            pipeline = test.get("pipeline") or {}
            pipeline.setdefault("status", "failed")
            pipeline.setdefault("completed_at", iso_utc_now())
            test["pipeline"] = pipeline
            st["tests"][test_id] = test
            append_test_log(test_id, f"Re-run error: {exc}")
            save_state(st)

    threading.Thread(target=worker, daemon=True).start()
    return {"success": True, "test_id": test_id, "status": "processing"}


def _get_assignment_quiz(assignment_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
    assignment = state["assignments"].get(assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    test = state["tests"].get(assignment["test_id"])
    if not test:
        raise HTTPException(status_code=404, detail="Test not found.")
    return _get_test_quiz(str(assignment["test_id"]), state)


@app.post("/student/start_adaptive")
async def student_start_adaptive(request: Request, assignment_id: str = Form(...)):
    user = get_session_user(request)
    if not user or user["role"] != "student":
        raise HTTPException(status_code=403, detail="Forbidden")
    state = load_state()
    assignment = state["assignments"].get(assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    # ensure student in class
    class_id = assignment.get("class_id")
    if class_id and user["id"] not in state["classes"].get(class_id, {}).get("students", []):
        raise HTTPException(status_code=403, detail="Not part of this class.")

    quiz = _get_assignment_quiz(assignment_id, state)
    test = state["tests"].get(assignment["test_id"], {})
    # pick first question random
    flat = []
    def collect(node, trail):
        if isinstance(node, dict):
            t = node.get("title")
            new = trail + [t] if t else trail
            if "questions" in node and node["questions"]:
                for q in node["questions"]:
                    flat.append({"question": q.get("question",""), "options": q.get("options", []), "correct_answer": q.get("correct_answer",""), "difficulty": q.get("difficulty", "medium"), "position": "/".join([s for s in new if s])})
            for k,v in node.items():
                if k not in {"title","questions"}:
                    collect(v, new+[k])
        elif isinstance(node, list):
            for item in node:
                collect(item, trail)
    collect(quiz, [])
    if not flat:
        raise HTTPException(status_code=400, detail="No questions in quiz.")
    import random
    first = random.choice(flat)
    q_limit = max(1, test.get("limit", 5))
    session = {"asked": [first["question"]], "answered": [], "limit": q_limit, "correct": 0, "current": first}
    assignment.setdefault("sessions", {})[user["id"]] = session
    state["assignments"][assignment_id] = assignment
    save_state(state)
    return {"question": first, "remaining": session["limit"] - len(session["asked"])}


@app.post("/student/answer_adaptive")
async def student_answer_adaptive(
    request: Request,
    assignment_id: str = Form(...),
    student_answer: str = Form(...),
    time_taken: float = Form(0.0),
    expected_time: float = Form(20.0),
    difficulty: str = Form("medium"),
):
    user = get_session_user(request)
    if not user or user["role"] != "student":
        raise HTTPException(status_code=403, detail="Forbidden")
    state = load_state()
    assignment = state["assignments"].get(assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found.")
    session = assignment.get("sessions", {}).get(user["id"])
    if not session or not session.get("current"):
        raise HTTPException(status_code=400, detail="Session not started.")

    quiz = _get_assignment_quiz(assignment_id, state)
    evaluator = _load_module(EVALUATOR_PATH, "answer_evaluator")
    mastery_mod = _load_module(MASTERY_PATH, "mastery_scorer")
    recommender_mod = _load_module(RECOMMENDER_PATH, "question_recommender")

    current = session["current"]
    evaluation = evaluator.evaluate_answer(
        question=current["question"],
        correct_answer=current.get("correct_answer",""),
        student_answer=student_answer,
        time_taken=time_taken,
        expected_time=expected_time,
        difficulty=current.get("difficulty", difficulty),
        position=current.get("position",""),
    )
    mastery = mastery_mod.calculate_mastery(evaluation)
    if evaluation["metrics"]["is_correct"]:
        session["correct"] += 1
    session["answered"].append({
        "question": current["question"],
        "evaluation": evaluation,
        "mastery": mastery,
    })

    # stop if limit reached
    if len(session["answered"]) >= session["limit"]:
        assignment["sessions"][user["id"]] = session
        assignment.setdefault("status", {})[user["id"]] = "completed"
        state["assignments"][assignment_id] = assignment
        save_state(state)
        return {
            "done": True,
            "evaluation": evaluation,
            "mastery": mastery,
            "score": session["correct"],
            "answered": len(session["answered"]),
            "limit": session["limit"],
        }

    exclude = [a["question"] for a in session["answered"]] + session.get("asked", [])
    recommendation = recommender_mod.recommend_question(
        quiz=quiz,
        evaluation=evaluation,
        mastery=mastery,
        override_score=None,
        exclude_questions=exclude,
    )
    next_q = recommendation.get("selected_question")
    if not next_q:
        assignment["sessions"][user["id"]] = session
        state["assignments"][assignment_id] = assignment
        save_state(state)
        return {"done": True, "evaluation": evaluation, "mastery": mastery, "score": session["correct"], "answered": len(session["answered"]), "limit": session["limit"], "note": "No more questions available"}

    session["current"] = {
        "question": next_q.get("question",""),
        "options": next_q.get("options", []),
        "correct_answer": next_q.get("correct_answer",""),
        "difficulty": next_q.get("difficulty", "medium"),
        "position": recommendation.get("position",""),
    }
    session.setdefault("asked", []).append(session["current"]["question"])
    assignment["sessions"][user["id"]] = session
    state["assignments"][assignment_id] = assignment
    save_state(state)

    return {
        "done": False,
        "evaluation": evaluation,
        "mastery": mastery,
        "next_question": session["current"],
        "remaining": session["limit"] - len(session["answered"]) - 0,
    }


@app.get("/teacher/test_pdf/{test_id}")
async def test_pdf(test_id: str):
    state = load_state()
    test = state["tests"].get(test_id)
    if not test or test["status"] != "ready":
        raise HTTPException(status_code=404, detail="Test not ready")
    pdf_path = (_resolve_quiz_paths(test) or {}).get("quiz_pdf")
    if not pdf_path or not pdf_path.exists():
        if DATABASE_URL:
            artifacts = _db_fetch_test_artifacts(test_id)
            pdf_bytes = artifacts.get("quiz_pdf")
            if isinstance(pdf_bytes, (bytes, bytearray)) and pdf_bytes:
                filename = f"{sanitize_filename(test.get('title') or 'quiz', default='quiz')}.pdf"
                return Response(
                    content=pdf_bytes,
                    media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{filename}"'},
                )
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(pdf_path, media_type="application/pdf", filename=pdf_path.name)


@app.post("/teacher/assign_test")
async def assign_test(
    request: Request,
    test_id: str = Form(...),
    class_name: str = Form(...),
    student_ids: str = Form(""),
):
    user = get_session_user(request)
    if not user or user["role"] != "teacher":
        raise HTTPException(status_code=403, detail="Forbidden")
    state = load_state()
    if test_id not in state["tests"]:
        raise HTTPException(status_code=400, detail="Test not found.")
    assignment_id = uuid.uuid4().hex
    students = [s.strip() for s in student_ids.split(",") if s.strip()]
    state["assignments"][assignment_id] = {
        "id": assignment_id,
        "test_id": test_id,
        "class_name": class_name,
        "students": students,
        "status": {},
        "created_at": iso_utc_now(),
        "sessions": {},
        "completed_at": {},
    }
    save_state(state)
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/student/test_pdf/{assignment_id}")
async def student_test_pdf(request: Request, assignment_id: str):
    user = get_session_user(request)
    if not user or user["role"] != "student":
        raise HTTPException(status_code=403, detail="Forbidden")
    state = load_state()
    assignment = state["assignments"].get(assignment_id)
    if not assignment or user["id"] not in assignment.get("students", []):
        raise HTTPException(status_code=404, detail="Assignment not found.")
    test = state["tests"].get(assignment["test_id"])
    if not test or test["status"] != "ready":
        raise HTTPException(status_code=404, detail="Test not ready.")
    pdf_path = (_resolve_quiz_paths(test) or {}).get("quiz_pdf")
    if not pdf_path or not pdf_path.exists():
        if DATABASE_URL:
            artifacts = _db_fetch_test_artifacts(str(assignment.get("test_id") or ""))
            pdf_bytes = artifacts.get("quiz_pdf")
            if isinstance(pdf_bytes, (bytes, bytearray)) and pdf_bytes:
                filename = f"{sanitize_filename(test.get('title') or 'quiz', default='quiz')}.pdf"
                return Response(
                    content=pdf_bytes,
                    media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{filename}"'},
                )
        raise HTTPException(status_code=404, detail="PDF not found.")
    return FileResponse(pdf_path, media_type="application/pdf", filename=pdf_path.name)


@app.post("/student/complete")
async def student_complete(request: Request, assignment_id: str = Form(...)):
    user = get_session_user(request)
    if not user or user["role"] != "student":
        raise HTTPException(status_code=403, detail="Forbidden")
    state = load_state()
    assignment = state["assignments"].get(assignment_id)
    if not assignment or user["id"] not in assignment.get("students", []):
        raise HTTPException(status_code=404, detail="Assignment not found.")
    assignment.setdefault("status", {})[user["id"]] = "completed"
    assignment.setdefault("completed_at", {})[user["id"]] = iso_utc_now()
    save_state(state)
    return RedirectResponse("/dashboard", status_code=303)


@app.post("/student/upload_practice")
async def upload_practice(
    request: Request,
    pdf: UploadFile = File(...),
    files: List[UploadFile] | None = File(None),
    api_key: str = Form(...),
    model: str = Form("llama3.1-8b"),
):
    user = get_session_user(request)
    if not user or user["role"] != "student":
        raise HTTPException(status_code=403, detail="Forbidden")

    state = load_state()
    uploads: List[UploadFile] = [pdf]
    if files:
        uploads.extend(files)
    job_id = uuid.uuid4().hex
    job_dir = DATA_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    saved_paths: List[Path] = []
    for upload in uploads:
        sanitized_name = Path(upload.filename or "upload").name
        target_path = job_dir / sanitized_name
        target_path.write_bytes(await upload.read())
        saved_paths.append(target_path)

    if not saved_paths:
        raise HTTPException(status_code=400, detail="No files were uploaded.")

    filename = saved_paths[0].name

    test_id = uuid.uuid4().hex
    state["tests"][test_id] = {
        "id": test_id,
        "owner_id": user["id"],
        "title": filename,
        "comment": "Practice test",
        "job_id": job_id,
        "pdf_filename": filename,
        "source_files": [p.name for p in saved_paths],
        "created_at": iso_utc_now(),
        "status": "processing",
        "paths": {},
        "log": [],
        "kind": "practice",
        "model": model,
        "pipeline": {"status": "running", "started_at": iso_utc_now(), "steps": []},
        "artifacts_persisted": False,
    }
    save_state(state)

    first_pdf_path: Optional[Path] = next((p for p in saved_paths if p.suffix.lower() == ".pdf"), None)

    def worker():
        try:
            log_fn = lambda msg: append_test_log(test_id, msg)
            append_test_log(test_id, "Starting pipeline...")
            pipeline_metrics: Dict[str, Any] = {}
            paths = run_pipeline(
                job_dir,
                list(saved_paths),
                api_key,
                model,
                question_limit=100,
                metrics_out=pipeline_metrics,
                log_fn=log_fn,
            )
            st = load_state()
            test = st["tests"][test_id]
            test["status"] = "ready"
            test["paths"] = paths
            pipeline_metrics.setdefault("model", model)
            test["pipeline"] = pipeline_metrics
            if DATABASE_URL:
                try:
                    _persist_test_artifacts_from_paths(test_id, paths=paths, source_pdf_path=first_pdf_path)
                    append_test_log(test_id, "Saved quiz artifacts to database.")
                    test["artifacts_persisted"] = True
                except Exception as exc:
                    append_test_log(test_id, f"Warning: Failed to persist quiz artifacts to database: {exc}")
            append_test_log(test_id, "Pipeline complete.")
            try:
                quiz_data = _get_test_quiz(test_id, st)
                test["quality"] = _compute_test_quality(quiz_data)
            except Exception:
                test["quality"] = None
            st["tests"][test_id] = test
            update_model_meta(st, model)
            save_state(st)
        except Exception as exc:  # pragma: no cover
            st = load_state()
            test = st["tests"].get(test_id, {})
            test["status"] = f"failed: {exc}"
            pipeline = test.get("pipeline") or {}
            pipeline.setdefault("status", "failed")
            pipeline.setdefault("completed_at", iso_utc_now())
            test["pipeline"] = pipeline
            st["tests"][test_id] = test
            append_test_log(test_id, f"Error: {exc}")
            save_state(st)

    threading.Thread(target=worker, daemon=True).start()
    return RedirectResponse("/dashboard", status_code=303)


@app.post("/admin/approve_test")
async def admin_approve_test(request: Request, test_id: str = Form(...), class_id: str = Form(...)):
    user = get_session_user(request)
    if not user or user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    state = load_state()
    test = state["tests"].get(test_id)
    if not test:
        raise HTTPException(status_code=400, detail="Test not found.")
    if test.get("status") == "pending_review":
        # assign to class -> create assignment for all students in class
        cls = state["classes"].get(class_id)
        if not cls:
            raise HTTPException(status_code=400, detail="Class not found.")
        assignment_id = uuid.uuid4().hex
        state["assignments"][assignment_id] = {
            "id": assignment_id,
            "test_id": test_id,
            "class_id": class_id,
            "students": list(cls.get("students", [])),
            "status": {},
            "created_at": iso_utc_now(),
            "sessions": {},
            "completed_at": {},
        }
        test["status"] = "ready"
        state["tests"][test_id] = test
        append_audit_log(
            state,
            actor_id=user.get("id"),
            action="test_approved",
            target_type="test",
            target_id=test_id,
            details={"class_id": class_id},
        )
        save_state(state)
    return RedirectResponse("/dashboard", status_code=303)


@app.post("/admin/create_user")
async def admin_create_user(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    school: str = Form(""),
    country: str = Form(""),
):
    admin = get_session_user(request)
    if not admin or admin["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    state = load_state()
    if role not in {"student", "teacher", "admin"}:
        raise HTTPException(status_code=400, detail="Invalid role.")
    for u in state["users"].values():
        if u["email"].lower() == email.lower():
            raise HTTPException(status_code=400, detail="Email already registered.")
    user_id = uuid.uuid4().hex
    state["users"][user_id] = {
        "id": user_id,
        "full_name": full_name,
        "email": email,
        "password": password,
        "role": role,
        "school": school,
        "country": country,
        "classes": [],
        "teachers": [],
        "practice_tests": [],
    }
    save_state(state)
    return RedirectResponse("/dashboard", status_code=303)


@app.post("/admin/delete_user")
async def admin_delete_user(request: Request, user_id: str = Form(...)):
    admin = get_session_user(request)
    if not admin or admin["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    state = load_state()
    state["users"].pop(user_id, None)
    # Clean from classes
    for cls in state["classes"].values():
        cls["students"] = [s for s in cls.get("students", []) if s != user_id]
        cls["teachers"] = [t for t in cls.get("teachers", []) if t != user_id]
    save_state(state)
    return RedirectResponse("/dashboard", status_code=303)


# ---------- Download quiz ----------
def _resolve_quiz_paths(test: Dict[str, Any]) -> Dict[str, Optional[Path]]:
    """
    Resolve quiz JSON/PDF paths even if the stored strings are stale or platform-specific.

    This can happen when `state.json` is moved between Windows and Linux machines (absolute paths),
    or when the test title doesn't match the uploaded filename (old flows without `pdf_filename`).
    """
    raw_paths = test.get("paths") or {}
    if not isinstance(raw_paths, dict):
        raw_paths = {}

    json_candidates: list[Path] = []
    pdf_candidates: list[Path] = []
    evidence_candidates: list[Path] = []

    def add_candidate(cands: list[Path], value: Any) -> None:
        if not value:
            return
        try:
            cands.append(Path(str(value)))
        except Exception:
            return

    def sorted_by_mtime_desc(paths: list[Path]) -> list[Path]:
        def key(p: Path) -> float:
            try:
                return p.stat().st_mtime
            except Exception:
                return 0.0

        return sorted(paths, key=key, reverse=True)

    # Stored paths first (may be Windows-formatted and not exist in this environment).
    add_candidate(json_candidates, raw_paths.get("quiz_json"))
    add_candidate(pdf_candidates, raw_paths.get("quiz_pdf"))
    add_candidate(evidence_candidates, raw_paths.get("evidence_json"))

    job_id = test.get("job_id")
    if job_id:
        job_dir = DATA_DIR / str(job_id)

        # 1) Scan the job dir for actual quiz artifacts (most robust).
        if job_dir.exists():
            json_globs = [
                "*_extracted_chunks_structure_quiz*.json",
                "*_extracted*_quiz*.json",
            ]
            pdf_globs = [
                "*_extracted_chunks_structure_quiz*.pdf",
                "*_extracted*_quiz*.pdf",
            ]
            evidence_globs = [
                "*_extracted_chunks_structure_evidence*.json",
                "*_structure_evidence*.json",
            ]

            job_jsons: list[Path] = []
            job_pdfs: list[Path] = []
            job_evidence: list[Path] = []
            for pat in json_globs:
                job_jsons.extend([p for p in job_dir.glob(pat) if p.is_file()])
            for pat in pdf_globs:
                job_pdfs.extend([p for p in job_dir.glob(pat) if p.is_file()])
            for pat in evidence_globs:
                job_evidence.extend([p for p in job_dir.glob(pat) if p.is_file()])

            # De-dupe while preserving order, then prefer newest artifacts.
            json_candidates.extend(sorted_by_mtime_desc(list(dict.fromkeys(job_jsons))))
            pdf_candidates.extend(sorted_by_mtime_desc(list(dict.fromkeys(job_pdfs))))
            evidence_candidates.extend(sorted_by_mtime_desc(list(dict.fromkeys(job_evidence))))

        # 2) Derive from filename hints (best-effort for older state files).
        title_guess = sanitize_filename(test.get("title") or "quiz", default="quiz")
        filename_hint = test.get("pdf_filename") or title_guess
        filename_hint = Path(str(filename_hint)).name  # strip any directory components

        filename_candidates: list[str] = []
        if filename_hint.lower().endswith(".pdf"):
            # Handle both <name>.pdf and the legacy double-extension <name>.pdf.pdf.
            filename_candidates.extend([filename_hint, f"{filename_hint}.pdf"])
        else:
            filename_candidates.extend([f"{filename_hint}.pdf", filename_hint])

        seen: set[str] = set()
        for fname in filename_candidates:
            if not fname or fname in seen:
                continue
            seen.add(fname)
            derived = derive_paths(job_dir / fname)
            json_candidates.append(derived["quiz_json"])
            pdf_candidates.append(derived["quiz_pdf"])
            evidence_candidates.append(derived["evidence_json"])

    def pick(cands: list[Path]) -> Optional[Path]:
        for p in cands:
            try:
                if p.exists():
                    return p
            except Exception:
                continue
        return cands[0] if cands else None

    return {
        "quiz_json": pick(json_candidates),
        "quiz_pdf": pick(pdf_candidates),
        "evidence_json": pick(evidence_candidates),
    }


def _load_evidence_sidecar(path: Optional[Path]) -> Optional[Dict[str, Any]]:
    if not path:
        return None
    try:
        if not path.exists():
            return None
    except Exception:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _lookup_question_evidence(
    sidecar: Optional[Dict[str, Any]],
    *,
    question_id: Optional[str],
    question_text: Optional[str],
) -> List[str]:
    if not sidecar:
        return []
    entries = sidecar.get("questions") or []
    if not isinstance(entries, list):
        return []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if question_id and str(entry.get("id") or "") == str(question_id):
            evidence = entry.get("evidence") or []
            return [str(e).strip() for e in evidence if str(e).strip()] if isinstance(evidence, list) else []
        if question_text and str(entry.get("question") or "").strip() == str(question_text).strip():
            evidence = entry.get("evidence") or []
            return [str(e).strip() for e in evidence if str(e).strip()] if isinstance(evidence, list) else []
    return []


@app.get("/api/tests/{test_id}/quiz")
async def api_get_test_quiz(
    test_id: str,
    fmt: str = "json",
    format: str = None,  # alias to support legacy ?format=pdf
    request: Request = None,
):
    """
    Serve the generated quiz for a test (JSON by default, PDF if fmt=pdf).
    """
    require_user(request)
    state = load_state()
    test = state["tests"].get(test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Test not found.")

    paths = _resolve_quiz_paths(test)
    fmt = (format or fmt or "json").lower()

    if fmt == "pdf":
        pdf_path = paths.get("quiz_pdf")
        if pdf_path and pdf_path.exists():
            if DATABASE_URL and not test.get("artifacts_persisted"):
                try:
                    _persist_test_artifacts_from_paths(test_id, paths=paths)
                    test["artifacts_persisted"] = True
                    state["tests"][test_id] = test
                    save_state(state)
                except Exception:
                    pass
            return FileResponse(pdf_path, filename=pdf_path.name, media_type="application/pdf")
        if DATABASE_URL:
            artifacts = _db_fetch_test_artifacts(test_id)
            pdf_bytes = artifacts.get("quiz_pdf")
            if isinstance(pdf_bytes, (bytes, bytearray)) and pdf_bytes:
                filename = (pdf_path.name if pdf_path else f"{sanitize_filename(test.get('title') or 'quiz', default='quiz')}.pdf")
                return Response(
                    content=pdf_bytes,
                    media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{filename}"'},
                )
        raise HTTPException(status_code=404, detail="Quiz PDF not found.")

    json_path = paths.get("quiz_json")
    if json_path and json_path.exists():
        if DATABASE_URL and not test.get("artifacts_persisted"):
            try:
                _persist_test_artifacts_from_paths(test_id, paths=paths)
                test["artifacts_persisted"] = True
                state["tests"][test_id] = test
                save_state(state)
            except Exception:
                pass
        return FileResponse(json_path, filename=json_path.name, media_type="application/json")
    quiz = _get_test_quiz(test_id, state)
    return JSONResponse(content=quiz)


@app.get("/api/tests/{test_id}/quiz-debug")
async def api_get_test_quiz_debug(test_id: str, request: Request):
    require_user(request)
    state = load_state()
    quiz = _get_test_quiz(test_id, state)
    flat = []
    def _flatten(node, trail):
        if isinstance(node, dict):
            t = node.get("title") or node.get("name")
            new = trail + [t] if t else trail
            if "questions" in node and node["questions"]:
                for q in node["questions"]:
                    flat.append({
                        "id": q.get("id") or q.get("question", ""),
                        "question": q.get("question", ""),
                        "options": q.get("options", []),
                        "correct_answer": q.get("correct_answer", ""),
                        "section": "/".join([s for s in new if s]),
                    })
            for k, v in node.items():
                if k not in {"title", "name", "questions"}:
                    _flatten(v, new + [k])
        elif isinstance(node, list):
            for item in node:
                _flatten(item, trail)
    _flatten(quiz, [])
    return {"flat_count": len(flat), "flat_preview": flat[:3], "limit": int(state["tests"].get(test_id, {}).get("questionLimit") or 0)}


# Practice next-question endpoint (uses recommender logic)
def _collect_questions_with_positions(node, trail, out):
    if isinstance(node, dict):
        segs = trail
        if node.get('title'):
            segs = trail + [node['title']]
        if node.get('questions'):
            for q in node.get('questions', []):
                out.append({
                    "id": q.get("id") or q.get("question", ""),
                    "question": q.get("question", ""),
                    "options": q.get("options", []),
                    "correct_answer": q.get("correct_answer", ""),
                    "difficulty": q.get("difficulty", "medium"),
                    "position": "/".join([s for s in segs if s]),
                })
        for k, v in node.items():
            if k not in {"title", "questions"}:
                _collect_questions_with_positions(v, segs + [k], out)
    elif isinstance(node, list):
        for item in node:
            _collect_questions_with_positions(item, trail, out)

@app.post("/api/tests/{test_id}/practice/next")
async def api_practice_next(test_id: str, payload: Dict[str, Any] = Body(...), request: Request = None):
    user = require_user(request)
    if user.get("role") != "student":
        raise HTTPException(status_code=403, detail="Forbidden")
    state = load_state()
    quiz = _get_test_quiz(test_id, state)
    test = state["tests"].get(test_id, {})
    limit = int(test.get("questionLimit") or test.get("limit") or 0)
    flat: List[Dict[str, Any]] = []
    _collect_questions_with_positions(quiz, [], flat)
    if limit and len(flat) > limit:
        flat = flat[:limit]
    if not flat:
        raise HTTPException(status_code=400, detail="No questions in quiz")

    asked = set(payload.get("asked") or [])
    remaining_candidates = [q for q in flat if q["question"] not in asked]
    if not remaining_candidates:
        return {"question": None, "remaining": 0, "total": len(flat)}

    last_q = payload.get("last_question")
    if not asked or not last_q:
        chosen = remaining_candidates[0]
    else:
        position = next((q["position"] for q in flat if q["question"] == last_q), "")
        evaluation = {"question": last_q, "position": position, "metrics": {}}
        recommender_mod = _load_module(RECOMMENDER_PATH, "question_recommender")
        try:
            rec = recommender_mod.recommend_question(
                quiz=quiz,
                evaluation=evaluation,
                mastery=None,
                override_score=payload.get("score"),
                exclude_questions=list(asked),
            )
            selected = (rec or {}).get("selected_question") or {}
            rec_q = selected.get("question") if isinstance(selected, dict) else None
            chosen = next((q for q in remaining_candidates if q["question"] == rec_q), remaining_candidates[0])
        except Exception:
            chosen = remaining_candidates[0]

    asked.add(chosen["question"])
    remaining_after = len([q for q in flat if q["question"] not in asked])
    return {"question": chosen, "remaining": remaining_after, "total": len(flat)}


@app.post("/api/tests/{test_id}/practice/submit")
async def api_practice_submit(test_id: str, payload: Dict[str, Any] = Body(...), request: Request = None):
    user = require_user(request)
    if user.get("role") != "student":
        raise HTTPException(status_code=403, detail="Forbidden")
    state = load_state()
    quiz = _get_test_quiz(test_id, state)
    test = state["tests"].get(test_id, {})
    limit = int(test.get("questionLimit") or test.get("limit") or 0)
    flat: List[Dict[str, Any]] = []
    _collect_questions_with_positions(quiz, [], flat)
    if limit and len(flat) > limit:
        flat = flat[:limit]
    if not flat:
        raise HTTPException(status_code=400, detail="No questions in quiz")

    current_q = payload.get("question") or payload.get("last_question")
    current = next((q for q in flat if q["question"] == current_q), None)
    if not current:
        raise HTTPException(status_code=400, detail="Question not in quiz")

    evaluator = _load_module(EVALUATOR_PATH, "answer_evaluator")
    mastery_mod = _load_module(MASTERY_PATH, "mastery_scorer")
    evaluation = evaluator.evaluate_answer(
        question=current["question"],
        correct_answer=current.get("correct_answer", ""),
        student_answer=payload.get("student_answer", ""),
        time_taken=payload.get("time_taken", 0.0) or 0.0,
        expected_time=payload.get("expected_time", 20.0) or 20.0,
        difficulty=current.get("difficulty", payload.get("difficulty", "medium")),
        position=current.get("position", ""),
    )
    mastery = mastery_mod.calculate_mastery(evaluation)

    evidence: List[str] = []
    try:
        if (
            str(test.get("kind") or "").lower() == "practice"
            and test.get("owner_id") == user["id"]
        ):
            paths = _resolve_quiz_paths(test)
            sidecar = _load_evidence_sidecar(paths.get("evidence_json"))
            if sidecar is None and DATABASE_URL:
                artifacts = _db_fetch_test_artifacts(test_id)
                sidecar_db = artifacts.get("evidence_json")
                if isinstance(sidecar_db, dict):
                    sidecar = sidecar_db
            evidence = _lookup_question_evidence(
                sidecar,
                question_id=str(current.get("id") or ""),
                question_text=str(current.get("question") or ""),
            )
    except Exception:
        evidence = []

    asked = set(payload.get("asked") or [])
    asked.add(current["question"])
    score = int(payload.get("score") or 0)
    if evaluation["metrics"].get("is_correct"):
        score += 1

    remaining_candidates = [q for q in flat if q["question"] not in asked]
    if not remaining_candidates:
        return {
            "done": True,
            "evaluation": evaluation,
            "mastery": mastery,
            "score": score,
            "asked": list(asked),
            "remaining": 0,
            "total": len(flat),
            "evidence": evidence,
        }

    recommender_mod = _load_module(RECOMMENDER_PATH, "question_recommender")
    try:
        rec = recommender_mod.recommend_question(
            quiz=quiz,
            evaluation=evaluation,
            mastery=mastery,
            override_score=score,
            exclude_questions=list(asked),
        )
        selected = (rec or {}).get("selected_question") or {}
        rec_q = selected.get("question") if isinstance(selected, dict) else None
        chosen = next((q for q in remaining_candidates if q["question"] == rec_q), remaining_candidates[0])
    except Exception:
        chosen = remaining_candidates[0]

    asked.add(chosen["question"])
    remaining_after = len([q for q in flat if q["question"] not in asked])

    return {
        "done": False,
        "evaluation": evaluation,
        "mastery": mastery,
        "score": score,
        "asked": list(asked),
        "next_question": chosen,
        "remaining": remaining_after,
        "total": len(flat),
        "evidence": evidence,
    }


@app.delete("/api/tests/{test_id}")
async def api_delete_test(test_id: str, request: Request):
    """
    Delete a test and any assignments that reference it.

    Permissions:
    - admin: can delete any test
    - teacher: can delete tests they own
    - student: can delete ONLY their own practice tests
    """
    user = require_user(request)
    state = load_state()
    test = state["tests"].get(test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Test not found.")

    role = (user.get("role") or "").lower()
    owner_id = test.get("owner_id")
    kind = (test.get("kind") or "").lower()

    allowed = False
    if role == "admin":
        allowed = True
    elif role == "teacher":
        allowed = bool(owner_id and owner_id == user.get("id"))
    elif role == "student":
        allowed = bool(kind == "practice" and owner_id and owner_id == user.get("id"))

    if not allowed:
        raise HTTPException(status_code=403, detail="Forbidden")

    # Remove assignments pointing to this test
    assignments = state.get("assignments", {})
    to_delete = [aid for aid, a in assignments.items() if a.get("test_id") == test_id]
    for aid in to_delete:
        assignments.pop(aid, None)

    # Remove test record itself
    state["tests"].pop(test_id, None)
    append_audit_log(
        state,
        actor_id=user.get("id"),
        action="test_deleted",
        target_type="test",
        target_id=test_id,
        details={"kind": kind, "owner_id": owner_id},
    )
    if DATABASE_URL:
        try:
            _db_delete_test_artifacts(test_id)
        except Exception:
            pass
    save_state(state)
    return {"success": True, "deleted_test_id": test_id, "deleted_assignments": to_delete}
