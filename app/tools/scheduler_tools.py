"""Agent 定时任务工具 - 让 Agent 为用户创建和管理定时任务。

参考 HermesAgent 的 cronjob 工具设计，提供类似的接口。
"""

import os
import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from langchain_core.tools import tool
from croniter import croniter

from app.database import ScheduledTaskDAO, ScheduledTaskExecutionDAO, init_business_tables
from app.log_utils import get_logger

logger = get_logger("scheduler_tools")


# ==================== 定时任务创建工具 ====================

@tool
async def create_scheduled_task(
    name: str,
    target_type: str,
    target_name: str,
    cron_expression: str,
    prompt: str,
    dimensions: Optional[List[str]] = None,
    alert_threshold: str = "HIGH",
    description: str = ""
) -> str:
    """创建定时扫描任务（Agent调用）。

    Args:
        name: 任务名称，如 "每日alibaba安全扫描"
        target_type: 目标类型，"org" 或 "repo"
        target_name: 目标名称，如 "alibaba" 或 "alibaba/nacos"
        cron_expression: cron表达式，如 "0 2 * * *" 表示每日凌晨2点
        prompt: Agent 执行的 prompt，描述要执行的任务
        dimensions: 扫描维度列表，如 ["cve", "secret", "license", "community"]
        alert_threshold: 告警阈值，"CRITICAL"/"HIGH"/"MEDIUM"
        description: 任务描述

    Returns:
        创建结果 JSON
    """
    await init_business_tables()

    # 验证 cron 表达式
    try:
        cron = croniter(cron_expression, datetime.now())
        next_run = cron.get_next(datetime)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"无效的cron表达式: {cron_expression}",
            "detail": str(e)
        })

    # 验证目标类型
    if target_type not in ["org", "repo"]:
        return json.dumps({
            "success": False,
            "error": f"无效的 target_type: {target_type}，必须是 org 或 repo"
        })

    # 默认维度
    if not dimensions:
        dimensions = ["cve", "secret", "license"]

    # 构建 prompt（如果没有足够信息）
    if not prompt or len(prompt) < 10:
        prompt = f"扫描 {target_name} 的安全问题，检查维度: {', '.join(dimensions)}，发现 {alert_threshold} 及以上问题推送钉钉"

    # 创建任务
    task_data = {
        "name": name,
        "description": description or f"Agent创建: 每日扫描 {target_name}",
        "target_type": target_type,
        "target_name": target_name,
        "prompt": prompt,
        "cron_expression": cron_expression,
        "dimensions": dimensions,
        "alert_threshold": alert_threshold,
        "created_by": "agent"
    }

    task_id = await ScheduledTaskDAO.create(task_data)

    # 更新下次执行时间
    await ScheduledTaskDAO.update(task_id, {"next_run_at": next_run})

    logger.info("scheduled_task_created_by_agent",
                task_id=task_id,
                name=name,
                cron=cron_expression,
                target=f"{target_type}:{target_name}")

    return json.dumps({
        "success": True,
        "task_id": task_id,
        "name": name,
        "target": f"{target_type}:{target_name}",
        "cron": cron_expression,
        "dimensions": dimensions,
        "next_run": next_run.isoformat(),
        "message": f"定时任务已创建: {name}，下次执行时间: {next_run.strftime('%Y-%m-%d %H:%M')}"
    }, indent=2)


@tool
async def list_scheduled_tasks(
    target_type: Optional[str] = None,
    target_name: Optional[str] = None,
    status: Optional[str] = None
) -> str:
    """查看定时任务列表。

    Args:
        target_type: 筛选目标类型 "org" 或 "repo"
        target_name: 筛选目标名称
        status: 筛选状态 "active" | "paused" | "disabled"

    Returns:
        任务列表 JSON
    """
    await init_business_tables()

    tasks = await ScheduledTaskDAO.list_all(
        target_type=target_type,
        target_name=target_name,
        status=status
    )

    return json.dumps({
        "success": True,
        "count": len(tasks),
        "tasks": [
            {
                "id": t.id,
                "name": t.name,
                "target": f"{t.target_type}:{t.target_name}",
                "cron": t.cron_expression,
                "dimensions": t.dimensions,
                "prompt_preview": t.prompt[:100] + "..." if len(t.prompt) > 100 else t.prompt,
                "status": t.status,
                "enabled": t.enabled,
                "last_run": t.last_run_at.isoformat() if t.last_run_at else None,
                "last_status": t.last_run_status,
                "next_run": t.next_run_at.isoformat() if t.next_run_at else None,
                "run_count": t.run_count
            }
            for t in tasks
        ]
    }, indent=2)


