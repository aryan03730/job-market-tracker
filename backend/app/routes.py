"""HTTP API. Every endpoint reads from the database only; no visitor triggers a job-API call."""
from __future__ import annotations

import json
import logging
import os
import statistics
import threading
from datetime import timedelta

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import func, or_, select, text

from .db import Posting, ProviderHealth, RefreshRun, SkillCount, utcnow
from .pipeline.refresh import hours_since_last_success, run_refresh
from .providers import REGISTRY

log = logging.getLogger(__name__)
bp = Blueprint("api", __name__)
_refresh_lock = threading.Lock()


def _db():
    return current_app.config["DB"]


def _settings():
    return current_app.config["SETTINGS"]


def _int_arg(name: str, default: int, lo: int = 1, hi: int = 500) -> int:
    try:
        return max(lo, min(hi, int(request.args.get(name, default))))
    except (TypeError, ValueError):
        return default


def _apply_filters(stmt, args):
    q = (args.get("q") or "").strip()
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Posting.title.ilike(like), Posting.company.ilike(like)))
    if args.get("source"):
        stmt = stmt.where(Posting.source.in_(args["source"].split(",")))
    if args.get("skill"):
        stmt = stmt.where(Posting.id.in_(select(SkillCount.posting_id).where(SkillCount.skill == args["skill"])))
    if args.get("remote") in ("true", "1"):
        stmt = stmt.where(Posting.is_remote.is_(True))
    if args.get("remote") in ("false", "0"):
        stmt = stmt.where(Posting.is_remote.is_(False))
    if args.get("state"):
        stmt = stmt.where(Posting.state == args["state"].upper())
    if args.get("has_salary") in ("true", "1"):
        stmt = stmt.where(Posting.salary_min.is_not(None))
    if args.get("days"):
        try:
            stmt = stmt.where(Posting.posted_at >= utcnow() - timedelta(days=int(args["days"])))
        except ValueError:
            pass
    return stmt


def _maybe_self_refresh() -> None:
    """Optional safety net: if data is stale and AUTO_REFRESH_IF_STALE_HOURS is set,
    start a refresh in the background. GitHub Actions remains the main scheduler."""
    limit = os.environ.get("AUTO_REFRESH_IF_STALE_HOURS")
    if not limit:
        return
    age = hours_since_last_success(_db())
    if age is not None and age < float(limit):
        return
    _start_background_refresh(current_app._get_current_object())


def _start_background_refresh(app) -> bool:
    if not _refresh_lock.acquire(blocking=False):
        return False

    def work():
        try:
            run_refresh(app.config["DB"], app.config["SETTINGS"])
        except Exception:  # pragma: no cover
            log.exception("Background refresh failed")
        finally:
            _refresh_lock.release()

    threading.Thread(target=work, daemon=True).start()
    return True


# ---------------------------------------------------------------- endpoints

@bp.get("/health")
def health():
    db_ok = True
    try:
        with _db().session() as s:
            s.execute(text("SELECT 1"))
            total = s.scalar(select(func.count(Posting.id))) or 0
            last = s.scalars(select(RefreshRun).order_by(RefreshRun.id.desc()).limit(1)).first()
            last_run = last.to_dict() if last else None
    except Exception as exc:
        db_ok, total, last_run = False, 0, {"error": str(exc)}
    age = hours_since_last_success(_db()) if db_ok else None
    stale = age is None or age > 30
    if db_ok:
        _maybe_self_refresh()
    return jsonify({
        "status": "ok" if db_ok and not stale else "degraded",
        "database": "ok" if db_ok else "error",
        "postings": total,
        "hours_since_last_success": round(age, 1) if age is not None else None,
        "stale": stale,
        "last_run": last_run,
        "server_time": utcnow().isoformat(),
    }), (200 if db_ok else 503)


@bp.get("/postings")
def postings():
    limit = _int_arg("limit", 20, 1, 100)
    offset = _int_arg("offset", 0, 0, 100_000)
    with _db().session() as s:
        base = _apply_filters(select(Posting), request.args)
        total = s.scalar(select(func.count()).select_from(base.subquery()))
        rows = s.scalars(base.order_by(Posting.posted_at.desc(), Posting.id.desc())
                         .offset(offset).limit(limit)).all()
        items = [r.to_dict() for r in rows]
    return jsonify({"total": total, "limit": limit, "offset": offset, "items": items})


@bp.get("/stats/daily")
def stats_daily():
    days = _int_arg("days", 30, 1, 365)
    since = utcnow() - timedelta(days=days)
    day = func.date(Posting.posted_at)
    with _db().session() as s:
        rows = s.execute(select(day, Posting.source, func.count(Posting.id))
                         .where(Posting.posted_at >= since)
                         .group_by(day, Posting.source).order_by(day)).all()
    by_day: dict[str, dict] = {}
    for d, source, n in rows:
        key = str(d)[:10]
        entry = by_day.setdefault(key, {"date": key, "total": 0})
        entry[source] = n
        entry["total"] += n
    # Fill missing days with zeros so the chart has no gaps.
    out = []
    for i in range(days, -1, -1):
        key = (utcnow() - timedelta(days=i)).date().isoformat()
        out.append(by_day.get(key, {"date": key, "total": 0}))
    return jsonify(out)


