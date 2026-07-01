"""Agent 创建模块。"""

import os
from deepagents import create_deep_agent
from deepagents.middleware.skills import SkillsMiddleware
from langgraph.checkpoint.mysql.aio import AIOMySQLSaver
from langgraph.store.base import BaseStore
from app.loader import SubAgentLoader
from app.tools.common import common_tools
from app.tools.skill_management import skill_tools
from app.tools.scheduler_tools import scheduler_tools
from app.backend_factory import create_backend
from app.middleware import ToolErrorHandlerMiddleware
from app.log_utils import get_logger
from app.llm_config import get_default_model

logger = get_logger("agent")

MAIN_SYSTEM_PROMPT = """
你是 GitHub 开源情报系统的总指挥。

## 职责

1. 接收用户指令，首先回复确认已收到请求
2. 使用 write_todos 规划任务
3. **必须**使用 task 工具委托子Agent执行具体分析
4. 汇总结果生成报告，使用 return_report_for_download 工具返回报告
5. **支持创建定时任务**：用户请求定时扫描时，使用 create_scheduled_task 工具

## 核心原则 - 必须遵守

- **分析任务必须使用 task 工具委派子Agent处理**
- **所有子Agent工具都支持单仓库和多仓库**
- **参数格式统一：repos="owner/repo" 或 repos="owner/repo1,owner/repo2"**
- **定时任务请求必须使用 create_scheduled_task 工具**

## 定时任务工具

当用户说"帮我每天扫描"、"每周检查"等定时需求时，使用以下工具：

- create_scheduled_task: 创建定时扫描任务
- list_scheduled_tasks: 查看所有定时任务
- pause_scheduled_task: 暂停任务
- resume_scheduled_task: 恢复任务
- delete_scheduled_task: 删除任务

**Cron 表达式说明**：
- "0 9 * * *" = 每天 9:00
- "0 9 * * 1" = 每周一 9:00
- "*/10 * * * *" = 每 10 分钟
- "0 0 * * *" = 每天凌晨

**创建定时任务示例**：
用户: "帮我每天凌晨3点扫描 github 组织的安全漏洞"
Agent 调用: create_scheduled_task(
    name="每日github安全扫描",
    target_type="org",
    target_name="github",
    cron_expression="0 3 * * *",
    prompt="扫描 github 组织的 CVE 漏洞和敏感信息",
    dimensions=["cve", "secret"]
)

## 可用子Agent（通过 task 工具调用）

- security-analyzer: 安全风控扫描（CVE、漏洞、敏感信息）
- compliance-analyzer: 合规审计（许可证、版权）
- community-analyzer: 社区健康分析（Issue、PR、贡献者）
- trend-analyzer: 技术趋势分析（Star、增长）

## 委派策略 - 根据范围选择正确的描述

**关键原则**：在委派描述中明确告诉子Agent参数格式！

| 用户请求范围 | 委派描述示例 |
|-------------|-------------|
| 整个组织 | "使用 scan_org 扫描 GitHub 组织" |
| 多个仓库 | "使用 check_cve_repos 检查 repos='microsoft/vscode,microsoft/typescript'" |
| 单个仓库 | "使用 check_cve_repos 检查 repos='microsoft/vscode'" |

## 并发委派示例

用户请求: "分析 SOFAStack 组织的安全和合规情况"

```json
[
  {"name": "task", "args": {"subagent_type": "security-analyzer", "description": "使用 scan_org(org_name='sofastack', dimensions='cve,secret') 扫描整个组织的安全漏洞"}},
  {"name": "task", "args": {"subagent_type": "compliance-analyzer", "description": "使用 scan_org(org_name='sofastack', dimensions='license') 扫描整个组织的许可证合规"}}
]
```

**错误做法**: 逐个仓库委派（效率极低）

## 工作流程

用户请求: "分析 sofa-rpc 和 sofa-boot 的安全漏洞"

正确流程:
1. write_todos: ["委派 security-analyzer 检查两个仓库"]
2. task: {"description": "使用 check_cve_repos(repos='sofastack/sofa-rpc,sofastack/sofa-boot')"}
3. 等待结果
4. 汇总报告
5. return_report_for_download

用户请求: "每10分钟扫描 ant-group 组织"

正确流程:
1. write_todos: ["创建定时任务"]
2. create_scheduled_task: {
    name: "ant-group 定时扫描",
    target_type: "org",
    target_name: "ant-group",
    cron_expression: "*/10 * * * *",
    prompt: "扫描 ant-group 组织的安全漏洞和合规问题",
    dimensions: ["cve", "license"]
}
3. 告知用户任务已创建
"""


