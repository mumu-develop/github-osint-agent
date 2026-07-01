"""飞书 Webhook 预警推送。"""

import os
import json
import aiohttp
from typing import Dict, Any, Optional
from app.log_utils import get_logger
from app.models import Finding

logger = get_logger("feishu")


class FeishuNotifier:
    """飞书机器人 Webhook 推送。"""

    def __init__(self, webhook_url: str = None):
        self.webhook_url = webhook_url or os.getenv("FEISHU_WEBHOOK")
        self._session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取 aiohttp session。"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        return self._session

    async def close(self):
        """关闭 session。"""
        if self._session and not self._session.closed:
            await self._session.close()

    async def send_text(self, content: str) -> bool:
        """发送文本消息。"""
        if not self.webhook_url:
            logger.warning("feishu_webhook_not_configured")
            return False

        payload = {
            "msg_type": "text",
            "content": {"text": content}
        }

        return await self._send(payload)

    async def send_post(self, title: str, content: list) -> bool:
        """发送富文本消息（Post 格式）。"""
        if not self.webhook_url:
            logger.warning("feishu_webhook_not_configured")
            return False

        payload = {
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {
                        "title": title,
                        "content": content
                    }
                }
            }
        }

        return await self._send(payload)

    async def send_card(self, title: str, content: str, color: str = "red") -> bool:
        """发送卡片消息。"""
        if not self.webhook_url:
            logger.warning("feishu_webhook_not_configured")
            return False

        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": title},
                    "template": color
                },
                "elements": [
                    {"tag": "markdown", "content": content}
                ]
            }
        }

        return await self._send(payload)

    async def send_finding_alert(self, finding: Finding) -> bool:
        """发送发现预警。"""
        severity_colors = {
            "CRITICAL": "red",
            "HIGH": "orange",
            "MEDIUM": "yellow",
            "LOW": "blue",
            "INFO": "grey"
        }

        color = severity_colors.get(finding.severity, "grey")

        title = f"OSINT 安全预警 - {finding.severity}"
        content = f"""**仓库**: {finding.repo_full_name}
**类型**: {finding.finding_type}
**标题**: {finding.title}
**描述**: {finding.description or '无详细描述'}
**时间**: {finding.created_at.strftime('%Y-%m-%d %H:%M') if finding.created_at else '未知'}

请尽快处理此安全问题"""

        return await self.send_card(title, content, color)

    async def send_batch_alert(self, findings: list, summary: str = None) -> bool:
        """批量发送预警（汇总形式）。"""
        if not findings:
            return True

        if not self.webhook_url:
            logger.warning("feishu_webhook_not_configured")
            return False

        # 按严重程度分组
        by_severity = {}
        for f in findings:
            by_severity.setdefault(f.severity, []).append(f)

        title = "OSINT 扫描结果汇总"
        content_lines = [[{"tag": "text", "text": f"扫描发现总数: {len(findings)}\n\n"}]]

        severity_order = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]

        for sev in severity_order:
            count = len(by_severity.get(sev, []))
            if count > 0:
                content_lines.append([{"tag": "text", "text": f"{sev}: {count} 个\n"}])

        # 列出高危问题
        high_critical = by_severity.get("CRITICAL", []) + by_severity.get("HIGH", [])
        if high_critical:
            content_lines.append([{"tag": "text", "text": "\n需紧急处理:\n"}])
            for f in high_critical[:5]:
                content_lines.append([{"tag": "text", "text": f"- {f.repo_full_name}: {f.title}\n"}])

        if summary:
            content_lines.append([{"tag": "text", "text": f"\n{summary}"}])

        return await self.send_post(title, content_lines)

    async def _send(self, payload: Dict) -> bool:
        """发送请求到飞书。"""
        try:
            session = await self._get_session()

            async with session.post(self.webhook_url, json=payload) as resp:
                result = await resp.json()

                if result.get("StatusCode") == 0 or result.get("code") == 0:
                    logger.info("feishu_send_success", msgtype=payload.get("msg_type"))
                    return True
                else:
                    logger.warning("feishu_send_failed", code=result.get("code"), msg=result.get("msg"))
                    return False

        except aiohttp.ClientError as e:
            logger.error("feishu_network_error", error=str(e))
            return False
        except Exception as e:
            logger.error("feishu_send_error", error=str(e))
            return False