"""The daily refresh: fetch from every available provider, clean, dedupe, store, prune.

Self-healing rules
------------------
* A provider with missing keys is skipped, never an error.
* Each provider runs in isolation: one crashing never stops the others.
* After `failure_threshold` failures in a row a provider rests (cooldown), and the
  rest doubles each further failure, up to `max_cooldown_hours`. When the cooldown
  ends it gets one trial run; a success resets it fully.
* A daily request budget per provider protects free tiers and fair-use rules.
* A run that crashed mid-way (status 'running' for over an hour) is marked failed,
  so it never blocks future runs.
* Postings unseen for `retention_days` are deleted to keep the free database small.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from datetime import date, timedelta

import requests
from sqlalchemy import delete, func, select

from ..db import Database, Posting, ProviderHealth, RefreshRun, SkillCount, utcnow
from ..providers import REGISTRY, BudgetExhausted, ProviderError
from .clean import CleanJob, clean_job
from .skills import SkillMatcher

log = logging.getLogger(__name__)


# ---------------------------------------------------------------- health helpers

def _health(session, name: str) -> ProviderHealth:
    h = session.get(ProviderHealth, name)
    if h is None:
        h = ProviderHealth(name=name, consecutive_failures=0, requests_today=0,
                           total_runs=0, total_failures=0, last_fetched=0, last_new=0)
        session.add(h)
    return h


def _budget_left(h: ProviderHealth, budget: int) -> int:
    if h.requests_day != date.today():
        h.requests_day, h.requests_today = date.today(), 0
    return max(0, budget - (h.requests_today or 0))


def _record_failure(h: ProviderHealth, error: str, settings) -> None:
    now = utcnow()
    h.consecutive_failures = (h.consecutive_failures or 0) + 1
    h.total_failures = (h.total_failures or 0) + 1
    h.last_error = error[:1000]
    over = h.consecutive_failures - settings.failure_threshold
    if over >= 0:
        hours = min(settings.cooldown_hours * (2 ** over), settings.max_cooldown_hours)
        h.cooldown_until = now + timedelta(hours=hours)
        log.warning("%s: %s failures in a row, resting for %.0fh", h.name, h.consecutive_failures, hours)


def _record_success(h: ProviderHealth) -> None:
    h.consecutive_failures = 0
    h.cooldown_until = None
    h.last_success_at = utcnow()
    h.last_error = None


# ---------------------------------------------------------------- run lock

def _start_run(session) -> RefreshRun | None:
    hour_ago = utcnow() - timedelta(hours=1)
    stale = session.scalars(select(RefreshRun).where(RefreshRun.status == "running")).all()
    for run in stale:
        if run.started_at < hour_ago:
            run.status, run.finished_at = "failed", utcnow()
            run.details = json.dumps({"error": "run did not finish (crashed or timed out)"})
        else:
            return None  # another run is genuinely in progress
    run = RefreshRun(status="running", started_at=utcnow())
    session.add(run)
    session.flush()
    return run


def hours_since_last_success(db: Database) -> float | None:
    with db.session() as s:
        last = s.scalar(select(func.max(RefreshRun.finished_at))
                        .where(RefreshRun.status.in_(["ok", "partial"])))
    if not last:
        return None
    return (utcnow() - last).total_seconds() / 3600


# ---------------------------------------------------------------- main

def run_refresh(db: Database, settings, env: dict | None = None,
                http_factory=requests.Session, only: list[str] | None = None) -> dict:
    env = dict(os.environ if env is None else env)
    db.create_all()
    matcher = SkillMatcher(settings.skills)
    us_only = (settings.country or "").lower() == "us"

    with db.session() as s:
        run = _start_run(s)
        if run is None:
            log.info("Another refresh is already running; exiting.")
            return {"status": "skipped", "reason": "already_running"}
        run_id = run.id

    report: dict[str, dict] = {}
    collected: list[CleanJob] = []
    skipped_reasons: dict[str, int] = {}

    for name, cls in REGISTRY.items():
        if only and name not in only:
            continue
        opts = settings.provider(name)
        entry: dict = {"status": "skipped"}
        report[name] = entry

        if not opts.get("enabled", False):
            entry["reason"] = "disabled in tracker.toml"
            continue
        missing = cls.missing_env(env)
        if missing:
            entry["reason"] = f"missing env: {', '.join(missing)}"
            continue

        with db.session() as s:
            h = _health(s, name)
            if h.cooldown_until and h.cooldown_until > utcnow():
                entry["reason"] = f"cooling down until {h.cooldown_until:%Y-%m-%d %H:%M} UTC"
                continue
            budget = _budget_left(h, int(opts.get("daily_request_budget", 10)))
            if budget <= 0:
                entry["reason"] = "daily request budget used"
                continue

        provider = cls(settings, opts, env, budget, session=http_factory())
        raw_count, kept, error = 0, 0, None
        try:
            for raw in provider.fetch():
                raw_count += 1
                job, reason = clean_job(raw, settings, us_only, cls.country_scoped)
                if job is None:
                    skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
                    continue
                collected.append(job)
                kept += 1
        except BudgetExhausted as exc:
            if raw_count == 0:
                error = str(exc)
        except ProviderError as exc:
            error = str(exc)
        except Exception as exc:  # unexpected shape change, bug, etc.
            log.exception("%s crashed", name)
            error = f"{type(exc).__name__}: {exc}"

        if error is None and raw_count == 0:
            error = "returned 0 jobs (API change or empty feed)"

        with db.session() as s:
            h = _health(s, name)
            _budget_left(h, 0)
            h.requests_today = (h.requests_today or 0) + provider.requests_made
            h.total_runs = (h.total_runs or 0) + 1
            h.last_run_at = utcnow()
            h.last_fetched = raw_count
            if error:
                _record_failure(h, error, settings)
                entry.update(status="failed", error=error, fetched=raw_count)
            else:
                _record_success(h)
                entry.update(status="ok", fetched=raw_count, kept=kept)
        entry["requests"] = provider.requests_made
        log.info("%s: %s (fetched %s, kept %s)", name, entry["status"], raw_count, kept)

    inserted, updated, per_source_new = _store(db, collected, matcher)
    with db.session() as s:
        for name, entry in report.items():
            if entry.get("status") == "ok":
                entry["new"] = per_source_new.get(name, 0)
                _health(s, name).last_new = entry["new"]
    pruned = _prune(db, settings.retention_days)

    ok = [n for n, e in report.items() if e.get("status") == "ok"]
    failed = [n for n, e in report.items() if e.get("status") == "failed"]
    status = "ok" if ok and not failed else "partial" if ok else "failed"

    summary = {
        "run_id": run_id, "status": status, "fetched": len(collected) + sum(skipped_reasons.values()),
        "inserted": inserted, "updated": updated, "pruned": pruned,
        "skipped": skipped_reasons, "providers": report,
    }
    with db.session() as s:
        run = s.get(RefreshRun, run_id)
        run.status, run.finished_at = status, utcnow()
        run.fetched, run.inserted, run.updated = summary["fetched"], inserted, updated
        run.pruned, run.skipped = pruned, sum(skipped_reasons.values())
        run.details = json.dumps(summary, default=str)
    return summary


def _store(db: Database, jobs: list[CleanJob], matcher: SkillMatcher) -> tuple[int, int, dict]:
    """Insert new postings, touch last_seen on known ones. Works on SQLite and Postgres."""
    unique: dict[str, CleanJob] = {}
    seen_ids: set[tuple[str, str]] = set()
    for j in jobs:
        if (j.source, j.external_id) in seen_ids and j.fingerprint not in unique:
            continue
        seen_ids.add((j.source, j.external_id))
        if j.fingerprint not in unique:
            unique[j.fingerprint] = j
        elif j.salary_min and not unique[j.fingerprint].salary_min:
            unique[j.fingerprint] = j  # prefer the copy that has a salary

    inserted = updated = 0
    per_source: dict[str, int] = {}
    now = utcnow()
    fps = list(unique)
    for i in range(0, len(fps), 500):
        chunk = fps[i:i + 500]
        with db.session() as s:
            existing = {p.fingerprint: p for p in s.scalars(
                select(Posting).where(Posting.fingerprint.in_(chunk)))}
            # Also catch same (source, external_id) whose title changed slightly.
            for fp in chunk:
                job = unique[fp]
                post = existing.get(fp) or s.scalar(select(Posting).where(
                    Posting.source == job.source, Posting.external_id == job.external_id))
                if post:
                    post.last_seen_at = now
                    if job.salary_min and not post.salary_min:
                        post.salary_min, post.salary_max = job.salary_min, job.salary_max
                        post.salary_is_predicted = job.salary_is_predicted
                    updated += 1
                    continue
                data = asdict(job)
                post = Posting(**data, first_seen_at=now, last_seen_at=now)
                for skill in matcher.find(job.title, job.description):
                    post.skills.append(SkillCount(skill=skill))
                s.add(post)
                s.flush()
                inserted += 1
                per_source[job.source] = per_source.get(job.source, 0) + 1
    return inserted, updated, per_source


def _prune(db: Database, retention_days: int) -> int:
    cutoff = utcnow() - timedelta(days=retention_days)
    with db.session() as s:
        old_ids = select(Posting.id).where(Posting.last_seen_at < cutoff)
        s.execute(delete(SkillCount).where(SkillCount.posting_id.in_(old_ids)))
        res = s.execute(delete(Posting).where(Posting.last_seen_at < cutoff))
        # Keep only the last 200 run records.
        keep = select(RefreshRun.id).order_by(RefreshRun.id.desc()).limit(200).scalar_subquery()
        s.execute(delete(RefreshRun).where(RefreshRun.id.not_in(keep)))
        return res.rowcount or 0