async def create_agent(checkpointer=None, store: BaseStore = None):
    """创建 DeepAgents 主 Agent（仅支持沙箱模式）。

    Args:
        checkpointer: 可选的 checkpoint saver 实例
        store: 可选的 BaseStore 实例（用于长期记忆和技能存储）

    Returns:
        tuple: (agent, backend) - Agent 实例和沙箱后端实例

    Raises:
        RuntimeError: 如果沙箱初始化失败
    """
    logger.info("create_agent_start")

    # ---------- 1. 配置百炼大模型平台 ----------
    dashscope_api_key = os.getenv("DASHSCOPE_API_KEY")
    if dashscope_api_key:
        os.environ["OPENAI_API_KEY"] = dashscope_api_key
        os.environ["OPENAI_API_BASE"] = os.getenv(
            "OPENAI_API_BASE",
            "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        logger.info("bailian_platform_configured", api_key_present=True)

    # ---------- 2. 初始化模型（使用统一配置）----------
    model = get_default_model()
    logger.info("model_initialized", use_responses_api=False)

    # ---------- 3. 创建沙箱 Backend（必须成功）----------
    logger.info("backend_creating", mode="sandbox_required")

    backend_factory = await create_backend()  # 强制使用沙箱
    logger.info("backend_created")

    # 获取实际 backend 实例（用于下载路由和技能加载）
    actual_backend = None
    composite = None
    try:
        composite = backend_factory(None)
        actual_backend = composite.default
        logger.info("sandbox_backend_extracted",
                    backend_type=type(actual_backend).__name__,
                    sandbox_id=actual_backend.id)
    except Exception as e:
        logger.error("backend_extract_failed", error=str(e))
        raise RuntimeError(f"沙箱后端初始化失败: {e}")

    # ---------- 4. 加载子Agent ----------
    subagents_dir = os.getenv("SUBAGENTS_DIR", "./subagents")
    logger.info("subagents_loading", directory=subagents_dir)

    loader = SubAgentLoader(subagents_dir)
    subagents = loader.load_all()
    logger.info("subagents_loaded", count=len(subagents), names=[s["name"] for s in subagents])

    # ---------- 5. 配置 Store ----------
    if store:
        logger.info("store_configured", store_type=type(store).__name__)
    else:
        logger.warning("store_not_configured", message="StoreBackend operations may fail")

    # ---------- 6. 配置 memory（沙箱路径）----------
    memory_config = ["/memories/AGENTS.md"]
    logger.info("memory_config_sandbox", path="/memories/AGENTS.md")

    logger.info("deep_agent_creating",
                has_checkpointer=checkpointer is not None,
                has_memory=memory_config is not None)

    agent = create_deep_agent(
        model=model,
        system_prompt=MAIN_SYSTEM_PROMPT,
        memory=memory_config,
        subagents=subagents,
        tools=common_tools + skill_tools + scheduler_tools,
        checkpointer=checkpointer,
        backend=backend_factory,
        store=store,
        middleware=[
            SkillsMiddleware(
                backend=composite,
                sources=["/skills/main/"],
            ),
            ToolErrorHandlerMiddleware(),
        ],
    )
    logger.info("agent_created_successfully",
                tool_count=len(common_tools) + len(skill_tools) + len(scheduler_tools),
                sandbox_id=actual_backend.id)

    return agent, actual_backend