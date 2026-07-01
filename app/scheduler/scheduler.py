"""定时任务调度器 - Agent 生成的定时任务执行引擎。

架构设计：
- 每个任务独立申请沙箱，执行完成后销毁
- 使用 deepagents.create_deep_agent，复用对话分析的子Agent系统
- 无记忆（checkpointer=None, store=None）
- 执行步骤记录到 scheduled_task_execution 表
- 报告存入数据库，用户后续查看

与对话分析的区别：
| 对话分析 | 定时任务 |
|---------|---------|
| 共用沙箱 | 独立沙箱，用完销毁 |
| 有记忆 | 无记忆 |
| 报告下载给用户 | 报告存入数据库 |
"""

import os
import asyncio
import json
import traceback
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from croniter import croniter
import httpx

from app.database import ScheduledTaskDAO, ScheduledTaskExecutionDAO, AlertChannelDAO, init_business_tables
from app.log_utils import get_logger
from app.progress.scheduled_task_tracker import ScheduledTaskProgressTracker, get_scheduled_task_queue
from app.scheduler.sandbox_pool import TaskSandboxPool
from app.scheduler.scheduler_agent import create_scheduler_agent

logger = get_logger("scheduler")

# ==================== 配置 ====================

SCHEDULED_TASK_MAX_PARALLEL = int(os.getenv("SCHEDULED_TASK_MAX_PARALLEL", "10"))
SCHEDULED_TASK_TIMEOUT = int(os.getenv("SCHEDULED_TASK_TIMEOUT", "600"))  # 增加到10分钟
SCHEDULED_TASK_TICK_INTERVAL = int(os.getenv("SCHEDULED_TASK_TICK_INTERVAL", "60"))


# ==================== 调度器 ====================

_scheduler: Optional[AsyncIOScheduler] = None
_semaphore: Optional[asyncio.Semaphore] = None


async def init_scheduler():
    """初始化调度器。"""
    global _scheduler, _semaphore

    logger.info("scheduler_init_start")
    await init_business_tables()

    _semaphore = asyncio.Semaphore(SCHEDULED_TASK_MAX_PARALLEL)
    _scheduler = AsyncIOScheduler()

    # 添加 tick 任务（每分钟检查到期任务）
    _scheduler.add_job(
        func=tick,
        trigger="interval",
        seconds=SCHEDULED_TASK_TICK_INTERVAL,
        id="scheduler_tick",
        replace_existing=True
    )

    _scheduler.start()
    logger.info("scheduler_initialized",
                tick_interval=SCHEDULED_TASK_TICK_INTERVAL,
                max_parallel=SCHEDULED_TASK_MAX_PARALLEL,
                scheduler_running=_scheduler.running)

    # 打印当前所有 jobs
    jobs = _scheduler.get_jobs()
    logger.info("scheduler_jobs_registered", job_count=len(jobs), job_ids=[j.id for j in jobs])


async def stop_scheduler():
    """停止调度器。"""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=True)
        logger.info("scheduler_stopped")


def get_scheduler() -> AsyncIOScheduler:
    """获取调度器实例。"""
    return _scheduler


# ==================== Tick 执行 ====================

async def tick():
    """检查并执行到期任务。

    每60秒调用一次，检查 scheduled_task 表中的到期任务。
    """
    logger.info("tick_start", timestamp=datetime.now().isoformat())
    await init_business_tables()

    tasks = await ScheduledTaskDAO.list_active()
    now = datetime.now()
    logger.info("tick_active_tasks_found", count=len(tasks))

    due_tasks = []
    for task in tasks:
        task_next_run = task.next_run_at
        logger.debug("tick_checking_task",
                     task_id=task.id,
                     task_name=task.name,
                     next_run_at=task_next_run.isoformat() if task_next_run else "None",
                     cron=task.cron_expression)

        # 检查是否到期
        if task_next_run and task_next_run <= now:
            logger.info("tick_task_due", task_id=task.id, task_name=task.name, next_run_at=task_next_run.isoformat())
            due_tasks.append(task)
        elif not task_next_run:
            # 计算下次执行时间
            try:
                cron = croniter(task.cron_expression, now)
                next_run = cron.get_next(datetime)
                await ScheduledTaskDAO.update(task.id, {"next_run_at": next_run})
                logger.info("next_run_calculated", task_id=task.id, next_run=next_run.isoformat(), cron=task.cron_expression)
            except Exception as e:
                logger.warning("cron_parse_error", task_id=task.id, cron=task.cron_expression, error=str(e))

    if not due_tasks:
        logger.debug("tick_no_due_tasks", checked=len(tasks))
        return

    logger.info("tick_due_tasks", count=len(due_tasks))

    # 先更新下次执行时间（保证 at-most-once）
    for task in due_tasks:
        try:
            cron = croniter(task.cron_expression, now)
            next_run = cron.get_next(datetime)
            await ScheduledTaskDAO.update(task.id, {"next_run_at": next_run})
        except Exception as e:
            logger.warning("next_run_update_failed", task_id=task.id, error=str(e))

    # 并发执行任务（受 semaphore 控制）
    async def run_with_limit(task):
        async with _semaphore:
            return await run_scheduled_task_safe(task)

    await asyncio.gather(*[run_with_limit(t) for t in due_tasks], return_exceptions=True)

    logger.info("tick_completed", executed=len(due_tasks))


