"""Discord webhook notifier."""
import aiohttp
from typing import Optional
from app.log_utils import get_logger

logger = get_logger("discord_notifier")


class DiscordNotifier:
    """Discord webhook alert notifier."""

    def __init__(self, webhook: str):
        """Initialize Discord notifier.

        Args:
            webhook: Discord webhook URL (https://discord.com/api/webhooks/...)
        """
        self.webhook = webhook
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
        """Send alert to Discord.

        Args:
            title: Alert title
            content: Alert content
            severity: Severity level (CRITICAL, HIGH, MEDIUM, LOW, INFO)

        Returns:
            True if sent successfully
        """
        session = await self._get_session()

        # Color mapping by severity (Discord uses decimal colors)
        colors = {
            "CRITICAL": 16711680,   # Red (FF0000 in decimal)
            "HIGH": 16744192,       # Orange (FF6B00 in decimal)
            "MEDIUM": 16763904,     # Yellow (FFCC00 in decimal)
            "LOW": 3578143,         # Green (36A64F in decimal)
            "INFO": 8421504,        # Gray (808080 in decimal)
        }

        # Build Discord message payload
        payload = {
            "embeds": [
                {
                    "title": title,
                    "description": content,
                    "color": colors.get(severity, 8421504),
                }
            ]
        }

        try:
            async with session.post(self.webhook, json=payload) as resp:
                if resp.status == 204:
                    logger.info("discord_send_success", title=title)
                    return True
                logger.warning("discord_send_failed", status=resp.status)
        except aiohttp.ClientError as e:
            logger.error("discord_send_error", error=str(e))

        return False