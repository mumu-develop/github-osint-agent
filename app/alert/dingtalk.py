"""钉钉 Webhook 预警推送。"""

import os
import json
import hashlib
import base64
import time
import hmac
import aiohttp
from typing import Dict, Any, Optional, List
from datetime import datetime
from app.log_utils import get_logger
from app.models import Finding

logger = get_logger("dingtalk")

# 严重程度图标映射
SEVERITY_ICONS = {
    "CRITICAL": "🔴",
    "HIGH": "🟠",
    "MEDIUM": "🟡",
    "LOW": "🟢",
    "INFO": "🔵"
}

# 发现类型图标映射
FINDING_TYPE_ICONS = {
    "CVE": "🛡️",
    "SECRET": "🔑",
    "LICENSE": "⚖️",
    "COMMUNITY": "👥",
    "TREND": "📈",
    "SUPPLY_CHAIN": "🔗"
}


class DingTalkNotifier:
    """钉钉机器人 Webhook 推送。"""

    def __init__(self, webhook_url: str = None, secret: str = None):
        self.webhook_url = webhook_url or os.getenv("DINGTALK_WEBHOOK")
        self.secret = secret or os.getenv("DINGTALK_SECRET")
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

    def _sign_url(self) -> str:
        """生成签名 URL。"""
        if not self.secret:
            return self.webhook_url

        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{self.secret}"
        hmac_code = hmac.new(
            self.secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256
        ).digest()
        sign = base64.b64encode(hmac_code).decode("utf-8")

        return f"{self.webhook_url}&timestamp={timestamp}&sign={sign}"

    async def send_text(self, content: str, at_all: bool = False) -> bool:
        """发送文本消息。"""
        if not self.webhook_url:
            logger.warning("dingtalk_webhook_not_configured")
            return False

        payload = {
            "msgtype": "text",
            "text": {"content": content},
            "at": {"isAtAll": at_all}
        }

        return await self._send(payload)

    async def send_markdown(self, title: str, content: str, at_all: bool = False) -> bool:
        """发送 Markdown 消息。"""
        if not self.webhook_url:
            logger.warning("dingtalk_webhook_not_configured")
            return False

        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": content
            },
            "at": {"isAtAll": at_all}
        }

        return await self._send(payload)

    async def send_finding_alert(self, finding: Finding, base_url: str = None) -> bool:
        """发送单个发现预警 - 优化版格式，包含详细修复建议。

        Args:
            finding: 发现对象
            base_url: 前端基础 URL，用于生成跳转链接
        """
        sev_icon = SEVERITY_ICONS.get(finding.severity, "⚪")
        type_icon = FINDING_TYPE_ICONS.get(finding.finding_type, "🔍")
        detail = finding.detail or {}

        # 生成仓库链接
        repo_url = f"https://github.com/{finding.repo_full_name}"

        # 生成前端详情链接（如果有）
        detail_url = ""
        if base_url and finding.scan_task_id:
            detail_url = f"[查看详情]({base_url}/scan/{finding.scan_task_id})"

        title = f"{sev_icon} 安全预警 - {finding.severity}"

        # 构建美观的消息内容
        content = f"""## {sev_icon} {finding.severity} 级别安全发现

{type_icon} **类型**: {finding.finding_type}

📦 **仓库**: [{finding.repo_full_name}]({repo_url})

"""

        # 根据 finding_type 添加特定信息
        if finding.finding_type == "CVE":
            # CVE 类型：展示包名、版本、修复建议
            package = detail.get("package", "未知")
            version = detail.get("version", "未知")
            cve_id = detail.get("cve_id", finding.title)
            fixed_version = detail.get("fixed_version")
            file_name = detail.get("file", "未知文件")

            content += f"""📌 **问题**: {cve_id}

📦 **依赖包**: `{package}@{version}`

📁 **文件**: {file_name}

"""

            # 添加问题摘要
            if detail.get("summary"):
                summary = detail["summary"][:150]
                if len(detail["summary"]) > 150:
                    summary += "..."
                content += f"📝 **摘要**: {summary}\n\n"

            # 添加修复建议（关键信息）
            if fixed_version:
                content += f"🔧 **修复建议**: 升级至 `{package}@{fixed_version}`\n\n"
            else:
                content += f"🔧 **修复建议**: 请查阅官方文档获取修复方案\n\n"

            # 添加相关链接
            references = detail.get("references", [])
            if references:
                ref_links = [f"[链接{i+1}]({r})" for i, r in enumerate(references[:3])]
                content += f"🔗 **参考**: {' | '.join(ref_links)}\n\n"

        elif finding.finding_type == "SECRET":
            # SECRET 类型：展示敏感信息类型和位置
            secret_type = detail.get("secret_type", "未知类型")
            file_path = detail.get("file_path", "未知位置")

            content += f"""📌 **问题**: {finding.title}

🔑 **类型**: {secret_type}

📁 **位置**: {file_path}

"""

        else:
            # 其他类型：通用展示
            content += f"""📌 **问题**: {finding.title}

"""
            if finding.description:
                desc = finding.description[:200]
                if len(finding.description) > 200:
                    desc += "..."
                content += f"📝 **描述**: {desc}\n\n"

        # 添加时间
        time_str = finding.created_at.strftime('%Y-%m-%d %H:%M') if finding.created_at else datetime.now().strftime('%Y-%m-%d %H:%M')
        content += f"⏰ **发现时间**: {time_str}\n\n"

        # 添加分隔线和行动提示
        content += "---\n\n"
        if detail_url:
            content += f"> {detail_url}  |  请尽快处理\n"
        else:
            content += "> ⚠️ 请尽快处理此安全问题\n"

        return await self.send_markdown(title, content, at_all=finding.severity == "CRITICAL")

    async def send_batch_alert(self, findings: List[Finding], org_name: str = None,
                                scan_task_id: int = None, base_url: str = None) -> bool:
        """批量发送预警 - 优化版汇总格式，包含详细修复建议。

        Args:
            findings: 发现列表
            org_name: 组织名称
            scan_task_id: 扫描任务 ID
            base_url: 前端基础 URL
        """
        if not findings:
            return True

        if not self.webhook_url:
            logger.warning("dingtalk_webhook_not_configured")
            return False

        # 按严重程度分组统计
        by_severity = {}
        by_type = {}
        for f in findings:
            by_severity.setdefault(f.severity, []).append(f)
            by_type.setdefault(f.finding_type, []).append(f)

        # 统计高危数量
        high_critical_count = len(by_severity.get("CRITICAL", [])) + len(by_severity.get("HIGH", []))

        # 标题根据严重程度调整
        if high_critical_count > 0:
            title = f"🔴 安全扫描告警 - 发现 {high_critical_count} 个高危问题"
        else:
            title = f"📊 安全扫描结果 - 共发现 {len(findings)} 个问题"

        # 构建消息内容
        content_lines = []

        # 头部：总览
        if org_name:
            content_lines.append(f"## 🔍 {org_name} 扫描结果\n\n")

        content_lines.append(f"**扫描发现总数**: {len(findings)} 个\n\n")
        content_lines.append(f"**高危问题**: {high_critical_count} 个 {'⚠️ 需紧急处理' if high_critical_count > 0 else ''}\n\n")

        # 严重程度分布（用表格样式的列表）
        content_lines.append("### 📊 按严重程度分布\n\n")
        severity_order = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
        for sev in severity_order:
            count = len(by_severity.get(sev, []))
            if count > 0:
                icon = SEVERITY_ICONS.get(sev, "⚪")
                content_lines.append(f"- {icon} **{sev}**: {count} 个\n")

        # 问题类型分布
        content_lines.append("\n### 📋 按问题类型分布\n\n")
        for finding_type, items in by_type.items():
            icon = FINDING_TYPE_ICONS.get(finding_type, "🔍")
            # 统计该类型的高危数量
            hc_in_type = len([f for f in items if f.severity in ["CRITICAL", "HIGH"]])
            content_lines.append(f"- {icon} **{finding_type}**: {len(items)} 个 ({hc_in_type} 高危)\n")

        # 高危问题详细列表（包含修复建议）
        high_critical = by_severity.get("CRITICAL", []) + by_severity.get("HIGH", [])
        if high_critical:
            content_lines.append(f"\n### 🔥 高危问题详情 (共 {len(high_critical)} 个)\n\n")
            content_lines.append("> ⚠️ 以下问题需要优先处理:\n\n")

            for i, f in enumerate(high_critical[:10], 1):
                icon = SEVERITY_ICONS.get(f.severity, "⚪")
                type_icon = FINDING_TYPE_ICONS.get(f.finding_type, "🔍")
                repo_url = f"https://github.com/{f.repo_full_name}"
                detail = f.detail or {}

                content_lines.append(f"**{i}.** {icon} [{f.repo_full_name}]({repo_url})\n")

                # 根据类型展示不同信息
                if f.finding_type == "CVE":
                    package = detail.get("package", "未知")
                    version = detail.get("version", "未知")
                    cve_id = detail.get("cve_id", f.title)
                    fixed_version = detail.get("fixed_version")

                    content_lines.append(f"   📌 `{cve_id}`: `{package}@{version}`\n")

                    # 显示修复建议（关键信息）
                    if fixed_version:
                        content_lines.append(f"   🔧 **修复**: 升级至 `{package}@{fixed_version}`\n")

                elif f.finding_type == "SECRET":
                    secret_type = detail.get("secret_type", "未知")
                    content_lines.append(f"   🔑 敏感信息泄露: {secret_type}\n")

                else:
                    # 截取标题
                    title_short = f.title[:50]
                    if len(f.title) > 50:
                        title_short += "..."
                    content_lines.append(f"   {type_icon} {title_short}\n")

                content_lines.append("\n")

            if len(high_critical) > 10:
                content_lines.append(f"_...还有 {len(high_critical) - 10} 个高危问题未列出_\n\n")

        # 底部：链接和时间
        content_lines.append("---\n\n")
        if base_url and scan_task_id:
            content_lines.append(f"🔗 [查看完整报告]({base_url}/scan/{scan_task_id})\n\n")
        content_lines.append(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

        return await self.send_markdown(title, "".join(content_lines), at_all=high_critical_count > 5)

    async def send_scan_summary(self, org_name: str, total_repos: int, total_findings: int,
                                 high_severity: int, scan_task_id: int = None,
                                 base_url: str = None) -> bool:
        """发送扫描完成摘要 - 简洁版。

        Args:
            org_name: 组织名称
            total_repos: 扫描仓库数
            total_findings: 发现问题总数
            high_severity: 高危问题数
            scan_task_id: 扫描任务 ID
            base_url: 前端基础 URL
        """
        # 标题根据结果调整
        if high_severity > 0:
            title = f"⚠️ 扫描完成 - 发现 {high_severity} 个高危问题"
        elif total_findings > 0:
            title = f"✅ 扫描完成 - 发现 {total_findings} 个问题"
        else:
            title = f"✅ 扫描完成 - 未发现问题"

        content = f"""## 🔍 {org_name} 扫描报告

📦 **扫描仓库**: {total_repos} 个

📊 **发现问题**: {total_findings} 个

{'🔴 **高危问题**: ' + str(high_severity) + ' 个 ⚠️' if high_severity > 0 else '✅ 无高危问题'}

---

"""

        if base_url and scan_task_id:
            content += f"🔗 [查看详细报告]({base_url}/scan/{scan_task_id})\n\n"

        content += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"

        return await self.send_markdown(title, content)

    async def send_weekly_report(self, findings: List[Finding], week_start: datetime,
                                  week_end: datetime, base_url: str = None) -> bool:
        """发送每周安全汇总报告。

        Args:
            findings: 本周发现列表
            week_start: 周开始时间
            week_end: 周结束时间
            base_url: 前端基础 URL
        """
        if not findings:
            title = "📊 每周安全汇总 - 本周无新发现问题"
            content = f"""## 📊 每周安全汇总

**统计周期**: {week_start.strftime('%Y-%m-%d')} ~ {week_end.strftime('%Y-%m-%d')}

✅ 本周未发现新的安全问题，继续保持！

---

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}
"""
            return await self.send_markdown(title, content)

        # 按严重程度分组
        by_severity = {}
        new_high_critical = 0
        for f in findings:
            by_severity.setdefault(f.severity, []).append(f)
            if f.severity in ["CRITICAL", "HIGH"]:
                new_high_critical += 1

        title = f"📊 每周安全汇总 - {len(findings)} 个问题 ({new_high_critical} 高危)"

        content_lines = [
            f"## 📊 每周安全汇总报告\n\n",
            f"**统计周期**: {week_start.strftime('%Y-%m-%d')} ~ {week_end.strftime('%Y-%m-%d')}\n\n",
            f"**新增发现**: {len(findings)} 个\n\n",
            f"**高危问题**: {new_high_critical} 个\n\n",
            "---\n\n",
            "### 📊 严重程度分布\n\n"
        ]

        severity_order = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
        for sev in severity_order:
            count = len(by_severity.get(sev, []))
            if count > 0:
                icon = SEVERITY_ICONS.get(sev, "⚪")
                content_lines.append(f"- {icon} **{sev}**: {count} 个\n")

        # 本周新增高危
        high_critical = by_severity.get("CRITICAL", []) + by_severity.get("HIGH", [])
        if high_critical:
            content_lines.append(f"\n### 🔥 本周新增高危问题\n\n")
            for i, f in enumerate(high_critical[:5], 1):
                icon = SEVERITY_ICONS.get(f.severity, "⚪")
                repo_url = f"https://github.com/{f.repo_full_name}"
                content_lines.append(f"**{i}.** {icon} [{f.repo_full_name}]({repo_url}) - {f.title[:40]}...\n\n")

            if len(high_critical) > 5:
                content_lines.append(f"_...还有 {len(high_critical) - 5} 个_\n\n")

        content_lines.append("---\n\n")
        if base_url:
            content_lines.append(f"🔗 [查看历史报告]({base_url}/reports)\n\n")
        content_lines.append(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

        return await self.send_markdown(title, "".join(content_lines))

    async def _send(self, payload: Dict) -> bool:
        """发送请求到钉钉。"""
        try:
            session = await self._get_session()
            url = self._sign_url()

            async with session.post(url, json=payload) as resp:
                result = await resp.json()

                if result.get("errcode") == 0:
                    logger.info("dingtalk_send_success", msgtype=payload.get("msgtype"))
                    return True
                else:
                    logger.warning("dingtalk_send_failed", errcode=result.get("errcode"), errmsg=result.get("errmsg"))
                    return False

        except aiohttp.ClientError as e:
            logger.error("dingtalk_network_error", error=str(e))
            return False
        except Exception as e:
            logger.error("dingtalk_send_error", error=str(e))
            return False