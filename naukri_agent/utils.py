from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def normalize_space(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def safe_lower(text: str | None) -> str:
    return normalize_space(text).lower()


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def copy_if_missing(src: Path, dst: Path) -> bool:
    if dst.exists():
        return False
    shutil.copy2(src, dst)
    return True


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def truncate(text: str, limit: int) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def host_from_url(url: str) -> str:
    try:
        from urllib.parse import urlparse

        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def is_naukri_url(url: str) -> bool:
    host = host_from_url(url)
    return host.endswith("naukri.com") or host.endswith("www.naukri.com")


def text_contains_any(text: str, needles: list[str]) -> bool:
    lowered = safe_lower(text)
    return any(needle.lower() in lowered for needle in needles)


def normalize_question_key(text: str) -> str:
    text = safe_lower(text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def best_answer_for_question(question: str, answers: dict[str, Any]) -> str | None:
    """Find a conservative answer for a visible application question.

    This intentionally avoids guessing. It matches by normalized key containment,
    common synonyms, and only returns an answer when confidence is reasonable.
    """
    normalized_question = normalize_question_key(question)
    if not normalized_question:
        return None

    normalized_answers = {
        normalize_question_key(str(key)): str(value) for key, value in answers.items()
    }

    for key, value in normalized_answers.items():
        if key and (key in normalized_question or normalized_question in key):
            return value

    synonym_groups = {
        "notice period": ["notice", "joining", "join", "available", "availability"],
        "current ctc": ["current ctc", "current salary", "present ctc", "present salary"],
        "expected ctc": ["expected ctc", "expected salary", "salary expectation"],
        "reason for job change": ["reason", "change", "looking for", "job change"],
        "willing to relocate": ["relocate", "relocation"],
        "serving notice": ["serving notice", "notice serving"],
        "total experience": ["total experience", "overall experience", "years of experience"],
        "relevant experience": ["relevant experience", "experience in", "hands on"],
        "current location": ["current location", "where are you located"],
        "preferred location": ["preferred location", "preferred work location"],
    }
    for answer_key, phrases in synonym_groups.items():
        normalized_answer_key = normalize_question_key(answer_key)
        if normalized_answer_key not in normalized_answers:
            continue
        if any(phrase in normalized_question for phrase in phrases):
            return normalized_answers[normalized_answer_key]
    return None
