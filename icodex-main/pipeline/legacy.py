from __future__ import annotations

import importlib.util
from importlib.machinery import SourceFileLoader
import sys
from pathlib import Path
from types import ModuleType

from pipeline.config import REPO_ROOT, SCRIPT_PATHS

_STRUCTURE_MODULE: ModuleType | None = None
_REVIEWER_MODULE: ModuleType | None = None


def _load_module(path: Path, name: str) -> ModuleType:
    path_str = str(path)
    spec = importlib.util.spec_from_file_location(name, path_str)
    if not spec or not spec.loader:
        # Some legacy files use non-standard suffix casing (e.g. ".Py"),
        # which the default loader may not recognize. Force a source loader.
        loader = SourceFileLoader(name, path_str)
        spec = importlib.util.spec_from_file_location(name, path_str, loader=loader)
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot load module at {path_str}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


def _ensure_legacy_path() -> None:
    legacy_dir = str(REPO_ROOT / "questions generator")
    if legacy_dir not in sys.path:
        sys.path.insert(0, legacy_dir)


def load_structure_module() -> ModuleType:
    global _STRUCTURE_MODULE
    if _STRUCTURE_MODULE is not None:
        return _STRUCTURE_MODULE
    _ensure_legacy_path()
    _STRUCTURE_MODULE = _load_module(SCRIPT_PATHS["structure_to_questions"], "structure_to_questions")
    return _STRUCTURE_MODULE


def load_reviewer_module() -> ModuleType:
    global _REVIEWER_MODULE
    if _REVIEWER_MODULE is not None:
        return _REVIEWER_MODULE
    _ensure_legacy_path()
    reviewer_path = REPO_ROOT / "questions generator" / "reviewer.py"
    _REVIEWER_MODULE = _load_module(reviewer_path, "reviewer")
    return _REVIEWER_MODULE