@tool
async def update_scheduled_task(
    task_id: int,
    updates: Dict[str, Any]
) -> str:
    """更新定时任务配置。

    Args:
        task_id: 任务ID
        updates: 更新内容，可包含:
            - name: 任务名称
            - cron_expression: cron表达式
            - prompt: 更新 prompt
            - dimensions: 更新扫描维度
            - status: 切换状态 "active" | "paused" | "disabled"

    Returns:
        更新结果 JSON
    """
    await init_business_tables()

    # 如果更新 cron，验证表达式
    if "cron_expression" in updates:
        try:
            cron = croniter(updates["cron_expression"], datetime.now())
            next_run = cron.get_next(datetime)
            updates["next_run_at"] = next_run
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"无效的cron表达式: {updates['cron_expression']}"
            })

    success = await ScheduledTaskDAO.update(task_id, updates)

    if success:
        return json.dumps({
            "success": True,
            "message": f"任务 {task_id} 已更新",
            "updates": list(updates.keys())
        })
    else:
        return json.dumps({
            "success": False,
            "error": f"任务 {task_id} 更新失败或不存在"
        })


@tool
async def pause_scheduled_task(task_id: int) -> str:
    """暂停定时任务。"""
    await init_business_tables()
    success = await ScheduledTaskDAO.pause(task_id)
    return json.dumps({
        "success": success,
        "message": f"任务 {task_id} 已暂停" if success else f"任务 {task_id} 暂停失败"
    })


@tool
async def resume_scheduled_task(task_id: int) -> str:
    """恢复定时任务。"""
    await init_business_tables()
    success = await ScheduledTaskDAO.resume(task_id)
    return json.dumps({
        "success": success,
        "message": f"任务 {task_id} 已恢复" if success else f"任务 {task_id} 恢复失败"
    })


@tool
async def delete_scheduled_task(task_id: int) -> str:
    """删除定时任务。"""
    await init_business_tables()
    success = await ScheduledTaskDAO.delete(task_id)
    return json.dumps({
        "success": success,
        "message": f"任务 {task_id} 已删除" if success else f"任务 {task_id} 删除失败"
    })


@tool
async def get_task_executions(task_id: int, limit: int = 10) -> str:
    """查看任务的执行历史。"""
    await init_business_tables()

    executions = await ScheduledTaskExecutionDAO.list_by_task(task_id, limit)

    return json.dumps({
        "success": True,
        "task_id": task_id,
        "count": len(executions),
        "executions": [
            {
                "run_id": e.run_id,
                "status": e.status,
                "started_at": e.started_at.isoformat(),
                "completed_at": e.completed_at.isoformat() if e.completed_at else None,
                "duration_seconds": e.duration_seconds,
                "total_findings": e.total_findings,
                "high_severity_count": e.high_severity_count,
                "error": e.error_message,
                "steps": e.steps
            }
            for e in executions
        ]
    }, indent=2)


# ==================== 工具注册信息 ====================

SCHEDULER_TOOLS_INFO = {
    "create_scheduled_task": {
        "name": "create_scheduled_task",
        "description": """创建定时扫描任务。

用户说"帮我每天凌晨3点扫描alibaba组织"时调用此工具。

参数说明:
- name: 任务名称，如 "每日alibaba安全扫描"
- target_type: "org" 或 "repo"
- target_name: 组织名或仓库全名
- cron_expression: "0 3 * * *" (每天3点) 或 "0 9 * * 1-5" (周一到周五9点)
- prompt: Agent 执行的任务描述
- dimensions: 扫描维度列表 ["cve", "secret", "license", "community"]
""",
        "emoji": "⏰"
    },
    "list_scheduled_tasks": {
        "name": "list_scheduled_tasks",
        "description": "查看定时任务列表",
        "emoji": "📋"
    },
    "update_scheduled_task": {
        "name": "update_scheduled_task",
        "description": "更新定时任务配置",
        "emoji": "🔧"
    },
    "pause_scheduled_task": {
        "name": "pause_scheduled_task",
        "description": "暂停定时任务",
        "emoji": "⏸️"
    },
    "resume_scheduled_task": {
        "name": "resume_scheduled_task",
        "description": "恢复定时任务",
        "emoji": "▶️"
    },
    "delete_scheduled_task": {
        "name": "delete_scheduled_task",
        "description": "删除定时任务",
        "emoji": "🗑️"
    },
    "get_task_executions": {
        "name": "get_task_executions",
        "description": "查看任务执行历史",
        "emoji": "📜"
    }
}

# ==================== 工具列表导出 ====================

scheduler_tools = [
    create_scheduled_task,
    list_scheduled_tasks,
    update_scheduled_task,
    pause_scheduled_task,
    resume_scheduled_task,
    delete_scheduled_task,
    get_task_executions,
]

__all__ = [
    "create_scheduled_task",
    "list_scheduled_tasks",
    "update_scheduled_task",
    "pause_scheduled_task",
    "resume_scheduled_task",
    "delete_scheduled_task",
    "get_task_executions",
    "scheduler_tools",
    "SCHEDULER_TOOLS_INFO",
]