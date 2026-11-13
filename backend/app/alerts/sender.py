"""Sends email. SMTP works with Gmail (app password), Brevo, Resend, SendGrid and others."""
from __future__ import annotations

import logging
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

log = logging.getLogger(__name__)


@dataclass
class Email:
    to: str
    subject: str
    text: str
    html: str
    headers: dict[str, str] = field(default_factory=dict)


class SendError(Exception):
    """One message failed (bad address, temporary error)."""


class SenderUnavailable(Exception):
    """The mail server itself refused us (wrong password, blocked). Stop sending this run."""


class SmtpSender:
    def __init__(self, settings):
        self.s = settings
        self._conn: smtplib.SMTP | None = None

    def __enter__(self):
        try:
            if self.s.smtp_port == 465:
                conn = smtplib.SMTP_SSL(self.s.smtp_host, 465, timeout=30,
                                        context=ssl.create_default_context())
            else:
                conn = smtplib.SMTP(self.s.smtp_host, self.s.smtp_port, timeout=30)
                conn.starttls(context=ssl.create_default_context())
            conn.login(self.s.smtp_user, self.s.smtp_password)
        except (smtplib.SMTPException, OSError) as exc:
            raise SenderUnavailable(f"could not log in to {self.s.smtp_host}: {exc}") from exc
        self._conn = conn
        return self

    def __exit__(self, *exc):
        if self._conn:
            try:
                self._conn.quit()
            except (smtplib.SMTPException, OSError):
                pass

    def send(self, email: Email) -> None:
        msg = EmailMessage()
        msg["From"] = formataddr(("Job Market Tracker", self.s.alert_from))
        msg["To"] = email.to
        msg["Subject"] = email.subject
        msg["Message-ID"] = make_msgid(domain=self.s.alert_from.split("@")[-1])
        for k, v in email.headers.items():
            msg[k] = v
        msg.set_content(email.text)
        msg.add_alternative(email.html, subtype="html")
        try:
            self._conn.send_message(msg)
        except smtplib.SMTPServerDisconnected as exc:
            raise SenderUnavailable(str(exc)) from exc
        except smtplib.SMTPException as exc:
            raise SendError(str(exc)) from exc


class ConsoleSender:
    """Prints emails instead of sending them. For trying alerts locally."""

    def __init__(self, settings=None):
        self.sent: list[Email] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def send(self, email: Email) -> None:
        self.sent.append(email)
        print(f"\n----- EMAIL to {email.to} -----\nSubject: {email.subject}\n\n{email.text}\n")


def make_sender(settings):
    """Returns a sender, or None when email is not configured (alerts are then skipped)."""
    mode = settings.email_mode
    if mode == "smtp":
        return SmtpSender(settings)
    if mode == "console":
        return ConsoleSender(settings)
    return None
