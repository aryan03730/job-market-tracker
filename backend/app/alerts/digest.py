"""Builds and sends each confirmed subscriber a digest of postings that are new since
their last email. Runs after every refresh; never breaks the refresh if email fails."""
from __future__ import annotations

import html
import logging
from datetime import timedelta

from sqlalchemy import select

from ..db import Posting, SkillCount, Subscriber, utcnow
from .sender import Email, SendError, SenderUnavailable, make_sender
from .subscriptions import describe

log = logging.getLogger(__name__)


def _money(lo, hi):
    if not lo:
        return ""
    if lo == hi:
        return f"${lo / 1000:.0f}k"
    return f"${lo / 1000:.0f}k–${hi / 1000:.0f}k"


def matching_postings(session, sub: Subscriber, limit: int) -> tuple[list[Posting], int]:
    since = max(d for d in (sub.last_sent_at, sub.confirmed_at, utcnow() - timedelta(days=2)) if d)
    stmt = select(Posting).where(Posting.first_seen_at > since)
    if sub.skill_list():
        stmt = stmt.where(Posting.id.in_(
            select(SkillCount.posting_id).where(SkillCount.skill.in_(sub.skill_list()))))
    if sub.keyword:
        stmt = stmt.where(Posting.title.ilike(f"%{sub.keyword}%"))
    if sub.remote_only:
        stmt = stmt.where(Posting.is_remote.is_(True))
    rows = session.scalars(stmt.order_by(Posting.posted_at.desc())).all()
    return rows[:limit], len(rows)


def build_digest(sub: Subscriber, postings: list[Posting], total: int, settings) -> Email:
    api, site = settings.public_api_url, settings.frontend_url
    unsub = f"{api}/alerts/unsubscribe?token={sub.unsubscribe_token}"
    n = total
    subject = f"{n} new job{'s' if n != 1 else ''} for {describe(sub)}"[:150]

    lines, items = [], []
    for p in postings:
        meta = " · ".join(x for x in (p.company, p.location, _money(p.salary_min, p.salary_max)) if x)
        lines.append(f"- {p.title} ({meta})\n  {p.url}")
        items.append(
            f'<li style="margin-bottom:12px"><a href="{html.escape(p.url)}" '
            f'style="font-weight:600;color:#2a78d6">{html.escape(p.title)}</a><br>'
            f'<span style="color:#555">{html.escape(meta)}</span></li>')
    more = total - len(postings)
    more_text = f"\n…and {more} more on the dashboard." if more > 0 else ""
    site_text = f"\nDashboard: {site}" if site else ""

    text = (f"New postings matching {describe(sub)}:\n\n" + "\n".join(lines) + more_text + site_text
            + f"\n\nUnsubscribe: {unsub}")
    body = (f"<p>New postings matching <b>{html.escape(describe(sub))}</b>:</p><ul>"
            + "".join(items) + "</ul>"
            + (f"<p>…and {more} more on the dashboard.</p>" if more > 0 else "")
            + (f'<p><a href="{html.escape(site)}">Open the dashboard</a></p>' if site else "")
            + f'<p style="color:#888;font-size:12px">You get this because you subscribed to '
              f'Job Market Tracker alerts. <a href="{html.escape(unsub)}">Unsubscribe</a></p>')
    headers = {"List-Unsubscribe": f"<{unsub}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}
    return Email(sub.email, subject, text, body, headers)


def send_alerts(db, settings, sender=None) -> dict:
    """Returns a small report. Skips quietly when email is not configured."""
    if not settings.alerts_enabled:
        return {"status": "skipped", "reason": "disabled in tracker.toml"}
    sender = sender or make_sender(settings)
    if sender is None:
        return {"status": "skipped", "reason": "email not configured (SMTP_* settings)"}
    if not settings.public_api_url:
        return {"status": "skipped", "reason": "PUBLIC_API_URL not set (needed for unsubscribe links)"}

    report = {"status": "ok", "sent": 0, "no_new_jobs": 0, "failed": 0}
    with db.session() as s:
        subs = s.scalars(select(Subscriber).where(Subscriber.confirmed.is_(True))
                         .order_by(Subscriber.last_sent_at.asc().nullsfirst())).all()
        work = []
        for sub in subs:
            postings, total = matching_postings(s, sub, settings.max_postings_per_email)
            if not postings:
                report["no_new_jobs"] += 1
                continue
            work.append((sub.id, build_digest(sub, postings, total, settings)))
    if not work:
        return report

    work = work[: settings.max_emails_per_run]
    try:
        with sender as conn:
            for sub_id, email in work:
                try:
                    conn.send(email)
                except SendError as exc:
                    log.warning("Alert to subscriber %s failed: %s", sub_id, exc)
                    report["failed"] += 1
                    _mark(db, sub_id, ok=False)
                    continue
                report["sent"] += 1
                _mark(db, sub_id, ok=True)
    except SenderUnavailable as exc:
        log.error("Email server unavailable: %s", exc)
        report.update(status="failed", error=str(exc)[:300])
    return report


def _mark(db, sub_id: int, ok: bool) -> None:
    with db.session() as s:
        sub = s.get(Subscriber, sub_id)
        if sub is None:
            return
        if ok:
            sub.last_sent_at, sub.failures = utcnow(), 0
        else:
            sub.failures = (sub.failures or 0) + 1
            if sub.failures >= 5:          # address keeps bouncing: stop emailing it
                sub.confirmed = False
