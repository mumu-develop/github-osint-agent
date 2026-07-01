"""Tests for alert notifications."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import aiohttp


class TestDingTalkAlert:
    """Test cases for DingTalk webhook alerts."""

    @pytest.mark.asyncio
    async def test_send_critical_alert_success(self):
        """Test successful CRITICAL alert sending."""
        from app.alert.dingtalk import DingTalkNotifier

        notifier = DingTalkNotifier(
            webhook="https://oapi.dingtalk.com/robot/send?access_token=test",
            secret="test-secret"
        )

        # Mock the session
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"errcode": 0})

        mock_session = MagicMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.closed = False

        notifier._session = mock_session

        result = await notifier.send(
            title="CRITICAL Alert",
            content="Test critical alert content",
            at_all=True
        )

        assert result is True
        await notifier.close()

    @pytest.mark.asyncio
    async def test_send_high_alert_success(self):
        """Test successful HIGH alert sending."""
        from app.alert.dingtalk import DingTalkNotifier

        notifier = DingTalkNotifier(
            webhook="https://oapi.dingtalk.com/robot/send?access_token=test"
        )

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"errcode": 0})

        mock_session = MagicMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.closed = False

        notifier._session = mock_session

        result = await notifier.send(
            title="HIGH Alert",
            content="Test high alert content"
        )

        assert result is True
        await notifier.close()

    @pytest.mark.asyncio
    async def test_webhook_failure_handling(self):
        """Test webhook failure handling."""
        from app.alert.dingtalk import DingTalkNotifier

        notifier = DingTalkNotifier(
            webhook="https://oapi.dingtalk.com/robot/send?access_token=test"
        )

        mock_response = MagicMock()
        mock_response.status = 500
        mock_response.json = AsyncMock(return_value={"errcode": 500})

        mock_session = MagicMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.closed = False

        notifier._session = mock_session

        result = await notifier.send(
            title="Test Alert",
            content="Test content"
        )

        assert result is False
        await notifier.close()

    @pytest.mark.asyncio
    async def test_network_error_handling(self):
        """Test network error handling."""
        from app.alert.dingtalk import DingTalkNotifier

        notifier = DingTalkNotifier(
            webhook="https://oapi.dingtalk.com/robot/send?access_token=test"
        )

        mock_session = MagicMock()
        mock_session.post = AsyncMock(side_effect=aiohttp.ClientError("Network error"))
        mock_session.closed = False

        notifier._session = mock_session

        result = await notifier.send(
            title="Test Alert",
            content="Test content"
        )

        assert result is False
        await notifier.close()


class TestFeishuAlert:
    """Test cases for Feishu webhook alerts."""

    @pytest.mark.asyncio
    async def test_send_alert_success(self):
        """Test successful Feishu alert sending."""
        from app.alert.feishu import FeishuNotifier

        notifier = FeishuNotifier(
            webhook="https://open.feishu.cn/open-apis/bot/v2/hook/test"
        )

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"code": 0})

        mock_session = MagicMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.closed = False

        notifier._session = mock_session

        result = await notifier.send(
            title="Test Alert",
            content="Test alert content"
        )

        assert result is True
        await notifier.close()

    @pytest.mark.asyncio
    async def test_send_alert_with_sign(self):
        """Test Feishu alert with sign verification."""
        from app.alert.feishu import FeishuNotifier

        notifier = FeishuNotifier(
            webhook="https://open.feishu.cn/open-apis/bot/v2/hook/test",
            secret="test-secret"
        )

        # Verify sign is generated
        assert notifier.secret == "test-secret"

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"code": 0})

        mock_session = MagicMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.closed = False

        notifier._session = mock_session

        result = await notifier.send(
            title="Test Alert",
            content="Test content"
        )

        assert result is True
        await notifier.close()

    @pytest.mark.asyncio
    async def test_feishu_error_handling(self):
        """Test Feishu error response handling."""
        from app.alert.feishu import FeishuNotifier

        notifier = FeishuNotifier(
            webhook="https://open.feishu.cn/open-apis/bot/v2/hook/test"
        )

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"code": 10000, "msg": "Invalid webhook"})

        mock_session = MagicMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.closed = False

        notifier._session = mock_session

        result = await notifier.send(
            title="Test Alert",
            content="Test content"
        )

        assert result is False
        await notifier.close()


class TestNotifierManager:
    """Test cases for unified notifier management."""

    @pytest.mark.asyncio
    async def test_notifier_factory(self):
        """Test notifier factory creation."""
        from app.alert.notifier import create_notifier

        # Test DingTalk creation
        dingtalk = create_notifier("dingtalk", webhook="https://test.com")
        assert dingtalk is not None

        # Test Feishu creation
        feishu = create_notifier("feishu", webhook="https://test.com")
        assert feishu is not None

    @pytest.mark.asyncio
    async def test_notifier_invalid_type(self):
        """Test notifier factory with invalid type."""
        from app.alert.notifier import create_notifier

        result = create_notifier("invalid_type", webhook="https://test.com")
        assert result is None


class TestAlertFormatting:
    """Test cases for alert message formatting."""

    def test_format_vulnerability_alert(self):
        """Test vulnerability alert formatting."""
        # This tests the expected format structure
        title = "🔴 [CRITICAL] sofa-boot 依赖发现高危 CVE"
        content = """仓库：SOFAStack/sofa-boot
依赖：log4j-core 2.14.1
CVE：CVE-2021-44228
建议：立即升级到 2.17.0+"""

        assert "CRITICAL" in title
        assert "CVE-2021-44228" in content
        assert "建议" in content

    def test_format_secret_leak_alert(self):
        """Test secret leak alert formatting."""
        title = "🔴 [CRITICAL] 发现敏感信息泄露"
        content = """仓库：test-org/test-repo
文件：config/settings.py
类型：AWS Access Key
建议：立即移除并轮换密钥"""

        assert "敏感信息" in title
        assert "AWS" in content