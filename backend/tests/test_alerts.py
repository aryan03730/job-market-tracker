"""Email alerts: double opt-in, unsubscribe, rate limits and the daily digest. No real email."""
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select

from app.alerts import subscriptions
from app.alerts.digest import send_alerts
from app.alerts.sender import ConsoleSender, SendError, SenderUnavailable
from app.db import Posting, SkillCount, Subscriber, utcnow
from app.pipeline.refresh import run_refresh
from tests.fake_http import FakeSession


class FakeSender(ConsoleSender):
    def send(self, email):
        self.sent.append(email)


@pytest.fixture
def alert_settings(settings, monkeypatch):
    settings.alerts_console = True
    settings.public_api_url = "https://api.example.com"
    settings.frontend_url = "https://site.example.com"
    return settings


@pytest.fixture
def sender(monkeypatch):
    fake = FakeSender()
    monkeypatch.setattr("app.routes.make_sender", lambda settings: fake)
    return fake


def token_from(email, path):
    link = next(w for w in email.text.split() if path in w)
    return parse_qs(urlparse(link).query)["token"][0]


def add_posting(db, title="Python Engineer", skills=("Python",), remote=True, age_minutes=5, **kw):
    with db.session() as s:
        p = Posting(source="test", external_id=title + str(age_minutes), fingerprint=title + str(age_minutes),
                    title=title, company="Acme", location="Remote (US)", is_remote=remote,
                    url="https://example.com/job", posted_at=utcnow(),
                    first_seen_at=utcnow() - timedelta(minutes=age_minutes),
                    last_seen_at=utcnow(), salary_is_predicted=False, **kw)
        for sk in skills:
            p.skills.append(SkillCount(skill=sk))
        s.add(p)


def subscribe_and_confirm(client, sender, **body):
    payload = {"email": "me@example.com", "skills": ["Python"], **body}
    assert client.post("/alerts/subscribe", json=payload).status_code == 202
    token = token_from(sender.sent[-1], "/alerts/confirm")
    assert client.get(f"/alerts/confirm?token={token}").status_code == 200
    db = client.application.config["DB"]
    with db.session() as s:  # pretend they confirmed an hour ago, before today's postings
        s.scalar(select(Subscriber)).confirmed_at = utcnow() - timedelta(hours=1)


# ---------------------------------------------------------------- subscribe flow

def test_status_reports_enabled_only_when_email_configured(client, alert_settings):
    assert client.get("/alerts/status").json["enabled"] is True
    alert_settings.alerts_console = False
    assert client.get("/alerts/status").json["enabled"] is False


def test_double_opt_in(client, db, alert_settings, sender):
    r = client.post("/alerts/subscribe", json={"email": " Me@Example.com ", "skills": ["Python", "Nope"]})
    assert r.status_code == 202
    assert sender.sent[0].to == "me@example.com"
    with db.session() as s:
        sub = s.scalar(select(Subscriber))
        assert sub.confirmed is False and sub.skills == "Python"  # unknown skill dropped

    token = token_from(sender.sent[0], "/alerts/confirm")
    page = client.get(f"/alerts/confirm?token={token}")
    assert page.status_code == 200 and b"subscribed" in page.data
    assert client.get(f"/alerts/confirm?token={token}").status_code == 404  # single use
    with db.session() as s:
        assert s.scalar(select(Subscriber)).confirmed is True


@pytest.mark.parametrize("email", ["", "nope", "a@b", "a b@c.com", "x" * 250 + "@a.com", "a@b.com,c@d.com"])
def test_rejects_bad_email(client, alert_settings, sender, email):
    r = client.post("/alerts/subscribe", json={"email": email})
    assert r.status_code == 400 and not sender.sent


def test_cooldown_prevents_inbox_spam(client, alert_settings, sender):
    for _ in range(3):
        assert client.post("/alerts/subscribe", json={"email": "me@example.com"}).status_code == 202
    assert len(sender.sent) == 1


def test_daily_confirmation_cap(client, alert_settings, sender):
    alert_settings.max_confirmations_per_day = 2
    for i in range(2):
        assert client.post("/alerts/subscribe", json={"email": f"u{i}@example.com"}).status_code == 202
    r = client.post("/alerts/subscribe", json={"email": "u9@example.com"})
    assert r.status_code == 400 and "paused" in r.json["error"]


def test_subscribe_when_email_not_configured(client, settings):
    r = client.post("/alerts/subscribe", json={"email": "me@example.com"})
    assert r.status_code == 400 and "not switched on" in r.json["error"]


