import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from app.core.config import Settings
from app.schemas.outreach import OutboxMessage


@dataclass
class OutreachSendResult:
    provider: str
    metadata: dict[str, str | int | bool | None]


class OutreachProvider:
    name = "base"

    async def send(self, message: OutboxMessage) -> OutreachSendResult:
        raise NotImplementedError


class SmtpOutreachProvider(OutreachProvider):
    name = "smtp"

    def __init__(self, settings: Settings):
        self.settings = settings

    async def send(self, message: OutboxMessage) -> OutreachSendResult:
        if not self.settings.smtp_send_enabled or not self.settings.smtp_host:
            raise RuntimeError("SMTP provider is not configured or smtp_send_enabled is false.")
        if not message.to:
            raise RuntimeError("Message has no recipient.")

        email = EmailMessage()
        email["From"] = self.settings.smtp_from_email
        email["To"] = message.to
        email["Subject"] = message.subject or "FUDI outreach"
        email.set_content(message.body)

        with smtplib.SMTP(
            self.settings.smtp_host,
            self.settings.smtp_port,
            timeout=self.settings.smtp_timeout_seconds,
        ) as smtp:
            if self.settings.smtp_use_tls:
                smtp.starttls()
            if self.settings.smtp_username and self.settings.smtp_password:
                smtp.login(self.settings.smtp_username, self.settings.smtp_password.get_secret_value())
            response = smtp.send_message(email)

        return OutreachSendResult(
            provider=self.name,
            metadata={
                "smtpHost": self.settings.smtp_host,
                "smtpPort": self.settings.smtp_port,
                "accepted": not bool(response),
            },
        )
