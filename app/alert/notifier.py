"""统一预警推送接口。"""

import os
import asyncio
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from app.log_utils import get_logger
from app.models import Finding
from app.alert.dingtalk import DingTalkNotifier
from app.alert.feishu import FeishuNotifier
from app.alert.slack import SlackNotifier
from app.alert.discord import DiscordNotifier
from app.alert.email import EmailNotifier
from app.database import FindingDAO

logger = get_logger("notifier")


class AlertNotifier:
    """统一预警推送管理器 - 支持多种通知渠道。"""

    def __init__(self):
        """初始化告警通知器。"""
        # 中国企业渠道
        dingtalk_webhook = os.getenv("DINGTALK_WEBHOOK")
        dingtalk_secret = os.getenv("DINGTALK_SECRET")
        feishu_webhook = os.getenv("FEISHU_WEBHOOK")

        # 国际化渠道
        slack_webhook = os.getenv("SLACK_WEBHOOK")
        slack_channel = os.getenv("SLACK_CHANNEL")
        discord_webhook = os.getenv("DISCORD_WEBHOOK")

        # Email渠道
        smtp_host = os.getenv("SMTP_HOST")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USER", "")
        smtp_password = os.getenv("SMTP_PASSWORD", "")
        email_from = os.getenv("EMAIL_FROM", "")
        email_to = os.getenv("EMAIL_TO", "").split(",") if os.getenv("EMAIL_TO") else []

        # 初始化各渠道通知器
        self.dingtalk = DingTalkNotifier(webhook_url=dingtalk_webhook, secret=dingtalk_secret) if dingtalk_webhook else None
        self.feishu = FeishuNotifier(webhook_url=feishu_webhook) if feishu_webhook else None
        self.slack = SlackNotifier(webhook=slack_webhook, channel=slack_channel) if slack_webhook else None
        self.discord = DiscordNotifier(webhook=discord_webhook) if discord_webhook else None
        self.email = EmailNotifier(
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_user=smtp_user,
            smtp_password=smtp_password,
            from_addr=email_from,
            to_addrs=email_to,
        ) if smtp_host else None

        self._pending_weekly: List[Finding] = []

    async def close(self):
        """关闭资源。"""
        for notifier in [self.dingtalk, self.feishu, self.slack, self.discord, self.email]:
            if notifier:
                await notifier.close()

    async def send_alert(self, finding: Finding, org_name: str = None) -> Dict[str, bool]:
        """发送单个发现预警 - 支持所有配置的渠道。"""
        results = {}

        severity = finding.severity
        title, content = self._format_alert_content(finding)

        if severity in ["CRITICAL", "HIGH"]:
            # 立即推送所有已配置的渠道
            if self.dingtalk:
                results["dingtalk"] = await self.dingtalk.send_finding_alert(finding)
            if self.feishu:
                results["feishu"] = await self.feishu.send_finding_alert(finding)
            if self.slack:
                results["slack"] = await self.slack.send(title, content, severity)
            if self.discord:
                results["discord"] = await self.discord.send(title, content, severity)
            if self.email:
                results["email"] = await self.email.send(title, content, severity)

            logger.info("alert_sent_immediate",
                        finding_id=finding.id,
                        severity=severity,
                        channels=list(results.keys()))

        else:
            # 加入周报汇总
            self._pending_weekly.append(finding)
            logger.info("alert_added_to_weekly", finding_id=finding.id, severity=severity)

        return results

    def _format_alert_content(self, finding: Finding) -> tuple:
        """格式化告警内容。"""
        severity_icons = {
            "CRITICAL": "🔴",
            "HIGH": "🟠",
            "MEDIUM": "🟡",
            "LOW": "🟢",
            "INFO": "ℹ️",
        }
        icon = severity_icons.get(finding.severity, "ℹ️")
        title = f"{icon} [{finding.severity}] {finding.title}"
        content = f"""{finding.description}

详情: {finding.detail or '无'}
状态: {finding.status}
时间: {finding.created_at.strftime('%Y-%m-%d %H:%M')}"""
        return title, content

    async def send_batch_alerts(self, findings: List[Finding], org_name: str = None) -> Dict[str, bool]:
        """批量发送预警。"""
        if not findings:
            return {"dingtalk": True, "feishu": True}

        # 分离高危和低危
        high_critical = [f for f in findings if f.severity in ["CRITICAL", "HIGH"]]
        low_medium = [f for f in findings if f.severity in ["MEDIUM", "LOW", "INFO"]]

        results = {}

        # 高危立即推送
        if high_critical:
            results["dingtalk"] = await self.dingtalk.send_batch_alert(high_critical, f"共发现 {len(findings)} 个问题")
            results["feishu"] = await self.feishu.send_batch_alert(high_critical, f"共发现 {len(findings)} 个问题")

        # 低危加入汇总
        self._pending_weekly.extend(low_medium)

        logger.info("batch_alerts_sent",
                    total=len(findings),
                    high_critical=len(high_critical),
                    low_medium=len(low_medium))

        return results

    async def send_scan_summary(self, scan_result: Dict, org_name: str) -> bool:
        """发送扫描完成摘要。"""
        title = "OSINT 扫描完成通知"
        repos_scanned = scan_result.get("repos_scanned", 0)
        total_findings = scan_result.get("total_findings", 0)
        high_severity = scan_result.get("high_severity_count", 0)

        content = f"""扫描任务已完成

**组织**: {org_name}
**扫描仓库数**: {repos_scanned}
**发现问题数**: {total_findings}
**高危问题数**: {high_severity}

---
时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}"""

        # 只发送到钉钉
        return await self.dingtalk.send_markdown(title, content)

    async def send_weekly_report(self) -> bool:
        """发送周报汇总。"""
        if not self._pending_weekly:
            logger.info("weekly_report_empty")
            return True

        # 获取过去一周的所有发现（包括已入库的）
        week_ago = datetime.now() - timedelta(days=7)
        recent_findings = await FindingDAO.query(created_after=week_ago)

        # 合并待发送的
        all_findings = recent_findings + self._pending_weekly

        title = "OSINT 每周安全汇总"
        summary = f"本周共发现 {len(all_findings)} 个安全问题"

        dingtalk_result = await self.dingtalk.send_batch_alert(all_findings, summary)
        feishu_result = await self.feishu.send_batch_alert(all_findings, summary)

        # 清空待发送队列
        self._pending_weekly.clear()

        logger.info("weekly_report_sent", total=len(all_findings))

        return dingtalk_result and feishu_result


# 全局实例
_notifier: AlertNotifier = None


def get_notifier() -> AlertNotifier:
    """获取预警通知器实例。"""
    global _notifier
    if _notifier is None:
        _notifier = AlertNotifier()
    return _notifier