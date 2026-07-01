"""定时任务 API 路由 - SSE 进度推送。"""

import asyncio
import json
from datetime import datetime
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from typing import Dict, Any, Optional

from app.database import ScheduledTaskDAO, ScheduledTaskExecutionDAO, init_business_tables
from app.progress.scheduled_task_tracker import get_scheduled_task_queue, remove_scheduled_task_queue
from app.log_utils import get_logger

logger = get_logger("scheduled_task_routes")

router = APIRouter(prefix="/api/scheduled-task", tags=["scheduled-task"])


# ==================== SSE 进度推送 ====================

@router.get("/{task_id}/progress-stream")
async def scheduled_task_progress_stream(task_id: int):
    """SSE 进度推送 - 前端订阅此接口获取实时进度。"""

    await init_business_tables()

    # 检查任务是否存在
    task = await ScheduledTaskDAO.get_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"定时任务 {task_id} 不存在")

    async def event_generator():
        queue = get_scheduled_task_queue(task_id)

        # 发送初始状态
        yield f"data: {json.dumps({'type': 'init', 'data': {'task_id': task_id, 'name': task.name, 'status': task.status}})}\\n\\n"

        logger.info("sse_connected", task_id=task_id)

        while True:
            try:
                # 等待事件（超时30秒发送心跳）
                event = await asyncio.wait_for(queue.get(), timeout=30)
                yield f"data: {json.dumps(event)}\\n\\n"

                # 如果任务完成，结束 SSE
                if event.get("type") in ["done", "error"]:
                    logger.info("sse_completed", task_id=task_id)
                    break

            except asyncio.TimeoutError:
                # 发送心跳保持连接
                yield f"data: {json.dumps({'type': 'heartbeat', 'data': {'timestamp': datetime.now().isoformat()}})}\\n\\n"

            except Exception as e:
                logger.warning("sse_error", task_id=task_id, error=str(e))
                break

        # 清理队列
        remove_scheduled_task_queue(task_id)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ==================== 任务管理 ====================

@router.get("/list")
async def list_scheduled_tasks(
    target_type: Optional[str] = None,
    target_name: Optional[str] = None,
    status: Optional[str] = None
) -> Dict[str, Any]:
    """列出定时任务。"""
    await init_business_tables()

    tasks = await ScheduledTaskDAO.list_all(
        target_type=target_type,
        target_name=target_name,
        status=status
    )

    return {
        "code": 0,
        "data": {
            "count": len(tasks),
            "tasks": [
                {
                    "id": t.id,
                    "name": t.name,
                    "target": f"{t.target_type}:{t.target_name}",
                    "cron": t.cron_expression,
                    "dimensions": t.dimensions,
                    "prompt_preview": t.prompt[:100] if len(t.prompt) > 100 else t.prompt,
                    "status": t.status,
                    "enabled": t.enabled,
                    "created_by": t.created_by,
                    "last_run": t.last_run_at.isoformat() if t.last_run_at else None,
                    "last_status": t.last_run_status,
                    "next_run": t.next_run_at.isoformat() if t.next_run_at else None,
                    "run_count": t.run_count,
                    "created_at": t.created_at.isoformat() if t.created_at else None
                }
                for t in tasks
            ]
        }
    }


@router.get("/{task_id}")
async def get_scheduled_task(task_id: int) -> Dict[str, Any]:
    """获取任务详情。"""
    await init_business_tables()

    task = await ScheduledTaskDAO.get_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"定时任务 {task_id} 不存在")

    return {
        "code": 0,
        "data": {
            "id": task.id,
            "name": task.name,
            "description": task.description,
            "target_type": task.target_type,
            "target_name": task.target_name,
            "prompt": task.prompt,
            "cron_expression": task.cron_expression,
            "dimensions": task.dimensions,
            "alert_threshold": task.alert_threshold,
            "alert_channels": task.alert_channels,
            "alert_channel_ids": task.alert_channel_ids,
            "status": task.status,
            "enabled": task.enabled,
            "created_by": task.created_by,
            "conversation_id": task.conversation_id,
            "last_run_id": task.last_run_id,
            "last_run_at": task.last_run_at.isoformat() if task.last_run_at else None,
            "last_run_status": task.last_run_status,
            "next_run_at": task.next_run_at.isoformat() if task.next_run_at else None,
            "run_count": task.run_count,
            "created_at": task.created_at.isoformat() if task.created_at else None
        }
    }


