"""扫描器 API 路由。"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Dict, Any
from datetime import datetime
import aiomysql
from app.models import ScanTriggerRequest, ScanTask
from app.database import ScanTaskDAO, ScanSubTaskDAO, init_business_tables, get_db_pool
from app.scheduler import get_scheduler
from app.log_utils import get_logger

logger = get_logger("scanner_routes")

router = APIRouter(prefix="/api/scanner", tags=["scanner"])


@router.post("/trigger")
async def trigger_scan(request: ScanTriggerRequest, background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """触发扫描任务。

    Args:
        scan_type: L1_LIGHT|L2_STANDARD|L3_DEEP|MANUAL
        org_name: 目标组织名称（可选，不填则扫描所有）
    """
    logger.info("scan_triggered", scan_type=request.scan_type, org=request.org_name)

    # 初始化业务表
    await init_business_tables()

    # 创建扫描任务记录
    run_id = f"SCAN_{request.org_name or 'ALL'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    task = ScanTask(
        run_id=run_id,
        scan_type=request.scan_type,
        org_name=request.org_name,
        trigger_by="manual",
        status="pending"
    )
    task_id = await ScanTaskDAO.create(task)

    # 后台执行扫描
    async def run_scan():
        scheduler = get_scheduler()
        result = await scheduler.trigger_manual_scan(request.scan_type, request.org_name)
        logger.info("scan_completed", run_id=run_id, result=result)

    background_tasks.add_task(run_scan)

    return {
        "code": 0,
        "data": {
            "run_id": run_id,
            "task_id": task_id,
            "scan_type": request.scan_type,
            "org_name": request.org_name,
            "status": "pending",
            "message": "扫描任务已提交，请通过 /api/scanner/status/{run_id} 查询进度"
        }
    }


@router.get("/status/{run_id}")
async def get_scan_status(run_id: str) -> Dict[str, Any]:
    """查询扫描任务状态。"""
    task = await ScanTaskDAO.get_by_run_id(run_id)

    if not task:
        raise HTTPException(status_code=404, detail=f"扫描任务 {run_id} 不存在")

    return {
        "code": 0,
        "data": {
            "run_id": task.run_id,
            "scan_type": task.scan_type,
            "org_name": task.org_name,
            "status": task.status,
            "total_repos": task.total_repos,
            "scanned_repos": task.scanned_repos,
            "findings_count": task.findings_count,
            "error_message": task.error_message,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "created_at": task.created_at.isoformat() if task.created_at else None
        }
    }


@router.get("/list")
async def list_scan_tasks(page: int = 1, page_size: int = 20, status: str = None) -> Dict[str, Any]:
    """列出扫描任务历史。"""
    await init_business_tables()

    # 查询扫描任务
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            where_clause = "WHERE status = %s" if status else ""
            params = [status] if status else []
            offset = (page - 1) * page_size

            await cur.execute(f"""
                SELECT * FROM scan_task {where_clause}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """, params + [page_size, offset])
            tasks = await cur.fetchall()

            count_params = params if params else []
            await cur.execute(f"SELECT COUNT(*) as cnt FROM scan_task {where_clause}", count_params)
            total_row = await cur.fetchone()
            total = total_row["cnt"] if total_row else 0

    return {
        "code": 0,
        "data": {
            "tasks": [
                {
                    "id": t["id"],
                    "run_id": t["run_id"],
                    "scan_type": t["scan_type"],
                    "org_name": t["org_name"],
                    "trigger_by": t["trigger_by"],
                    "status": t["status"],
                    "total_repos": t["total_repos"],
                    "scanned_repos": t["scanned_repos"],
                    "findings_count": t["findings_count"],
                    "error_message": t["error_message"],
                    "started_at": t["started_at"].isoformat() if t["started_at"] else None,
                    "completed_at": t["completed_at"].isoformat() if t["completed_at"] else None,
                    "created_at": t["created_at"].isoformat() if t["created_at"] else None
                }
                for t in tasks
            ],
            "page": page,
            "page_size": page_size,
            "total": total
        }
    }


@router.get("/health")
async def scanner_health() -> Dict[str, Any]:
    """扫描器健康检查。"""
    scheduler = get_scheduler()
    jobs = scheduler.scheduler.get_jobs() if scheduler.scheduler.running else []

    return {
        "code": 0,
        "data": {
            "scheduler_running": scheduler.scheduler.running,
            "scheduled_jobs": [
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run": job.next_run_time.isoformat() if job.next_run_time else None
                }
                for job in jobs
            ]
        }
    }


# ==================== 任务控制（暂停/恢复） ====================

@router.post("/pause/{run_id}")
async def pause_scan(run_id: str) -> Dict[str, Any]:
    """暂停扫描任务。"""
    await init_business_tables()

    task = await ScanTaskDAO.get_by_run_id(run_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"扫描任务 {run_id} 不存在")

    if task.status != "running":
        raise HTTPException(status_code=400, detail=f"任务状态为 {task.status}，无法暂停")

    # 暂停主任务
    success = await ScanTaskDAO.pause(run_id)

    # 暂停所有运行中的子任务
    paused_subtasks = await ScanSubTaskDAO.pause_all_by_task(task.id)

    if success:
        logger.info("scan_paused", run_id=run_id, paused_subtasks=paused_subtasks)

        # 获取当前进度
        progress = await ScanSubTaskDAO.get_progress(task.id)

        return {
            "code": 0,
            "data": {
                "message": f"扫描任务 {run_id} 已暂停",
                "status": "paused",
                "scanned_repos": task.scanned_repos,
                "total_repos": task.total_repos,
                "paused_subtasks": paused_subtasks,
                "progress": progress
            }
        }
    else:
        raise HTTPException(status_code=500, detail="暂停失败")


@router.post("/resume/{run_id}")
async def resume_scan(run_id: str, background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """恢复扫描任务。"""
    await init_business_tables()

    task = await ScanTaskDAO.get_by_run_id(run_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"扫描任务 {run_id} 不存在")

    if task.status != "paused":
        raise HTTPException(status_code=400, detail=f"任务状态为 {task.status}，无法恢复")

    # 获取待执行的子任务数量
    pending_subtasks = await ScanSubTaskDAO.get_pending_subtasks(task.id, limit=100)
    pending_count = len(pending_subtasks)

    logger.info("scan_resumed", run_id=run_id, pending_subtasks=pending_count)

    # 后台继续执行扫描
    async def continue_scan():
        try:
            # 根据任务的 scan_type 选择恢复方式
            if task.scan_type and "FAST" in task.scan_type.upper():
                # fast 模式用 ScanOrchestrator 恢复
                from app.scanner.scan_orchestrator import ScanOrchestrator
                orchestrator = ScanOrchestrator()
                result = await orchestrator.resume_fast_scan(run_id, task.org_name)
                logger.info("fast_scan_resume_result", run_id=run_id, result=result)
            else:
                # balanced/deep 模式用 HybridScanner 恢复
                from app.scanner.hybrid_scanner import HybridScanner
                scanner = HybridScanner(scan_mode="balanced")
                result = await scanner.resume_scan(run_id)
                await scanner.close()
                logger.info("scan_resume_result", run_id=run_id, result=result)
        except Exception as e:
            logger.error("scan_resume_error", run_id=run_id, error=str(e))

    background_tasks.add_task(continue_scan)

    return {
        "code": 0,
        "data": {
            "message": f"扫描任务 {run_id} 已恢复",
            "status": "running",
            "pending_subtasks": pending_count
        }
    }


# ==================== 子任务进度 ====================

@router.get("/subtasks/{run_id}")
async def get_subtask_progress(run_id: str, status: str = None) -> Dict[str, Any]:
    """获取扫描任务的子任务进度（仓库级详情）。"""
    await init_business_tables()

    task = await ScanTaskDAO.get_by_run_id(run_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"扫描任务 {run_id} 不存在")

    subtasks = await ScanSubTaskDAO.list_by_scan_task(task.id, status)

    return {
        "code": 0,
        "data": {
            "run_id": run_id,
            "task_status": task.status,
            "subtasks": [
                {
                    "id": st.id,
                    "repo_full_name": st.repo_full_name,
                    "status": st.status,
                    "findings_count": st.findings_count,
                    "high_severity_count": st.high_severity_count,
                    "started_at": st.started_at.isoformat() if st.started_at else None,
                    "completed_at": st.completed_at.isoformat() if st.completed_at else None,
                    "error_message": st.error_message
                }
                for st in subtasks
            ],
            "total": len(subtasks)
        }
    }


@router.get("/progress/{run_id}")
async def get_scan_progress(run_id: str) -> Dict[str, Any]:
    """获取扫描任务进度统计。"""
    await init_business_tables()

    task = await ScanTaskDAO.get_by_run_id(run_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"扫描任务 {run_id} 不存在")

    progress = await ScanSubTaskDAO.get_progress(task.id)

    # 计算百分比
    total = sum(progress.values()) - progress["total_findings"] - progress["high_severity_count"]
    if total > 0:
        percent = int(progress["completed"] / total * 100)
    else:
        percent = 0

    return {
        "code": 0,
        "data": {
            "run_id": run_id,
            "task_status": task.status,
            "total_repos": task.total_repos,
            "progress": progress,
            "percent": percent,
            "findings": {
                "total": progress["total_findings"],
                "high_severity": progress["high_severity_count"]
            }
        }
    }


@router.get("/running-repo/{run_id}")
async def get_current_running_repo(run_id: str) -> Dict[str, Any]:
    """获取当前正在扫描的仓库。"""
    await init_business_tables()

    task = await ScanTaskDAO.get_by_run_id(run_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"扫描任务 {run_id} 不存在")

    running_subtask = await ScanSubTaskDAO.get_running_subtask(task.id)

    if running_subtask:
        return {
            "code": 0,
            "data": {
                "run_id": run_id,
                "current_repo": running_subtask.repo_full_name,
                "started_at": running_subtask.started_at.isoformat() if running_subtask.started_at else None
            }
        }
    else:
        return {
            "code": 0,
            "data": {
                "run_id": run_id,
                "current_repo": None,
                "message": "当前没有正在扫描的仓库"
            }
        }


@router.post("/cancel/{run_id}")
async def cancel_scan(run_id: str, reason: str = "用户取消") -> Dict[str, Any]:
    """取消扫描任务。"""
    await init_business_tables()

    task = await ScanTaskDAO.get_by_run_id(run_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"扫描任务 {run_id} 不存在")

    if task.status not in ["running", "pending", "paused"]:
        raise HTTPException(status_code=400, detail=f"任务状态为 {task.status}，无法取消")

    # 取消主任务
    success = await ScanTaskDAO.cancel(run_id, reason)

    # 将所有未完成的子任务标记为取消
    cancelled_subtasks = await ScanSubTaskDAO.finalize_remaining_subtasks(
        task.id, status="cancelled", error_message=reason
    )

    if success:
        logger.info("scan_cancelled", run_id=run_id, cancelled_subtasks=cancelled_subtasks)

        return {
            "code": 0,
            "data": {
                "message": f"扫描任务 {run_id} 已取消",
                "status": "cancelled",
                "cancelled_subtasks": cancelled_subtasks
            }
        }
    else:
        raise HTTPException(status_code=500, detail="取消失败")


@router.post("/force-reset/{run_id}")
async def force_reset_scan(run_id: str) -> Dict[str, Any]:
    """强制重置卡住的任务。

    用于处理服务异常终止导致任务状态异常的情况。
    """
    await init_business_tables()

    task = await ScanTaskDAO.get_by_run_id(run_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"扫描任务 {run_id} 不存在")

    if task.status != "running":
        raise HTTPException(status_code=400, detail=f"任务状态为 {task.status}，无需重置（仅支持 running 状态）")

    # 强制重置主任务
    success = await ScanTaskDAO.force_reset(run_id)

    # 将所有未完成的子任务标记为失败
    reset_subtasks = await ScanSubTaskDAO.finalize_remaining_subtasks(
        task.id, status="failed", error_message="任务被强制重置（服务异常终止）"
    )

    if success:
        logger.info("scan_force_reset", run_id=run_id, reset_subtasks=reset_subtasks)

        return {
            "code": 0,
            "data": {
                "message": f"扫描任务 {run_id} 已强制重置为失败状态",
                "status": "failed",
                "reset_subtasks": reset_subtasks,
                "note": "任务已被标记为失败，可以重新触发新任务"
            }
        }
    else:
        raise HTTPException(status_code=500, detail="重置失败")


@router.post("/reset-stuck")
async def reset_stuck_tasks(timeout_minutes: int = 30) -> Dict[str, Any]:
    """批量重置超时卡住的任务。

    Args:
        timeout_minutes: 超时分钟数，默认 30 分钟
    """
    await init_business_tables()

    reset_count = await ScanTaskDAO.reset_stuck_tasks(timeout_minutes)

    logger.info("stuck_tasks_reset", count=reset_count, timeout_minutes=timeout_minutes)

    return {
        "code": 0,
        "data": {
            "message": f"已重置 {reset_count} 个超时任务",
            "reset_count": reset_count,
            "timeout_minutes": timeout_minutes
        }
    }