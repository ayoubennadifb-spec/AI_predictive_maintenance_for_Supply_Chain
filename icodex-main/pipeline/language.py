from __future__ import annotations

import re
from typing import Optional, Tuple

try:
    from langdetect import DetectorFactory, detect_langs  # type: ignore
except Exception:  # pragma: no cover
    DetectorFactory = None
    detect_langs = None


_NON_LATIN_RE = re.compile(r"[\u0400-\u04FF\u0600-\u06FF\u4E00-\u9FFF]")


def detect_language(text: str, *, sample_size: int = 4000) -> Tuple[Optional[str], Optional[float]]:
    sample = (text or "").strip()
    if not sample:
        return None, None
    if len(sample) > sample_size:
        sample = sample[:sample_size]

    if detect_langs is not None:
        if DetectorFactory is not None:
            DetectorFactory.seed = 0
        try:
            langs = detect_langs(sample)
            if langs:
                top = langs[0]
                return getattr(top, "lang", None), getattr(top, "prob", None)
        except Exception:
            pass

    if _NON_LATIN_RE.search(sample):
        return "non_latin", None
    return "latin", None


def languages_match(base: Optional[str], other: Optional[str]) -> bool:
    if not base or not other:
        return True
    coarse = {"latin", "non_latin"}
    if base in coarse and other in coarse:
        return base == other
    if base in coarse or other in coarse:
        return True
    return base == other
