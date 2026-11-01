from datetime import timedelta

from sqlalchemy import func, select

from app.db import Posting, ProviderHealth, RefreshRun, SkillCount, utcnow
from app.pipeline.refresh import hours_since_last_success, run_refresh
from tests.fake_http import FakeResponse, FakeSession, demo_env


def count(db, model):
    with db.session() as s:
        return s.scalar(select(func.count()).select_from(model))


def test_full_refresh_stores_and_dedupes(db, settings):
    summary = run_refresh(db, settings, env=demo_env(), http_factory=FakeSession)
    assert summary["status"] == "ok"
    assert summary["inserted"] > 100 and count(db, SkillCount) > summary["inserted"]
    first = count(db, Posting)

    settings.raw["providers"]["remotive"]["daily_request_budget"] = 10  # allow a second call today
    again = run_refresh(db, settings, env=demo_env(), http_factory=FakeSession)
    assert again["inserted"] == 0 and count(db, Posting) == first  # idempotent


def test_providers_without_keys_are_skipped(db, settings):
    summary = run_refresh(db, settings, env={}, http_factory=FakeSession)
    assert summary["providers"]["adzuna"]["status"] == "skipped"
    assert "missing env" in summary["providers"]["adzuna"]["reason"]
    assert summary["providers"]["remotive"]["status"] == "ok"  # keyless sources keep it alive


class BrokenRemotive(FakeSession):
    def get(self, url, **kw):
        if "remotive" in url:
            return FakeResponse({}, 500)
        return super().get(url, **kw)


def test_failing_provider_is_isolated_and_rested(db, settings):
    settings.raw["providers"]["remotive"]["daily_request_budget"] = 100
    for _ in range(settings.failure_threshold):
        summary = run_refresh(db, settings, env={}, http_factory=BrokenRemotive, only=["remotive", "jobicy"])
        assert summary["providers"]["jobicy"]["status"] == "ok"
        assert summary["status"] == "partial"
    with db.session() as s:
        h = s.get(ProviderHealth, "remotive")
        assert h.consecutive_failures == settings.failure_threshold and h.cooldown_until > utcnow()
    summary = run_refresh(db, settings, env={}, http_factory=BrokenRemotive, only=["remotive"])
    assert "cooling down" in summary["providers"]["remotive"]["reason"]

    # After the rest, one good run resets it completely.
    with db.session() as s:
        s.get(ProviderHealth, "remotive").cooldown_until = utcnow() - timedelta(minutes=1)
    summary = run_refresh(db, settings, env={}, http_factory=FakeSession, only=["remotive"])
    assert summary["providers"]["remotive"]["status"] == "ok"
    with db.session() as s:
        assert s.get(ProviderHealth, "remotive").consecutive_failures == 0


class EmptyFeed(FakeSession):
    def get(self, url, **kw):
        return FakeResponse({"jobs": []})


def test_empty_feed_counts_as_failure(db, settings):
    summary = run_refresh(db, settings, env={}, http_factory=EmptyFeed, only=["remotive"])
    assert summary["status"] == "failed" and "0 jobs" in summary["providers"]["remotive"]["error"]


class Exploding(FakeSession):
    def get(self, url, **kw):
        if "jobicy" in url:
            return FakeResponse({"jobs": "not-a-list-anymore"})
        return super().get(url, **kw)


def test_unexpected_schema_does_not_crash_run(db, settings):
    summary = run_refresh(db, settings, env={}, http_factory=Exploding, only=["jobicy", "remoteok"])
    assert summary["providers"]["jobicy"]["status"] == "failed"
    assert summary["providers"]["remoteok"]["status"] == "ok"


def test_daily_budget_persists_between_runs(db, settings):
    settings.raw["providers"]["remotive"]["daily_request_budget"] = 1
    run_refresh(db, settings, env={}, http_factory=FakeSession, only=["remotive"])
    summary = run_refresh(db, settings, env={}, http_factory=FakeSession, only=["remotive"])
    assert summary["providers"]["remotive"]["reason"] == "daily request budget used"


def test_prune_and_crashed_run_recovery(db, settings):
    run_refresh(db, settings, env={}, http_factory=FakeSession, only=["remoteok"])
    with db.session() as s:
        for p in s.scalars(select(Posting)):
            p.last_seen_at = utcnow() - timedelta(days=settings.retention_days + 1)
        s.add(RefreshRun(status="running", started_at=utcnow() - timedelta(hours=3)))
    settings.raw["providers"]["remoteok"]["daily_request_budget"] = 0  # nothing new fetched
    summary = run_refresh(db, settings, env={}, http_factory=FakeSession, only=["remoteok"])
    assert summary["pruned"] > 0 and count(db, Posting) == 0 and count(db, SkillCount) == 0
    with db.session() as s:
        assert s.scalar(select(func.count()).where(RefreshRun.status == "running")) == 0


def test_concurrent_run_is_refused(db, settings):
    with db.session() as s:
        s.add(RefreshRun(status="running", started_at=utcnow()))
    assert run_refresh(db, settings, env={}, http_factory=FakeSession)["status"] == "skipped"


def test_hours_since_last_success(db, settings):
    assert hours_since_last_success(db) is None
    run_refresh(db, settings, env={}, http_factory=FakeSession, only=["remoteok"])
    assert hours_since_last_success(db) < 0.1
