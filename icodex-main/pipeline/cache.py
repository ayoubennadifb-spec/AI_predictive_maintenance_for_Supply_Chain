from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Optional

from pipeline.config import CACHE_ENV_FLAG


def cache_enabled(env: dict) -> bool:
    value = (env or {}).get(CACHE_ENV_FLAG, "")
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def hash_bytes(*parts: bytes) -> str:
    hasher = hashlib.sha256()
    for part in parts:
        hasher.update(part)
    return hasher.hexdigest()


def cache_path(job_dir: str, step: str, key: str, suffix: str) -> Path:
    root = Path(job_dir) / ".cache"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{step}_{key}{suffix}"


def read_cached(path: Path) -> Optional[bytes]:
    if path.exists():
        return path.read_bytes()
    return None


def write_cached(path: Path, payload: bytes) -> None:
    path.write_bytes(payload)
