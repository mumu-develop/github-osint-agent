"""Slack webhook notifier."""
import aiohttp
from typing import Optional
from app.log_utils import get_logger

logger = get_logger("slack_notifier")


class SlackNotifier:
    """Slack webhook alert notifier."""

    def __init__(self, webhook: str, channel: Optional[str] = None):
        """Initialize Slack notifier.

        Args:
            webhook: Slack webhook URL (https://hooks.slack.com/services/...)
            channel: Optional channel override (e.g., "#alerts")
        """
        self.webhook = webhook
        self.channel = channel
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """Close session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def send(self, title: str, content: str, severity: str = "INFO") -> bool:
        """Send alert to Slack.

        Args:
            title: Alert title
            content: Alert content
            severity: Severity level (CRITICAL, HIGH, MEDIUM, LOW, INFO)

        Returns:
            True if sent successfully
        """
        session = await self._get_session()

        # Color mapping by severity
        colors = {
            "CRITICAL": "#FF0000",  # Red
            "HIGH": "#FF6B00",      # Orange
            "MEDIUM": "#FFCC00",    # Yellow
            "LOW": "#36A64F",       # Green
            "INFO": "#808080",      # Gray
        }

        # Build Slack message payload
        payload = {
            "attachments": [
                {
                    "color": colors.get(severity, "#808080"),
                    "title": title,
                    "text": content,
                    "mrkdwn_in": ["text"],
                }
            ]
        }

        if self.channel:
            payload["channel"] = self.channel

        try:
            async with session.post(self.webhook, json=payload) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    if text == "ok":
                        logger.info("slack_send_success", title=title)
                        return True
                logger.warning("slack_send_failed", status=resp.status)
        except aiohttp.ClientError as e:
            logger.error("slack_send_error", error=str(e))

        return False