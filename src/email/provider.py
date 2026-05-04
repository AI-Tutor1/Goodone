"""Email provider abstraction.

Switches between ``stub``, ``smtp``, ``sendgrid``, ``ses`` based on
``EMAIL_PROVIDER``. Sanction-approval click-through links and period-close
report deliveries hit this in Phase 5+.
"""

from __future__ import annotations

import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Protocol

from src.core.config import get_settings


@dataclass(frozen=True)
class EmailMessageOut:
    to: list[str]
    subject: str
    body_text: str
    body_html: str | None = None
    cc: list[str] = field(default_factory=list)


class EmailProvider(Protocol):
    def send(self, msg: EmailMessageOut) -> None: ...


# ---------------------------------------------------------------------------


class StubEmailProvider:
    """Keeps a list of sent messages in memory; used by tests + dev."""

    def __init__(self) -> None:
        self.sent: list[EmailMessageOut] = []

    def send(self, msg: EmailMessageOut) -> None:
        self.sent.append(msg)


class SmtpEmailProvider:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        use_tls: bool,
        from_address: str,
        from_name: str,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._use_tls = use_tls
        self._from_address = from_address
        self._from_name = from_name

    def send(self, msg: EmailMessageOut) -> None:
        em = EmailMessage()
        em["From"] = f"{self._from_name} <{self._from_address}>"
        em["To"] = ", ".join(msg.to)
        if msg.cc:
            em["Cc"] = ", ".join(msg.cc)
        em["Subject"] = msg.subject
        em.set_content(msg.body_text)
        if msg.body_html:
            em.add_alternative(msg.body_html, subtype="html")
        with smtplib.SMTP(self._host, self._port) as smtp:
            if self._use_tls:
                smtp.starttls()
            if self._username:
                smtp.login(self._username, self._password)
            smtp.send_message(em)


# ---------------------------------------------------------------------------


_active: EmailProvider | None = None


def get_email_provider() -> EmailProvider:
    global _active
    if _active is not None:
        return _active
    s = get_settings()
    name = getattr(s, "email_provider", "stub")
    if name == "stub":
        _active = StubEmailProvider()
    elif name == "smtp":
        _active = SmtpEmailProvider(
            host=getattr(s, "smtp_host", ""),
            port=int(getattr(s, "smtp_port", 587)),
            username=getattr(s, "smtp_username", ""),
            password=getattr(s, "smtp_password", ""),
            use_tls=bool(getattr(s, "smtp_use_tls", True)),
            from_address=getattr(s, "email_from_address", ""),
            from_name=getattr(s, "email_from_name", "Tuitional Finance"),
        )
    else:
        # Fallback for sendgrid/ses (Phase 6 implements)
        _active = StubEmailProvider()
    return _active


def reset_provider_for_tests() -> None:
    global _active
    _active = None
