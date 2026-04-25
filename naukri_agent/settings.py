from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from .utils import read_json


DEFAULT_CONFIG: dict[str, Any] = {
    "search_urls": [],
    "min_match_score": 75,
    "max_applications_per_day": 10,
    "allowed_locations": [],
    "blacklisted_companies": [],
    "auto_submit": False,
    "dry_run": True,
    "skip_external_apply": True,
    "skip_unknown_questions": True,
    "skip_captcha": True,
    "browser_headless": False,
    "delay_seconds_between_jobs": 8,
}


@dataclass(slots=True)
class AgentSettings:
    project_root: Path
    config: dict[str, Any]
    profile: dict[str, Any]
    answers: dict[str, Any]
    openai_api_key: str
    openai_model: str

    @property
    def data_dir(self) -> Path:
        return self.project_root / "data"

    @property
    def browser_profile_dir(self) -> Path:
        return self.data_dir / "browser-profile"

    @property
    def tracker_path(self) -> Path:
        return self.data_dir / "applications.csv"

    @property
    def min_match_score(self) -> int:
        return int(self.config.get("min_match_score", 75))

    @property
    def max_applications_per_day(self) -> int:
        return int(self.config.get("max_applications_per_day", 10))

    @property
    def delay_seconds_between_jobs(self) -> float:
        return float(self.config.get("delay_seconds_between_jobs", 8))

    @property
    def dry_run_default(self) -> bool:
        return bool(self.config.get("dry_run", True))

    @property
    def auto_submit_default(self) -> bool:
        return bool(self.config.get("auto_submit", False))

    @property
    def browser_headless(self) -> bool:
        return bool(self.config.get("browser_headless", False))


def load_yaml_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing config file: {path}")
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    config = DEFAULT_CONFIG.copy()
    config.update(loaded)
    if not isinstance(config.get("search_urls"), list):
        raise ValueError("config.yaml: search_urls must be a list")
    return config


def load_settings(project_root: Path | None = None) -> AgentSettings:
    root = (project_root or Path.cwd()).resolve()
    load_dotenv(root / ".env")

    import os

    config = load_yaml_config(root / "config.yaml")
    profile_path = root / "profile.json"
    answers_path = root / "answers.json"
    if not profile_path.exists():
        raise FileNotFoundError("Missing profile.json. Run: python -m naukri_agent.cli init")
    if not answers_path.exists():
        raise FileNotFoundError("Missing answers.json. Run: python -m naukri_agent.cli init")

    return AgentSettings(
        project_root=root,
        config=config,
        profile=read_json(profile_path),
        answers=read_json(answers_path),
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini",
    )