@bp.get("/stats/skills")
def stats_skills():
    limit = _int_arg("limit", 30, 1, 100)
    with _db().session() as s:
        filtered = _apply_filters(select(Posting.id), request.args).subquery()
        total = s.scalar(select(func.count()).select_from(filtered)) or 0
        rows = s.execute(select(SkillCount.skill, func.count(SkillCount.id).label("n"))
                         .where(SkillCount.posting_id.in_(select(filtered.c.id)))
                         .group_by(SkillCount.skill).order_by(text("n DESC")).limit(limit)).all()
    return jsonify([{"skill": k, "count": n, "share": round(n / total, 3) if total else 0}
                    for k, n in rows])


@bp.get("/stats/salary")
def stats_salary():
    settings = _settings()
    with _db().session() as s:
        stmt = _apply_filters(select(Posting.salary_min, Posting.salary_max), request.args) \
            .where(Posting.salary_min.is_not(None))
        if not settings.include_predicted_salary:
            stmt = stmt.where(Posting.salary_is_predicted.is_(False))
        rows = s.execute(stmt).all()
        total = s.scalar(select(func.count()).select_from(
            _apply_filters(select(Posting.id), request.args).subquery())) or 0
    mids = sorted((lo + hi) / 2 for lo, hi in rows)
    buckets: dict[int, int] = {}
    for m in mids:
        b = int(min(m, 299_999) // 20_000) * 20_000
        buckets[b] = buckets.get(b, 0) + 1
    def pct(p):
        if not mids:
            return None
        return round(mids[min(len(mids) - 1, int(p * (len(mids) - 1)))], -3)
    return jsonify({
        "count": len(mids),
        "coverage": round(len(mids) / total, 3) if total else 0,
        "p25": pct(0.25), "median": round(statistics.median(mids), -3) if mids else None, "p75": pct(0.75),
        "buckets": [{"from": b, "to": b + 20_000,
                     "label": f"${b // 1000}k" + ("+" if b >= 280_000 else f"–{(b + 20_000) // 1000}k"),
                     "count": buckets[b]} for b in sorted(buckets)],
    })


@bp.get("/stats/summary")
def stats_summary():
    day_ago = utcnow() - timedelta(days=1)
    with _db().session() as s:
        total = s.scalar(select(func.count(Posting.id))) or 0
        new_24h = s.scalar(select(func.count(Posting.id)).where(Posting.first_seen_at >= day_ago)) or 0
        remote = s.scalar(select(func.count(Posting.id)).where(Posting.is_remote.is_(True))) or 0
        salary = s.scalar(select(func.count(Posting.id)).where(Posting.salary_min.is_not(None))) or 0
        companies = s.scalar(select(func.count(func.distinct(Posting.company)))) or 0
        by_source = dict(s.execute(select(Posting.source, func.count(Posting.id))
                                   .group_by(Posting.source)).all())
        states = s.execute(select(Posting.state, func.count(Posting.id).label("n"))
                           .where(Posting.state.is_not(None)).group_by(Posting.state)
                           .order_by(text("n DESC")).limit(10)).all()
    return jsonify({
        "total": total, "new_24h": new_24h, "companies": companies,
        "remote_share": round(remote / total, 3) if total else 0,
        "salary_share": round(salary / total, 3) if total else 0,
        "by_source": by_source,
        "top_states": [{"state": st, "count": n} for st, n in states],
    })


@bp.get("/providers")
def providers():
    settings = _settings()
    env = os.environ
    with _db().session() as s:
        health = {h.name: h.to_dict() for h in s.scalars(select(ProviderHealth))}
    out = []
    for name, cls in REGISTRY.items():
        opts = settings.provider(name)
        missing = cls.missing_env(env)
        h = health.get(name, {})
        if not opts.get("enabled"):
            state = "disabled"
        elif missing:
            state = "needs_key"
        elif h.get("cooldown_until") and h["cooldown_until"] > utcnow().isoformat():
            state = "cooling_down"
        elif h.get("consecutive_failures"):
            state = "failing"
        elif h.get("last_success_at"):
            state = "healthy"
        else:
            state = "waiting"
        out.append({"name": name, "state": state, "attribution": cls.attribution,
                    "homepage": cls.homepage, "missing_env": missing, **h})
    return jsonify(out)


@bp.get("/runs")
def runs():
    limit = _int_arg("limit", 10, 1, 50)
    with _db().session() as s:
        rows = s.scalars(select(RefreshRun).order_by(RefreshRun.id.desc()).limit(limit)).all()
        out = []
        for r in rows:
            d = r.to_dict()
            try:
                d["providers"] = (json.loads(r.details or "{}")).get("providers")
            except ValueError:
                d["providers"] = None
            out.append(d)
    return jsonify(out)


@bp.post("/admin/refresh")
def admin_refresh():
    token = _settings().admin_token
    if not token or request.headers.get("Authorization") != f"Bearer {token}":
        return jsonify({"error": "unauthorized"}), 401
    started = _start_background_refresh(current_app._get_current_object())
    return jsonify({"started": started}), 202 if started else 409


@bp.app_errorhandler(404)
def not_found(_e):
    return jsonify({"error": "not found"}), 404


@bp.app_errorhandler(500)
def server_error(e):  # pragma: no cover
    log.exception("Server error: %s", e)
    return jsonify({"error": "server error"}), 500
