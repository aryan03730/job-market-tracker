"""Subscribe, confirm and unsubscribe. Double opt-in: nobody is emailed alerts until they
click the confirmation link, so a stranger cannot sign someone else up."""
from __future__ import annotations

import html
import logging
import re
import secrets
from datetime import timedelta

from sqlalchemy import func, select

from ..db import Subscriber, utcnow
from .sender import Email, SendError, SenderUnavailable

log = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"^[^@\s,;<>]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,}$")


class SubscribeError(Exception):
    """Bad input; message is safe to show to the user."""


def normalize_request(data: dict, settings) -> dict:
    email = str(data.get("email") or "").strip().lower()
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise SubscribeError("Please enter a valid email address.")
    allowed = set(settings.skills)
    skills = data.get("skills") or []
    if not isinstance(skills, list):
        raise SubscribeError("Skills must be a list.")
    skills = sorted({str(s) for s in skills if str(s) in allowed})[:10]
    keyword = re.sub(r"\s+", " ", str(data.get("keyword") or "")).strip()[:100]
    return {"email": email, "skills": skills, "keyword": keyword or None,
            "remote_only": bool(data.get("remote_only"))}


def confirmation_email(sub: Subscriber, api_url: str) -> Email:
    link = f"{api_url}/alerts/confirm?token={sub.confirm_token}"
    what = describe(sub)
    text = (f"Confirm your daily job alerts for {what}:\n{link}\n\n"
            "If you did not ask for this, ignore this email and nothing will be sent.")
    body = (f"<p>Confirm your daily job alerts for <b>{html.escape(what)}</b>.</p>"
            f'<p><a href="{html.escape(link)}">Confirm my alerts</a></p>'
            "<p style='color:#666'>If you did not ask for this, ignore this email "
            "and nothing will be sent.</p>")
    return Email(sub.email, "Confirm your Job Market Tracker alerts", text, body)


def describe(sub: Subscriber) -> str:
    parts = []
    if sub.skill_list():
        parts.append(", ".join(sub.skill_list()))
    if sub.keyword:
        parts.append(f'titles with "{sub.keyword}"')
    if not parts:
        parts.append("all new software postings")
    if sub.remote_only:
        parts.append("remote only")
    return "; ".join(parts)


def subscribe(db, settings, sender, data: dict, api_url: str) -> str:
    """Creates or updates a subscription and sends a confirmation email.
    Always returns the same message, so the API never reveals who is subscribed."""
    req = normalize_request(data, settings)
    if sender is None:
        raise SubscribeError("Email alerts are not switched on yet.")
    done = "Check your inbox and click the link to confirm your alerts."
    now = utcnow()
    with db.session() as s:
        sub = s.scalar(select(Subscriber).where(Subscriber.email == req["email"]))
        if sub is None:
            sub = Subscriber(email=req["email"], unsubscribe_token=secrets.token_urlsafe(32),
                             confirmed=False, failures=0, created_at=now)
            s.add(sub)
        # Signing up again with the same address updates the preferences.
        sub.skills = ",".join(req["skills"]) or None
        sub.keyword = req["keyword"]
        sub.remote_only = req["remote_only"]

        cooldown = timedelta(minutes=settings.confirm_cooldown_minutes)
        if sub.confirm_sent_at and now - sub.confirm_sent_at < cooldown:
            return done  # quietly avoid spamming the same inbox
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        sent_today = s.scalar(select(func.count(Subscriber.id))
                              .where(Subscriber.confirm_sent_at >= day_start)) or 0
        if sent_today >= settings.max_confirmations_per_day:
            raise SubscribeError("Sign-ups are paused for today. Please try again tomorrow.")
        sub.confirm_token = secrets.token_urlsafe(32)
        sub.confirm_sent_at = now
        s.flush()
        sub_id = sub.id
        email = confirmation_email(sub, api_url)

    try:
        with sender as conn:
            conn.send(email)
    except (SendError, SenderUnavailable) as exc:
        log.error("Confirmation email failed: %s", exc)
        with db.session() as s:  # let them retry straight away
            row = s.get(Subscriber, sub_id)
            if row:
                row.confirm_sent_at = None
        raise SubscribeError("We could not send the confirmation email. Please try again later.")
    return done


def confirm(db, token: str) -> Subscriber | None:
    if not token:
        return None
    with db.session() as s:
        sub = s.scalar(select(Subscriber).where(Subscriber.confirm_token == token))
        if sub is None:
            return None
        sub.confirmed = True
        sub.confirm_token = None
        sub.confirmed_at = sub.confirmed_at or utcnow()
        sub.failures = 0
        s.flush()
        s.expunge(sub)
        return sub


def unsubscribe(db, token: str) -> bool:
    if not token:
        return False
    with db.session() as s:
        sub = s.scalar(select(Subscriber).where(Subscriber.unsubscribe_token == token))
        if sub is None:
            return False
        s.delete(sub)  # remove the email address completely
        return True