@router.put("/{task_id}/alert-channels")
async def update_alert_channels(task_id: int, channels: Dict[str, Any]) -> Dict[str, Any]:
    """更新告警渠道配置。

    channels 格式:
    {
        "dingtalk": {"webhook": "https://oapi.dingtalk.com/...", "secret": "SECxxx"},
        "feishu": {"webhook": "https://open.feishu.cn/..."}
    }
    """
    await init_business_tables()

    task = await ScheduledTaskDAO.get_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"定时任务 {task_id} 不存在")

    # 更新 alert_channels
    success = await ScheduledTaskDAO.update(task_id, {"alert_channels": channels})
    if not success:
        raise HTTPException(status_code=500, detail="更新失败")

    return {
        "code": 0,
        "data": {
            "message": "告警渠道配置已更新",
            "task_id": task_id,
            "channels": channels
        }
    }


@router.get("/{task_id}/executions")
async def get_task_executions(task_id: int, limit: int = 20) -> Dict[str, Any]:
    """获取任务执行历史（简要列表）。"""
    await init_business_tables()

    task = await ScheduledTaskDAO.get_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"定时任务 {task_id} 不存在")

    executions = await ScheduledTaskExecutionDAO.list_by_task(task_id, limit)

    return {
        "code": 0,
        "data": {
            "task_id": task_id,
            "count": len(executions),
            "executions": [
                {
                    "id": e.id,
                    "run_id": e.run_id,
                    "scheduled_task_id": e.scheduled_task_id,  # 添加此字段用于 SSE 连接
                    "status": e.status,
                    "started_at": e.started_at.isoformat(),
                    "completed_at": e.completed_at.isoformat() if e.completed_at else None,
                    "duration_seconds": e.duration_seconds,
                    "total_findings": e.total_findings,
                    "high_severity_count": e.high_severity_count,
                    "error_message": e.error_message,
                    "steps": e.steps  # 保留简要步骤
                }
                for e in executions
            ]
        }
    }


@router.get("/executions/{run_id}")
async def get_execution_detail(run_id: str) -> Dict[str, Any]:
    """获取执行详情（完整数据：tool_calls、agent_output、execution_log）。"""
    await init_business_tables()

    execution = await ScheduledTaskExecutionDAO.get_by_run_id(run_id)
    if not execution:
        raise HTTPException(status_code=404, detail=f"执行记录 {run_id} 不存在")

    return {
        "code": 0,
        "data": {
            "id": execution.id,
            "run_id": execution.run_id,
            "scheduled_task_id": execution.scheduled_task_id,
            "status": execution.status,
            "started_at": execution.started_at.isoformat(),
            "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
            "duration_seconds": execution.duration_seconds,
            "total_findings": execution.total_findings,
            "high_severity_count": execution.high_severity_count,
            "error_message": execution.error_message,
            "error_detail": execution.error_detail,
            # 完整详情数据
            "steps": execution.steps,
            "tool_calls": execution.tool_calls,
            "agent_output": execution.agent_output,
            "execution_log": execution.execution_log,
        }
    }


@router.post("/{task_id}/pause")
async def pause_task(task_id: int) -> Dict[str, Any]:
    """暂停任务。"""
    await init_business_tables()

    success = await ScheduledTaskDAO.pause(task_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"定时任务 {task_id} 不存在")

    return {
        "code": 0,
        "data": {"message": f"任务 {task_id} 已暂停", "status": "paused"}
    }


@router.post("/{task_id}/resume")
async def resume_task(task_id: int) -> Dict[str, Any]:
    """恢复任务。"""
    await init_business_tables()

    success = await ScheduledTaskDAO.resume(task_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"定时任务 {task_id} 不存在")

    return {
        "code": 0,
        "data": {"message": f"任务 {task_id} 已恢复", "status": "active"}
    }


@router.delete("/{task_id}")
async def delete_task(task_id: int) -> Dict[str, Any]:
    """删除任务。"""
    await init_business_tables()

    success = await ScheduledTaskDAO.delete(task_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"定时任务 {task_id} 不存在")

    return {
        "code": 0,
        "data": {"message": f"任务 {task_id} 已删除"}
    }


# ==================== 手动触发 ====================

@router.post("/{task_id}/run")
async def trigger_task_now(task_id: int) -> Dict[str, Any]:
    """立即触发任务执行（测试用）。"""
    await init_business_tables()

    task = await ScheduledTaskDAO.get_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"定时任务 {task_id} 不存在")

    if task.status != "active":
        raise HTTPException(status_code=400, detail=f"任务状态为 {task.status}，无法执行")

    # 触发执行
    from app.scheduler import run_scheduled_task_safe

    # 后台执行（不等待结果）
    asyncio.create_task(run_scheduled_task_safe(task))

    logger.info("task_triggered_manually", task_id=task_id, task_name=task.name)

    return {
        "code": 0,
        "data": {
            "message": f"任务 {task_id} 已触发执行",
            "task_id": task_id,
            "task_name": task.name,
            "sse_url": f"/api/scheduled-task/{task_id}/progress-stream"
        }
    }