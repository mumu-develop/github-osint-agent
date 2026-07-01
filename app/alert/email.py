"""Email notifier via SMTP."""
import asyncio
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional
from app.log_utils import get_logger

logger = get_logger("email_notifier")


class EmailNotifier:
    """Email alert notifier via SMTP."""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int = 587,
        smtp_user: str = "",
        smtp_password: str = "",
        from_addr: str = "",
        to_addrs: List[str] = None,
        use_tls: bool = True,
    ):
        """Initialize Email notifier.

        Args:
            smtp_host: SMTP server host
            smtp_port: SMTP server port (default 587 for TLS)
            smtp_user: SMTP username
            smtp_password: SMTP password
            from_addr: Sender email address
            to_addrs: Recipient email addresses
            use_tls: Whether to use TLS (STARTTLS)
        """
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.from_addr = from_addr
        self.to_addrs = to_addrs or []
        self.use_tls = use_tls

    async def send(self, title: str, content: str, severity: str = "INFO") -> bool:
        """Send alert via Email.

        Args:
            title: Email subject
            content: Email body
            severity: Severity level (included in subject prefix)

        Returns:
            True if sent successfully
        """
        if not self.to_addrs:
            logger.warning("email_no_recipients")
            return False

        # Add severity prefix to subject
        severity_icons = {
            "CRITICAL": "🔴",
            "HIGH": "🟠",
            "MEDIUM": "🟡",
            "LOW": "🟢",
            "INFO": "ℹ️",
        }
        icon = severity_icons.get(severity, "ℹ️")
        subject = f"{icon} [{severity}] {title}"

        # Build email message
        msg = MIMEMultipart()
        msg["From"] = self.from_addr
        msg["To"] = ", ".join(self.to_addrs)
        msg["Subject"] = subject

        body = MIMEText(content, "plain")
        msg.attach(body)

        try:
            # Run SMTP in thread pool (blocking operation)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._send_email_sync, msg)

            logger.info("email_send_success", subject=subject, recipients=len(self.to_addrs))
            return True
        except Exception as e:
            logger.error("email_send_error", error=str(e))
            return False

    def _send_email_sync(self, msg: MIMEMultipart):
        """Send email synchronously (blocking)."""
        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            if self.use_tls:
                server.starttls()
            if self.smtp_user and self.smtp_password:
                server.login(self.smtp_user, self.smtp_password)
            server.sendmail(self.from_addr, self.to_addrs, msg.as_string())

    async def close(self):
        """No cleanup needed for email."""
        pass