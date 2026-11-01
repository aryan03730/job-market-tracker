import pytest

from app import create_app
from app.config import load_settings
from app.db import Database
from app.providers.base import Provider


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Retries back off with sleep(); tests should not wait."""
    monkeypatch.setattr(Provider, "_sleep", lambda self, s: None)


@pytest.fixture
def settings(tmp_path, monkeypatch):
    for var in ("DATABASE_URL", "ADZUNA_APP_ID", "ADZUNA_APP_KEY", "USAJOBS_API_KEY",
                "USAJOBS_EMAIL", "ADMIN_TOKEN", "AUTO_REFRESH_IF_STALE_HOURS", "TRACKER_KEYWORDS"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    s = load_settings()
    s.keywords = ["software engineer", "python developer"]
    s.retries = 2
    return s


@pytest.fixture
def db(settings):
    d = Database(settings.database_url)
    d.create_all()
    return d


@pytest.fixture
def client(settings, db):
    return create_app(settings, db).test_client()