def test_failed_confirmation_send_allows_retry(client, db, alert_settings, monkeypatch):
    class Broken(FakeSender):
        def send(self, email):
            raise SendError("mailbox unavailable")
    monkeypatch.setattr("app.routes.make_sender", lambda s: Broken())
    assert client.post("/alerts/subscribe", json={"email": "me@example.com"}).status_code == 400
    with db.session() as s:
        assert s.scalar(select(Subscriber)).confirm_sent_at is None


def test_unsubscribe_removes_email(client, db, alert_settings, sender):
    subscribe_and_confirm(client, sender)
    with db.session() as s:
        token = s.scalar(select(Subscriber)).unsubscribe_token
    assert b"Unsubscribed" in client.get(f"/alerts/unsubscribe?token={token}").data
    assert client.post(f"/alerts/unsubscribe?token={token}").status_code == 204  # one-click, idempotent
    with db.session() as s:
        assert s.scalar(select(Subscriber)) is None


def test_confirmation_page_escapes_html(client, db, alert_settings, sender):
    subscribe_and_confirm(client, sender, keyword="<script>alert(1)</script>")
    # the keyword is shown on pages and emails only in escaped form
    assert "<script>" not in sender.sent[0].html


# ---------------------------------------------------------------- digest

def test_digest_matches_filters_and_never_repeats(client, db, alert_settings, sender):
    subscribe_and_confirm(client, sender, remote_only=True)
    add_posting(db, "Python Engineer", ("Python",), remote=True, salary_min=120000, salary_max=150000)
    add_posting(db, "Java Engineer", ("Java",), remote=True, age_minutes=6)
    add_posting(db, "Onsite Python Dev", ("Python",), remote=False, age_minutes=7)

    out = FakeSender()
    report = send_alerts(db, alert_settings, sender=out)
    assert report["sent"] == 1
    mail = out.sent[0]
    assert "Python Engineer" in mail.text and "$120k–$150k" in mail.text
    assert "Java Engineer" not in mail.text and "Onsite" not in mail.text
    assert "https://api.example.com/alerts/unsubscribe?token=" in mail.text
    assert mail.headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"

    again = FakeSender()
    assert send_alerts(db, alert_settings, sender=again)["no_new_jobs"] == 1 and not again.sent


def test_unconfirmed_get_nothing(client, db, alert_settings, sender):
    client.post("/alerts/subscribe", json={"email": "me@example.com"})
    add_posting(db)
    out = FakeSender()
    send_alerts(db, alert_settings, sender=out)
    assert not out.sent


def test_keyword_and_limit(client, db, alert_settings, sender):
    subscribe_and_confirm(client, sender, skills=[], keyword="backend")
    for i in range(5):
        add_posting(db, f"Backend Developer {i}", (), age_minutes=i + 1)
    add_posting(db, "Frontend Developer", (), age_minutes=9)
    alert_settings.max_postings_per_email = 3
    out = FakeSender()
    send_alerts(db, alert_settings, sender=out)
    assert out.sent[0].subject.startswith("5 new jobs")
    assert out.sent[0].text.count("Backend Developer") == 3 and "2 more" in out.sent[0].text


def test_skips_cleanly_without_config(db, settings):
    assert send_alerts(db, settings)["status"] == "skipped"
    settings.alerts_console = True
    assert "PUBLIC_API_URL" in send_alerts(db, settings)["reason"]


def test_server_down_does_not_crash(client, db, alert_settings, sender):
    subscribe_and_confirm(client, sender)
    add_posting(db)

    class Down(FakeSender):
        def __enter__(self):
            raise SenderUnavailable("login failed")
    report = send_alerts(db, alert_settings, sender=Down())
    assert report["status"] == "failed" and "login failed" in report["error"]


def test_bouncing_address_is_stopped_after_5_failures(client, db, alert_settings, sender):
    subscribe_and_confirm(client, sender)

    class Bounce(FakeSender):
        def send(self, email):
            raise SendError("550 no such user")
    for i in range(5):
        add_posting(db, f"Python Job {i}", age_minutes=1)
        send_alerts(db, alert_settings, sender=Bounce())
    with db.session() as s:
        assert s.scalar(select(Subscriber)).confirmed is False


def test_refresh_sends_alerts_after_new_postings(client, db, alert_settings, sender):
    subscribe_and_confirm(client, sender, skills=[])
    out = FakeSender()
    summary = run_refresh(db, alert_settings, env={}, http_factory=FakeSession,
                          only=["remoteok"], alert_sender=out)
    assert summary["alerts"]["sent"] == 1 and "new job" in out.sent[0].subject
