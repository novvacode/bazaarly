"""Email delivery behind one interface (SPEC §15): Resend in production, SMTP (Mailpit) locally,
in-memory for tests. Only queue handlers send email."""

from __future__ import annotations

import asyncio
import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import make_msgid
from functools import lru_cache
from typing import Protocol

import httpx

from app.config import get_settings


@dataclass(frozen=True, slots=True)
class Email:
    to: str
    subject: str
    html: str
    text: str


class EmailSendError(Exception):
    pass


class EmailSender(Protocol):
    async def send(self, email: Email) -> None: ...


class SmtpEmailSender:
    def __init__(self, host: str, port: int, sender: str) -> None:
        self.host, self.port, self.sender = host, port, sender

    def _send_sync(self, email: Email) -> None:
        msg = EmailMessage()
        msg["From"] = self.sender
        msg["To"] = email.to
        msg["Subject"] = email.subject
        msg["Message-ID"] = make_msgid(domain="bazaarly.local")
        msg.set_content(email.text)
        msg.add_alternative(email.html, subtype="html")
        with smtplib.SMTP(self.host, self.port, timeout=10) as smtp:
            smtp.send_message(msg)

    async def send(self, email: Email) -> None:
        try:
            await asyncio.to_thread(self._send_sync, email)
        except (OSError, smtplib.SMTPException) as exc:
            raise EmailSendError(f"SMTP send failed: {exc}") from exc


class ResendEmailSender:
    URL = "https://api.resend.com/emails"

    def __init__(self, api_key: str, sender: str) -> None:
        self.api_key, self.sender = api_key, sender

    async def send(self, email: Email) -> None:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.post(
                self.URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "from": self.sender,
                    "to": [email.to],
                    "subject": email.subject,
                    "html": email.html,
                    "text": email.text,
                },
            )
        if res.status_code >= 400:
            raise EmailSendError(f"Resend returned {res.status_code}: {res.text[:200]}")


@dataclass
class MemoryEmailSender:
    """Collects messages instead of sending them (tests, `EMAIL_PROVIDER=memory`)."""

    sent: list[Email] = field(default_factory=list)

    async def send(self, email: Email) -> None:
        self.sent.append(email)


@lru_cache(maxsize=1)
def get_email_sender() -> EmailSender:
    s = get_settings()
    if s.email_provider == "resend":
        return ResendEmailSender(s.resend_api_key, s.email_from)
    if s.email_provider == "memory":
        return MemoryEmailSender()
    return SmtpEmailSender(s.smtp_host, s.smtp_port, s.email_from)
