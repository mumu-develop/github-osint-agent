"""LLM 告警汇总分析模块 - 将扫描发现汇总成精简报告后推送钉钉。

使用项目统一的 llm_config 模块创建模型。
"""

import os
import asyncio
from typing import Dict, List, Optional
from datetime import datetime
from app.log_utils import get_logger
from app.models import Finding
from app.llm_config import create_chat_model, get_api_config

logger = get_logger("alert_summarizer")


class AlertSummarizer:
    """LLM 告警汇总分析器。

    功能：
    1. 按 severity + finding_type 分组 findings
    2. 调用 LLM 生成精简汇总报告
    3. 返回 Markdown 格式内容（适合钉钉）
    """

    def __init__(self):
        # 使用项目统一的 LLM 配置
        self.llm_enabled = self._check_llm_available()
        if self.llm_enabled:
            try:
                # 使用轻量模型进行汇总（qwen-turbo 或默认模型）
                model_name = os.getenv("SUMMARY_MODEL", "openai:qwen-turbo")
                self.model = create_chat_model(model_name, temperature=0.3, max_tokens=800)
                logger.info("summarizer_model_created", model=model_name)
            except Exception as e:
                logger.warning("summarizer_model_failed", error=str(e))
                self.llm_enabled = False

    def _check_llm_available(self) -> bool:
        """检查 LLM 是否可用。"""
        api_base, api_key = get_api_config()
        return bool(api_key)

    async def summarize(self, findings: List[Finding], org_name: str) -> str:
        """汇总 findings 并生成精简报告。

        Args:
            findings: 需要推送的发现列表
            org_name: 组织名称

        Returns:
            Markdown 格式的汇总报告
        """
        if not findings:
            return ""

        if not self.llm_enabled:
            # 无 LLM 时，使用模板格式
            return self._format_without_llm(findings, org_name)

        # 按 severity + finding_type 分组
        grouped = self._group_findings(findings)

        # 构建 Prompt
        prompt = self._build_prompt(grouped, org_name, len(findings))

        # 调用 LLM（使用 asyncio.to_thread 因为 langchain 是同步的）
        try:
            response = await asyncio.to_thread(
                lambda: self.model.invoke(prompt)
            )
            return response.content
        except Exception as e:
            logger.warning("llm_summarize_error", error=str(e))
            # 降级到模板格式
            return self._format_without_llm(findings, org_name)

    def _group_findings(self, findings: List[Finding]) -> Dict[str, Dict]:
        """按 severity + finding_type 分组 findings。"""
        grouped = {}

        for f in findings:
            key = f"{f.severity}|{f.finding_type}"
            if key not in grouped:
                grouped[key] = {
                    "severity": f.severity,
                    "finding_type": f.finding_type,
                    "count": 0,
                    "repos": set(),
                    "examples": []
                }

            grouped[key]["count"] += 1
            grouped[key]["repos"].add(f.repo_full_name)

            # 收集示例（最多 3 个）
            if len(grouped[key]["examples"]) < 3:
                example = {
                    "repo": f.repo_full_name,
                    "title": f.title,
                    "detail": f.detail or {}
                }
                grouped[key]["examples"].append(example)

        return grouped

    def _build_prompt(self, grouped: Dict, org_name: str, total_count: int) -> str:
        """构建 LLM Prompt。"""
        # 严重程度图标
        severity_icons = {
            "CRITICAL": "🔴",
            "HIGH": "🟠",
            "MEDIUM": "🟡",
            "LOW": "🟢",
            "INFO": "🔵"
        }

        # 类型名称
        type_names = {
            "CVE": "CVE 漏洞",
            "SECRET": "敏感信息泄露",
            "LICENSE": "许可证合规",
            "COMMUNITY": "社区健康",
            "TREND": "趋势分析",
            "SUPPLY_CHAIN": "供应链风险",
            "AGENT_ANALYSIS": "AI 分析"
        }

        prompt = f"""你是一个安全运营专家，请根据以下扫描发现生成一份精简的告警报告。

## 输入数据

**组织**: {org_name}
**发现问题总数**: {total_count}
**扫描时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}

### 问题分类汇总

"""

        # 添加分组数据
        for key, data in sorted(grouped.items(), key=lambda x: (
            ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"].index(x[1]["severity"]),
            x[1]["count"]
        ), reverse=True):
            icon = severity_icons.get(data["severity"], "⚪")
            type_name = type_names.get(data["finding_type"], data["finding_type"])
            repos_str = ", ".join(list(data["repos"])[:5])

            prompt += f"""
#### {icon} {data["severity"]} - {type_name} ({data["count"]} 个)

**涉及仓库**: {repos_str}

**示例**:
"""
            for ex in data["examples"]:
                detail_info = ""
                if data["finding_type"] == "CVE":
                    pkg = ex["detail"].get("package", "未知")
                    ver = ex["detail"].get("version", "未知")
                    fix = ex["detail"].get("fixed_version", "未知")
                    detail_info = f"包: {pkg}@{ver} → 建议升级至 {fix}"
                elif data["finding_type"] == "SECRET":
                    detail_info = ex["detail"].get("secret_type", ex["title"][:50])
                else:
                    detail_info = ex["title"][:80]

                prompt += f"- `{ex['repo']}`: {detail_info}\n"

        prompt += """

## 输出要求

请生成一份适合钉钉推送的 Markdown 格式报告，要求：

1. **格式精简**：控制在 500 字以内，避免冗余
2. **结构清晰**：按严重程度排序，突出问题等级
3. **优先级建议**：明确指出哪些问题需要立即处理
4. **修复指引**：针对主要问题类型给出简洁的修复建议

输出格式示例：

## 🚨 {org_name} 安全告警

> 发现 **{total_count}** 个问题，需立即关注

### 🔴 严重问题（需立即处理）
- CVE 漏洞 **X** 个：涉及 log4j、protobuf 等高危依赖，建议升级至安全版本
- 敏感信息泄露 **Y** 个：发现 API Key 泄露，请立即撤销并更新

### 🟠 高危问题（本周处理）
- 许可证合规 **Z** 个：发现 GPL 许可证依赖，商业项目需评估

### 💡 处理建议
1. 立即升级高危依赖版本
2. 撤销并轮换泄露的凭证
3. 推送钉钉后请及时跟进处理

---
*报告时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}*
"""

        return prompt

    def _format_without_llm(self, findings: List[Finding], org_name: str) -> str:
        """无 LLM 时使用模板格式。"""
        severity_icons = {
            "CRITICAL": "🔴",
            "HIGH": "🟠",
            "MEDIUM": "🟡",
            "LOW": "🟢",
            "INFO": "🔵"
        }

        type_names = {
            "CVE": "CVE",
            "SECRET": "敏感信息",
            "LICENSE": "许可证",
            "COMMUNITY": "社区",
            "TREND": "趋势",
            "SUPPLY_CHAIN": "供应链"
        }

        # 统计
        by_severity = {}
        by_type = {}
        for f in findings:
            by_severity[f.severity] = by_severity.get(f.severity, 0) + 1
            by_type[f.finding_type] = by_type.get(f.finding_type, 0) + 1

        # 按严重程度排序
        severity_order = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]

        content = f"""## 🚨 {org_name} 安全告警

> 发现 **{len(findings)}** 个问题需关注

### 问题分布

"""

        for sev in severity_order:
            if sev in by_severity:
                icon = severity_icons.get(sev, "⚪")
                content += f"| {icon} {sev} | {by_severity[sev]} 个 |\n"

        content += "\n### 问题类型\n\n"
        for typ, cnt in sorted(by_type.items(), key=lambda x: x[1], reverse=True):
            type_name = type_names.get(typ, typ)
            content += f"- {type_name}: **{cnt}** 个\n"

        # 高危问题详情（最多 10 条）
        high_critical = [f for f in findings if f.severity in ["CRITICAL", "HIGH"]][:10]
        if high_critical:
            content += "\n### 🔴 高危问题详情\n\n"
            for f in high_critical:
                icon = severity_icons.get(f.severity, "⚪")
                content += f"{icon} `{f.repo_full_name}` - {f.title[:50]}\n"

        content += f"\n---\n*扫描时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}*"

        return content


# 便捷函数
async def summarize_alerts(findings: List[Finding], org_name: str) -> str:
    """汇总告警（便捷函数）。"""
    summarizer = AlertSummarizer()
    return await summarizer.summarize(findings, org_name)