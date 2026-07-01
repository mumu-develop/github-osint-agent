"""定时任务 Agent 创建模块。

使用 deepagents.create_deep_agent 创建 Agent，复用对话分析的子Agent系统。
与对话分析的区别：
- 无记忆（checkpointer=None, store=None）
- 无用户偏好（不加载 /memories/{user_id}/preferences.md）
- 直接保存报告到数据库（无需询问用户）
"""

import os
from pathlib import Path
from typing import List, Dict, Any

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend

from app.loader import SubAgentLoader
from app.tools import SUBAGENT_TOOLS
from app.tools.unified import (
    scan_org,
    get_org_repos,
    check_cve_repos,
    check_package_cve,
    scan_secrets,
    check_license,
    check_community,
    get_issue_metrics,
    get_pr_metrics,
    get_repo_stats,
    get_star_history,
    get_contributor_activity,
)
from app.tools.report import get_sandbox_report_path
from app.llm_config import get_default_model
from app.backend import OpenSandboxBackend
from app.log_utils import get_logger
from langchain_core.tools import tool

logger = get_logger("scheduler_agent")

# 加载 AGENTS.md 内容
AGENTS_MD_PATH = Path(__file__).parent.parent.parent / "AGENTS.md"
AGENTS_MD_CONTENT = ""
if AGENTS_MD_PATH.exists():
    try:
        AGENTS_MD_CONTENT = AGENTS_MD_PATH.read_text(encoding="utf-8")
        logger.info("agents_md_loaded", path=str(AGENTS_MD_PATH))
    except Exception as e:
        logger.warning("agents_md_load_failed", error=str(e))


# 定时任务专用补充规则
SCHEDULER_APPEND_RULES = """
---

## 定时任务特殊规则

### 与对话分析的区别

| 对话分析 | 定时任务 |
|---------|---------|
| 需要询问用户是否下载报告 | **直接保存报告内容**（返回给调度器存入数据库） |
| 记录用户偏好到 /memories/ | **不记录任何记忆** |
| 多轮对话、状态持久化 | **单次执行、即用即销** |
| 需要等待用户确认 | **直接执行完整流程** |

### 执行流程（简化版 - 无需用户确认）

直接执行阶段1→4：

1. **阶段1：数据收集** - 委派子Agent获取数据
2. **阶段2：数据汇总** - 主Agent解析数据、提取关键发现
3. **阶段3：报告生成** - 生成完整 Markdown 报告（包含所有发现和修复建议）
4. **阶段4：告警推送** - 如发现高危问题，调用 dingtalk_send 或 feishu_send 发送告警

### 报告格式要求（必须完整）

报告必须包含以下内容：

```markdown
## 扫描报告

**扫描概览**
- 扫描仓库数：X 个
- 发现问题总数：Y 个
- 高危/严重问题：Z 个
- 执行时间：YYYY-MM-DD HH:MM:SS

### 详细发现

#### CVE 漏洞（如有）
| CVE ID | 影响仓库 | 严重程度 | 描述 | 修复建议 |
|--------|---------|---------|------|---------|

#### 许可证问题（如有）
| 仓库 | 许可证类型 | 问题 | 建议 |

#### 社区健康问题（如有）
| 仓库 | 问题类型 | 严重程度 | 建议 |

### 修复建议汇总
1. ...
2. ...

### 结论
...
```

**重要**：报告内容将直接存入数据库，用户后续查看执行详情时会看到完整报告。请确保报告完整、清晰。

"""


def get_scheduler_system_prompt() -> str:
    """获取定时任务系统提示词（AGENTS.md + 定时任务规则）。"""

    if not AGENTS_MD_CONTENT:
        # 如果没有 AGENTS.md，使用简化的提示词
        return """
你是定时扫描任务执行助手。

## 核心职责

执行定时扫描任务，生成完整的分析报告。

## 任务分配规则

使用 task 工具委派子Agent：
- 安全扫描 → security-analyzer
- 合规审计 → compliance-analyzer
- 社区健康 → community-analyzer
- 趋势分析 → trend-analyzer

## 委派格式

调用 task 工具时，description 必须包含：

【任务目标】
扫描指定范围的安全风险

【扫描范围】
组织名/仓库：{target}

【输出要求】
1. 漏洞列表（CVE编号、评分、风险等级）
2. 修复建议

## 执行流程

1. 委派子Agent获取数据
2. 解析数据、汇总结果
3. 生成完整 Markdown 报告
4. 高危问题发送告警

""" + SCHEDULER_APPEND_RULES

    # 过滤掉对话生命周期相关内容（定时任务不需要）
    lines_to_remove_markers = [
        "### 1. 对话开始时",
        "### 3. 收到子 Agent 返回后",
        "### 4. 对话结束前",
        "## 长期记忆规范",
        "## 报告生成流程",  # 用定时任务规则替换
    ]

    # 构建简化版内容
    lines = AGENTS_MD_CONTENT.split("\n")
    filtered_lines = []
    skip_until_next_major_section = False

    for line in lines:
        # 检查是否需要跳过某个段落
        for marker in lines_to_remove_markers:
            if line.startswith(marker):
                skip_until_next_major_section = True
                break

        # 检查是否到了下一个主要段落（## 开头）
        if skip_until_next_major_section and line.startswith("##"):
            skip_until_next_major_section = False

        if not skip_until_next_major_section:
            filtered_lines.append(line)

    simplified_content = "\n".join(filtered_lines)

    # 替换报告生成流程部分（阶段4改为直接保存）
    # 添加定时任务特殊规则
    return simplified_content + SCHEDULER_APPEND_RULES