# ==================== 执行上下文 ====================

class ExecutionContext:
    """执行上下文，用于记录详细执行内容。"""

    def __init__(self):
        self.tool_calls: List[Dict] = []
        self.steps: List[Dict] = []
        self.logs: List[str] = []
        self.agent_output: str = ""
        self.total_findings: int = 0
        self.high_severity_count: int = 0
        self.start_time: datetime = None

    def add_log(self, message: str):
        """添加日志。"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.logs.append(f"[{timestamp}] {message}")

    def add_tool_call(self, tool_name: str, input_data: Any, output: Any, status: str, duration_ms: int = 0):
        """添加工具调用记录。"""
        self.tool_calls.append({
            "tool": tool_name,
            "input": str(input_data)[:500] if input_data else "",
            "output": str(output)[:2000] if output else "",
            "status": status,
            "duration_ms": duration_ms,
            "timestamp": datetime.now().isoformat()
        })

        # 解析 findings 数量
        if status == "done" and output:
            self._parse_findings(output)

    def _parse_findings(self, output: Any):
        """解析工具输出中的 findings 数量。"""
        try:
            if isinstance(output, dict):
                self.total_findings += output.get("total_findings", 0) or output.get("findings_count", 0)
                self.high_severity_count += output.get("high_severity_count", 0) or output.get("high_critical_count", 0)
            elif isinstance(output, str):
                parsed = json.loads(output)
                self.total_findings += parsed.get("total_findings", 0) or parsed.get("findings_count", 0)
                self.high_severity_count += parsed.get("high_severity_count", 0) or parsed.get("high_critical_count", 0)
        except Exception:
            pass

    def add_step(self, name: str, status: str, message: str = ""):
        """添加执行步骤。"""
        self.steps.append({
            "name": name,
            "status": status,  # running | done | failed | info
            "message": message,
            "timestamp": datetime.now().isoformat()
        })

    def get_execution_log(self) -> str:
        """获取完整执行日志。"""
        return "\n".join(self.logs)

    def to_dict(self) -> Dict:
        """转换为字典。"""
        return {
            "tool_calls": self.tool_calls,
            "steps": self.steps,
            "agent_output": self.agent_output,
            "execution_log": self.get_execution_log(),
            "total_findings": self.total_findings,
            "high_severity_count": self.high_severity_count,
        }


# ==================== 安全执行 ====================

async def run_scheduled_task_safe(task):
    """安全执行定时任务。

    流程：
    1. 检查任务状态（确保是 active）
    2. 创建独立沙箱
    3. 创建 Agent（复用对话分析架构，无记忆）
    4. 执行任务，记录每一步数据
    5. 写入执行记录到数据库
    6. 销毁沙箱
    """
    run_id = f"SCHED_{task.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # 0. 首先检查任务状态
    current_task = await ScheduledTaskDAO.get_by_id(task.id)
    if not current_task or current_task.status != 'active' or not current_task.enabled:
        logger.warning("task_skipped_not_active", task_id=task.id, status=current_task.status if current_task else "not_found")
        return  # 跳过执行

    tracker = ScheduledTaskProgressTracker(task.id, run_id)
    ctx = ExecutionContext()
    ctx.start_time = datetime.now()

    sandbox_pool = TaskSandboxPool.get_instance()
    backend = None
    agent = None

    ctx.add_log(f"任务开始执行: {task.name} (ID: {task.id})")
    ctx.add_log(f"Run ID: {run_id}")
    ctx.add_log(f"Prompt: {task.prompt[:200]}...")
    logger.info("task_execution_start", task_id=task.id, task_name=task.name, run_id=run_id)

    try:
        # 1. 更新任务状态
        await ScheduledTaskDAO.update_run_start(task.id, run_id, datetime.now())
        ctx.add_log("任务状态已更新为 running")

        # 2. 推送开始事件
        await tracker.start()
        ctx.add_step("init", "done", "任务初始化完成")

        # 3. 创建执行记录
        execution_id = await ScheduledTaskExecutionDAO.create({
            "scheduled_task_id": task.id,
            "run_id": run_id,
            "status": "running",
            "started_at": datetime.now()
        })
        ctx.add_log(f"执行记录已创建: execution_id={execution_id}")

        # 4. 获取告警渠道配置
        channel_ids = task.alert_channel_ids or []
        alert_channels = []
        if channel_ids:
            alert_channels = await AlertChannelDAO.get_by_ids(channel_ids)
            ctx.add_log(f"加载了 {len(alert_channels)} 个告警渠道")

        # 5. 创建独立沙箱
        ctx.add_step("sandbox_create", "running", "申请沙箱资源...")
        backend = await sandbox_pool.create_for_task(task.id)
        ctx.add_step("sandbox_create", "done", "执行环境已就绪")
        ctx.add_log(f"沙箱创建成功")

        # 6. 创建 Agent
        ctx.add_step("agent_create", "running", "创建执行 Agent...")
        agent = await create_scheduler_agent(backend, alert_channels)
        ctx.add_step("agent_create", "done", "Agent 已创建")
        ctx.add_log("Agent 已创建 (deepagents.create_deep_agent)")

        # 7. 执行任务（捕获每一步事件）
        ctx.add_step("task_execute", "running", "开始执行扫描任务...")

        # 构建 prompt（包含任务信息）
        full_prompt = task.prompt
        if task.target_type == "org" and task.target_name:
            full_prompt = f"{task.prompt}\n\n目标组织: {task.target_name}"

        agent_output = ""
        current_tool_start_time = None
        current_tool_name = None

        MAX_RETRIES = 3
        RETRY_DELAY = 5

        for retry_count in range(MAX_RETRIES):
            try:
                ctx.add_log(f"开始执行 Agent (尝试 {retry_count + 1}/{MAX_RETRIES})")

                # 使用 astream_events 捕获执行过程
                async for event in agent.astream_events(
                    {"messages": [{"role": "user", "content": full_prompt}]},
                    version="v2"
                ):
                    event_type = event.get("event")
                    event_name = event.get("name", "")
                    event_data = event.get("data", {})

                    # 工具调用开始
                    if event_type == "on_tool_start":
                        current_tool_name = event_name
                        current_tool_start_time = datetime.now()
                        tool_input = event_data.get("input", {})

                        ctx.add_log(f"工具调用开始: {event_name}")
                        ctx.add_step(f"tool:{event_name}", "running", f"输入: {str(tool_input)[:200]}")
                        ctx.add_tool_call(event_name, tool_input, None, "running")
                        await tracker.tool_start(event_name)

                    # 工具调用完成
                    elif event_type == "on_tool_end":
                        tool_output = event_data.get("output", "")
                        duration_ms = 0
                        if current_tool_start_time and current_tool_name == event_name:
                            duration_ms = int((datetime.now() - current_tool_start_time).total_seconds() * 1000)
                            current_tool_start_time = None
                            current_tool_name = None

                        ctx.add_log(f"工具调用完成: {event_name} ({duration_ms}ms)")
                        ctx.add_step(f"tool:{event_name}", "done", f"完成")
                        ctx.add_tool_call(event_name, None, tool_output, "done", duration_ms)
                        await tracker.tool_end(event_name, tool_output)

                    # 工具调用错误
                    elif event_type == "on_tool_error":
                        error_msg = str(event_data.get("error", event_data))
                        duration_ms = 0
                        if current_tool_start_time and current_tool_name == event_name:
                            duration_ms = int((datetime.now() - current_tool_start_time).total_seconds() * 1000)
                            current_tool_start_time = None
                            current_tool_name = None

                        ctx.add_log(f"工具调用失败: {event_name} - {error_msg[:200]}")
                        ctx.add_step(f"tool:{event_name}", "failed", error_msg[:200])
                        ctx.add_tool_call(event_name, None, f"ERROR: {error_msg}", "failed", duration_ms)
                        await tracker.tool_end(event_name, f"Error: {error_msg}")

                    # 子Agent开始
                    elif event_type == "on_chain_start":
                        if "agent" in event_name.lower() and event_name not in ["Agent", "agent"]:
                            ctx.add_log(f"子Agent开始执行: {event_name}")
                            ctx.add_step(f"subagent:{event_name}", "running", "开始执行")

                    # 子Agent完成
                    elif event_type == "on_chain_end":
                        if "agent" in event_name.lower() and event_name not in ["Agent", "agent"]:
                            output_data = event_data.get("output", {})
                            if output_data:
                                messages = []
                                if isinstance(output_data, dict):
                                    messages = output_data.get("messages", [])
                                elif isinstance(output_data, list):
                                    messages = output_data

                                if messages:
                                    last_msg = messages[-1]
                                    if hasattr(last_msg, "content"):
                                        content_preview = last_msg.content[:200] if last_msg.content else ""
                                        ctx.add_log(f"子Agent完成: {event_name}")
                                        ctx.add_step(f"subagent:{event_name}", "done", content_preview)

                        # 主Agent最终输出
                        if event_name in ["Agent", "agent", "LangGraphAgent"]:
                            output_data = event_data.get("output", {})
                            if output_data:
                                messages = []
                                if isinstance(output_data, dict):
                                    messages = output_data.get("messages", [])
                                elif isinstance(output_data, list):
                                    messages = output_data

                                if messages:
                                    last_msg = messages[-1]
                                    if hasattr(last_msg, "content") and last_msg.content:
                                        agent_output = last_msg.content

                    # LLM 流式输出
                    elif event_type == "on_chat_model_stream":
                        chunk = event_data.get("chunk")
                        if chunk and hasattr(chunk, "content") and chunk.content:
                            agent_output += chunk.content

                # 成功完成，跳出重试循环
                ctx.add_log(f"Agent 流执行完成 (尝试 {retry_count + 1})")
                break

            except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ConnectError) as e:
                ctx.add_log(f"网络连接错误: {str(e)}")
                logger.warning("agent_network_error", task_id=task.id, error=str(e), retry_count=retry_count)

                if retry_count < MAX_RETRIES - 1:
                    ctx.add_log(f"等待 {RETRY_DELAY} 秒后重试...")
                    await asyncio.sleep(RETRY_DELAY)
                    continue
                else:
                    ctx.add_log(f"达到最大重试次数 ({MAX_RETRIES})，任务失败")
                    raise

            except Exception as e:
                ctx.add_log(f"Agent 流执行出错: {str(e)}")
                logger.error("agent_stream_error", task_id=task.id, error=str(e), traceback=traceback.format_exc())
                raise

        # 8. 设置最终输出
        ctx.agent_output = agent_output
        ctx.add_step("task_execute", "done", "任务执行完成")
        ctx.add_log(f"Agent 执行完成，共发现 {ctx.total_findings} 个问题，高危 {ctx.high_severity_count} 个")

        # 9. 完成执行记录
        await ScheduledTaskExecutionDAO.complete(
            run_id=run_id,
            status="completed",
            agent_output=ctx.agent_output,
            tool_calls=ctx.tool_calls,
            steps=ctx.steps,
            execution_log=ctx.get_execution_log(),
            total_findings=ctx.total_findings,
            high_severity_count=ctx.high_severity_count,
        )

        await ScheduledTaskDAO.update_run_complete(task.id, "completed")
        await tracker.complete({
            "total_findings": ctx.total_findings,
            "high_severity_count": ctx.high_severity_count,
            "agent_output": ctx.agent_output,
        })

        logger.info("task_completed", task_id=task.id, run_id=run_id,
                    findings=ctx.total_findings)

    except asyncio.TimeoutError:
        ctx.add_log(f"任务执行超时（超过 {SCHEDULED_TASK_TIMEOUT} 秒）")
        ctx.add_step("timeout", "failed", f"执行超时（{SCHEDULED_TASK_TIMEOUT}秒）")
        logger.warning("task_timeout", task_id=task.id, run_id=run_id)

        await tracker.fail("任务执行超时")
        await ScheduledTaskExecutionDAO.complete(
            run_id=run_id,
            status="failed",
            error="执行超时",
            error_detail=f"任务执行超过 {SCHEDULED_TASK_TIMEOUT} 秒被终止",
            tool_calls=ctx.tool_calls,
            steps=ctx.steps,
            execution_log=ctx.get_execution_log(),
        )
        await ScheduledTaskDAO.update_run_complete(task.id, "failed")

    except Exception as e:
        error_traceback = traceback.format_exc()
        ctx.add_log(f"执行出错: {str(e)}")
        ctx.add_step("error", "failed", str(e))
        logger.error("task_execution_error", task_id=task.id, run_id=run_id, error=str(e), traceback=error_traceback)

        await tracker.fail(str(e))
        await ScheduledTaskExecutionDAO.complete(
            run_id=run_id,
            status="failed",
            error=str(e),
            error_detail=error_traceback,
            tool_calls=ctx.tool_calls,
            steps=ctx.steps,
            execution_log=ctx.get_execution_log(),
        )
        await ScheduledTaskDAO.update_run_complete(task.id, "failed")

    finally:
        # 10. 销毁沙箱（不记录销毁步骤）
        if backend:
            await sandbox_pool.destroy_for_task(task.id)
            ctx.add_log("沙箱已销毁")

        # 销毁 Agent
        if agent:
            del agent

        logger.info("task_cleanup_done", task_id=task.id, run_id=run_id,
                    active_sandboxes=sandbox_pool.get_active_count())