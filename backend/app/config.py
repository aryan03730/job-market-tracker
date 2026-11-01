"""Loads settings from tracker.toml plus environment variables.

Environment variables always win, so production secrets never live in the repo.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = BACKEND_DIR / "tracker.toml"


def _load_dotenv(path: Path) -> None:
    """Tiny .env loader so local development needs no extra package."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass
class Settings:
    raw: dict
    database_url: str
    admin_token: str | None
    cors_origins: list[str]
    keywords: list[str] = field(default_factory=list)
    country: str = "us"
    location: str = ""
    max_days_old: int = 7
    retention_days: int = 60
    max_description_chars: int = 6000
    include_predicted_salary: bool = False
    salary_min_valid: int = 15000
    salary_max_valid: int = 1_000_000
    failure_threshold: int = 3
    cooldown_hours: float = 6
    max_cooldown_hours: float = 168
    retries: int = 3
    timeout_seconds: float = 20
    skills: dict[str, str] = field(default_factory=dict)

    def provider(self, name: str) -> dict:
        return self.raw.get("providers", {}).get(name, {})


def _normalize_db_url(url: str) -> str:
    # Neon/Heroku style URLs start with postgres:// ; SQLAlchemy wants a driver.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def load_settings(config_path: str | Path | None = None) -> Settings:
    _load_dotenv(BACKEND_DIR / ".env")
    path = Path(config_path or os.environ.get("TRACKER_CONFIG", DEFAULT_CONFIG_PATH))
    raw = tomllib.loads(path.read_text()) if path.exists() else {}

    search = raw.get("search", {})
    storage = raw.get("storage", {})
    salary = raw.get("salary", {})
    res = raw.get("resilience", {})

    keywords = search.get("keywords", ["software engineer"])
    if os.environ.get("TRACKER_KEYWORDS"):
        keywords = [k.strip() for k in os.environ["TRACKER_KEYWORDS"].split(",") if k.strip()]

    db_url = os.environ.get("DATABASE_URL") or f"sqlite:///{BACKEND_DIR / 'tracker.db'}"

    origins = os.environ.get("CORS_ORIGINS", "*")
    return Settings(
        raw=raw,
        database_url=_normalize_db_url(db_url),
        admin_token=os.environ.get("ADMIN_TOKEN") or None,
        cors_origins=[o.strip() for o in origins.split(",")],
        keywords=keywords,
        country=search.get("country", "us"),
        location=os.environ.get("TRACKER_LOCATION", search.get("location", "")),
        max_days_old=int(search.get("max_days_old", 7)),
        retention_days=int(storage.get("retention_days", 60)),
        max_description_chars=int(storage.get("max_description_chars", 6000)),
        include_predicted_salary=bool(salary.get("include_predicted", False)),
        salary_min_valid=int(salary.get("min_valid", 15000)),
        salary_max_valid=int(salary.get("max_valid", 1_000_000)),
        failure_threshold=int(res.get("failure_threshold", 3)),
        cooldown_hours=float(res.get("cooldown_hours", 6)),
        max_cooldown_hours=float(res.get("max_cooldown_hours", 168)),
        retries=int(res.get("retries", 3)),
        timeout_seconds=float(res.get("timeout_seconds", 20)),
        skills=dict(raw.get("skills", {})),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