def collect_all_tools() -> List:
    """收集所有子Agent的工具（合并）。"""

    all_tools = []

    # 从 SUBAGENT_TOOLS 收集所有工具
    for subagent_name, tools in SUBAGENT_TOOLS.items():
        for tool in tools:
            if tool not in all_tools:
                all_tools.append(tool)

    # 添加额外的统计工具（定时任务可能需要）
    extra_tools = [
        get_repo_stats,
        get_issue_metrics,
        get_pr_metrics,
        get_star_history,
        get_contributor_activity,
    ]

    for tool in extra_tools:
        if tool not in all_tools:
            all_tools.append(tool)

    logger.info("all_tools_collected", tool_count=len(all_tools), tool_names=[t.name for t in all_tools])
    return all_tools


def create_alert_tools(alert_channels: List) -> List:
    """创建告警工具（基于任务绑定的渠道）。

    Args:
        alert_channels: AlertChannel 对象列表（Pydantic 模型）
    """

    tools = []

    for channel in alert_channels:
        # 处理 Pydantic 模型或字典
        if hasattr(channel, 'model_dump'):
            channel_dict = channel.model_dump()
        elif hasattr(channel, 'dict'):
            channel_dict = channel.dict()
        elif isinstance(channel, dict):
            channel_dict = channel
        else:
            logger.warning("unknown_channel_type", channel_type=type(channel))
            continue

        channel_id = channel_dict.get("id")
        channel_name = channel_dict.get("name")
        channel_type = channel_dict.get("channel_type")
        webhook_url = channel_dict.get("webhook_url")
        secret = channel_dict.get("secret")

        if channel_type == "dingtalk":
            @tool
            async def dingtalk_send(message: str) -> str:
                """发送钉钉告警消息（Markdown格式）。"""
                from app.alert.dingtalk import DingTalkNotifier

                notifier = DingTalkNotifier(webhook_url=webhook_url, secret=secret)
                try:
                    title = message.split('\n')[0][:50] if message else "定时任务告警"
                    success = await notifier.send_markdown(title, message)
                    await notifier.close()

                    if success:
                        logger.info("dingtalk_sent", channel_name=channel_name)
                        return f"告警已发送到钉钉 [{channel_name}]"
                    else:
                        return f"发送失败，请检查渠道 [{channel_name}] 配置"
                except Exception as e:
                    logger.error("dingtalk_send_error", channel_name=channel_name, error=str(e))
                    return f"发送失败: {str(e)}"

            # 重命名工具以区分不同渠道
            dingtalk_send.name = f"dingtalk_send_{channel_id}"
            tools.append(dingtalk_send)

        elif channel_type == "feishu":
            @tool
            async def feishu_send(message: str) -> str:
                """发送飞书告警消息。"""
                from app.alert.feishu import FeishuNotifier

                notifier = FeishuNotifier(webhook_url=webhook_url)
                try:
                    success = await notifier.send_text(message)
                    await notifier.close()

                    if success:
                        logger.info("feishu_sent", channel_name=channel_name)
                        return f"告警已发送到飞书 [{channel_name}]"
                    else:
                        return f"发送失败，请检查渠道 [{channel_name}] 配置"
                except Exception as e:
                    logger.error("feishu_send_error", channel_name=channel_name, error=str(e))
                    return f"发送失败: {str(e)}"

            feishu_send.name = f"feishu_send_{channel_id}"
            tools.append(feishu_send)

    # 如果没有配置告警渠道，添加一个默认工具
    if not tools:
        @tool
        async def no_alert_channel(message: str) -> str:
            """提示未配置告警渠道。"""
            return "未配置告警渠道，报告将仅保存到数据库"

        tools.append(no_alert_channel)

    return tools


async def create_scheduler_agent(
    backend: OpenSandboxBackend,
    alert_channels: List[Dict] = None
) -> Any:
    """创建定时任务 Agent（复用对话分析架构，无记忆）。

    Args:
        backend: 任务独立沙箱 Backend
        alert_channels: 任务绑定的告警渠道列表

    Returns:
        Agent 实例
    """

    logger.info("creating_scheduler_agent")

    # 1. 加载子Agent（与对话分析相同）
    subagents_dir = os.getenv("SUBAGENTS_DIR", "./subagents")
    loader = SubAgentLoader(subagents_dir)
    subagents = loader.load_all()
    logger.info("subagents_loaded_for_scheduler", count=len(subagents))

    # 2. 收集工具
    all_tools = collect_all_tools()

    # 3. 添加告警工具
    if alert_channels:
        alert_tools = create_alert_tools(alert_channels)
        all_tools.extend(alert_tools)

    # 4. 创建 Backend 工厂（使用任务独立沙箱）
    def backend_factory(runtime):
        return CompositeBackend(default=backend, routes={})

    # 5. 创建 Agent（无记忆）
    agent = create_deep_agent(
        model=get_default_model(),
        system_prompt=get_scheduler_system_prompt(),
        memory=["/memories/AGENTS.md"],  # 只加载执行准则，不加载用户偏好
        subagents=subagents,              # 复用子Agent系统
        tools=all_tools,                  # 复用工具集 + 告警工具
        backend=backend_factory,          # 任务独立沙箱
        checkpointer=None,                # 无对话状态
        store=None,                       # 无长期记忆
    )

    logger.info("scheduler_agent_created", tool_count=len(all_tools))
    return agent