"""扫描任务 DAO。

保持静态方法调用方式以兼容旧代码。
"""

import aiomysql
from datetime import datetime
from typing import Optional, List, Dict
from app.database.base import get_db_pool, parse_json_field, to_json_str
from app.models import ScanTask


# scan_task 表字段顺序（用于 tuple 转 dict）
SCAN_TASK_FIELDS = [
    "id", "run_id", "scan_type", "org_name", "trigger_by", "status", "phase",
    "phase_progress", "scan_warnings", "total_repos", "scanned_repos", "findings_count",
    "alert_status", "alert_sent_at", "alert_findings_count", "alert_error",
    "paused_at", "resume_from_repo", "error_message", "started_at", "completed_at", "created_at"
]


class ScanTaskDAO:
    """扫描任务数据访问对象 - 使用静态方法保持兼容。"""

    @staticmethod
    def _row_to_scan_task(row) -> ScanTask:
        """将数据库行转换为 ScanTask 对象。"""
        if isinstance(row, tuple):
            row = dict(zip(SCAN_TASK_FIELDS, row))

        phase_progress = parse_json_field(row.get("phase_progress"), {})
        scan_warnings = parse_json_field(row.get("scan_warnings"), [])

        return ScanTask(
            id=row.get("id"),
            run_id=row.get("run_id"),
            scan_type=row.get("scan_type"),
            org_name=row.get("org_name"),
            trigger_by=row.get("trigger_by"),
            status=row.get("status"),
            phase=row.get("phase", "init"),
            phase_progress=phase_progress,
            scan_warnings=scan_warnings,
            total_repos=row.get("total_repos", 0),
            scanned_repos=row.get("scanned_repos", 0),
            findings_count=row.get("findings_count", 0),
            alert_status=row.get("alert_status"),
            alert_sent_at=row.get("alert_sent_at"),
            alert_findings_count=row.get("alert_findings_count", 0),
            alert_error=row.get("alert_error"),
            paused_at=row.get("paused_at"),
            resume_from_repo=row.get("resume_from_repo"),
            error_message=row.get("error_message"),
            started_at=row.get("started_at"),
            completed_at=row.get("completed_at"),
            created_at=row.get("created_at")
        )

    @staticmethod
    async def create(task: ScanTask) -> int:
        """创建扫描任务。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    INSERT INTO scan_task (run_id, scan_type, org_name, trigger_by, status, phase,
                                           phase_progress, scan_warnings, total_repos, scanned_repos,
                                           findings_count, started_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    task.run_id,
                    task.scan_type,
                    task.org_name,
                    task.trigger_by,
                    task.status,
                    task.phase or "init",
                    to_json_str(task.phase_progress or {}),
                    to_json_str(task.scan_warnings or []),
                    task.total_repos,
                    task.scanned_repos,
                    task.findings_count,
                    task.started_at or datetime.now()
                ))
                return cur.lastrowid

    @staticmethod
    async def get_by_run_id(run_id: str) -> Optional[ScanTask]:
        """根据 run_id 获取任务。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("SELECT * FROM scan_task WHERE run_id = %s", (run_id,))
                row = await cur.fetchone()
                return ScanTaskDAO._row_to_scan_task(row) if row else None

    @staticmethod
    async def get_by_id(id: int) -> Optional[ScanTask]:
        """根据 ID 获取任务。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("SELECT * FROM scan_task WHERE id = %s", (id,))
                row = await cur.fetchone()
                return ScanTaskDAO._row_to_scan_task(row) if row else None

    @staticmethod
    async def update_status(run_id: str, status: str,
                            scanned_repos: int = None, findings_count: int = None,
                            error_message: str = None) -> bool:
        """更新任务状态。"""
        updates = {"status": status}

        if scanned_repos is not None:
            updates["scanned_repos"] = scanned_repos
        if findings_count is not None:
            updates["findings_count"] = findings_count
        if error_message is not None:
            updates["error_message"] = error_message
        if status == "completed":
            updates["completed_at"] = datetime.now()

        fields = ", ".join(f"{k} = %s" for k in updates.keys())
        values = list(updates.values()) + [run_id]

        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(f"UPDATE scan_task SET {fields} WHERE run_id = %s", tuple(values))
                return cur.rowcount > 0

    @staticmethod
    async def update_phase(run_id: str, phase: str, phase_progress: Dict = None) -> bool:
        """更新扫描阶段和进度。"""
        updates = {"phase": phase}
        if phase_progress is not None:
            updates["phase_progress"] = to_json_str(phase_progress)

        fields = ", ".join(f"{k} = %s" for k in updates.keys())
        values = list(updates.values()) + [run_id]

        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(f"UPDATE scan_task SET {fields} WHERE run_id = %s", tuple(values))
                return cur.rowcount > 0

    @staticmethod
    async def add_warning(run_id: str, warning: Dict) -> bool:
        """添加警告信息。"""
        task = await ScanTaskDAO.get_by_run_id(run_id)
        if not task:
            return False

        warnings = task.scan_warnings or []
        warnings.append(warning)

        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE scan_task SET scan_warnings = %s WHERE run_id = %s",
                    (to_json_str(warnings), run_id)
                )
                return cur.rowcount > 0

    @staticmethod
    async def get_running_task_by_org(org_name: str) -> Optional[ScanTask]:
        """获取组织正在运行的任务。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT * FROM scan_task WHERE org_name = %s AND status IN ('running', 'pending', 'paused') ORDER BY created_at DESC LIMIT 1",
                    (org_name,)
                )
                row = await cur.fetchone()
                return ScanTaskDAO._row_to_scan_task(row) if row else None

    @staticmethod
    async def get_active_task_by_org(org_name: str) -> Optional[ScanTask]:
        """获取组织的活跃任务。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT * FROM scan_task WHERE org_name = %s AND status IN ('running', 'pending', 'paused', 'completed', 'failed') ORDER BY created_at DESC LIMIT 1",
                    (org_name,)
                )
                row = await cur.fetchone()
                return ScanTaskDAO._row_to_scan_task(row) if row else None

    @staticmethod
    async def list_recent(org_name: str = None, limit: int = 20) -> List[ScanTask]:
        """获取最近的任务列表。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                if org_name:
                    await cur.execute(
                        "SELECT * FROM scan_task WHERE org_name = %s ORDER BY created_at DESC LIMIT %s",
                        (org_name, limit)
                    )
                else:
                    await cur.execute(
                        "SELECT * FROM scan_task ORDER BY created_at DESC LIMIT %s",
                        (limit,)
                    )
                rows = await cur.fetchall()
                return [ScanTaskDAO._row_to_scan_task(row) for row in rows]

    @staticmethod
    async def pause(run_id: str, current_repo: str = None) -> bool:
        """暂停任务。

        Args:
            run_id: 任务 ID
            current_repo: 当前正在扫描的仓库（用于恢复）

        Returns:
            是否更新成功
        """
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    UPDATE scan_task
                    SET status = 'paused',
                        paused_at = %s,
                        resume_from_repo = %s
                    WHERE run_id = %s AND status = 'running'
                """, (datetime.now(), current_repo, run_id))
                return cur.rowcount > 0

    @staticmethod
    async def resume(run_id: str) -> bool:
        """恢复暂停的任务。

        Args:
            run_id: 任务 ID

        Returns:
            是否更新成功
        """
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    UPDATE scan_task
                    SET status = 'running',
                        paused_at = NULL
                    WHERE run_id = %s AND status = 'paused'
                """, (run_id,))
                return cur.rowcount > 0

    @staticmethod
    async def cancel(run_id: str, reason: str = None) -> bool:
        """取消任务。

        Args:
            run_id: 任务 ID
            reason: 取消原因

        Returns:
            是否更新成功
        """
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                if reason:
                    await cur.execute("""
                        UPDATE scan_task
                        SET status = 'cancelled',
                            error_message = %s,
                            completed_at = %s
                        WHERE run_id = %s AND status IN ('running', 'pending', 'paused')
                    """, (reason, datetime.now(), run_id))
                else:
                    await cur.execute("""
                        UPDATE scan_task
                        SET status = 'cancelled',
                            completed_at = %s
                        WHERE run_id = %s AND status IN ('running', 'pending', 'paused')
                    """, (datetime.now(), run_id))
                return cur.rowcount > 0

    @staticmethod
    async def force_reset(run_id: str) -> bool:
        """强制重置卡住的任务状态。

        用于处理服务异常终止导致任务状态异常的情况。

        Args:
            run_id: 任务 ID

        Returns:
            是否更新成功
        """
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    UPDATE scan_task
                    SET status = 'failed',
                        error_message = '任务被强制重置（服务异常终止）',
                        completed_at = %s
                    WHERE run_id = %s AND status = 'running'
                """, (datetime.now(), run_id))
                return cur.rowcount > 0

    @staticmethod
    async def reset_stuck_tasks(timeout_minutes: int = 30) -> int:
        """重置超时卡住的任务。

        Args:
            timeout_minutes: 超时分钟数

        Returns:
            重置的任务数量
        """
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 找出超过指定时间仍在 running 状态的任务
                await cur.execute("""
                    UPDATE scan_task
                    SET status = 'failed',
                        error_message = '任务超时自动重置',
                        completed_at = %s
                    WHERE status = 'running'
                      AND started_at < DATE_SUB(NOW(), INTERVAL %s MINUTE)
                """, (datetime.now(), timeout_minutes))
                return cur.rowcount

    @staticmethod
    async def update_alert_status(run_id: str, alert_status: str,
                                   alert_findings_count: int = None,
                                   alert_error: str = None) -> bool:
        """更新告警推送状态。

        Args:
            run_id: 任务运行ID
            alert_status: 告警状态: pending|sending|sent|skipped|failed
            alert_findings_count: 推送的发现数量
            alert_error: 告警发送错误信息

        Returns:
            是否更新成功
        """
        updates = {"alert_status": alert_status}

        if alert_status == "sent":
            updates["alert_sent_at"] = datetime.now()
        if alert_findings_count is not None:
            updates["alert_findings_count"] = alert_findings_count
        if alert_error is not None:
            updates["alert_error"] = alert_error

        fields = ", ".join(f"{k} = %s" for k in updates.keys())
        values = list(updates.values()) + [run_id]

        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(f"UPDATE scan_task SET {fields} WHERE run_id = %s", tuple(values))
                return cur.rowcount > 0