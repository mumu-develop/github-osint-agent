"""扫描子任务 DAO。

保持静态方法调用方式以兼容旧代码。
"""

import aiomysql
from datetime import datetime
from typing import Optional, List, Dict
from app.database.base import get_db_pool
from app.models import ScanSubTask


# scan_subtask 表字段顺序（用于 tuple 转 dict）
SCAN_SUBTASK_FIELDS = [
    "id", "scan_task_id", "repo_full_name", "status", "findings_count",
    "high_severity_count", "started_at", "completed_at", "error_message", "created_at"
]


class ScanSubTaskDAO:
    """扫描子任务数据访问对象 - 使用静态方法保持兼容。"""

    @staticmethod
    def _row_to_subtask(row) -> ScanSubTask:
        """将数据库行转换为 ScanSubTask 对象。"""
        if isinstance(row, tuple):
            row = dict(zip(SCAN_SUBTASK_FIELDS, row))

        return ScanSubTask(
            id=row.get("id"),
            scan_task_id=row.get("scan_task_id"),
            repo_full_name=row.get("repo_full_name"),
            status=row.get("status"),
            findings_count=row.get("findings_count", 0),
            high_severity_count=row.get("high_severity_count", 0),
            started_at=row.get("started_at"),
            completed_at=row.get("completed_at"),
            error_message=row.get("error_message"),
            created_at=row.get("created_at")
        )

    @staticmethod
    async def create(subtask: ScanSubTask) -> int:
        """创建单个子任务。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    INSERT INTO scan_subtask (scan_task_id, repo_full_name, status)
                    VALUES (%s, %s, %s)
                """, (subtask.scan_task_id, subtask.repo_full_name, subtask.status or "pending"))
                return cur.lastrowid

    @staticmethod
    async def batch_create(subtasks: List[ScanSubTask]) -> int:
        """批量创建子任务。"""
        if not subtasks:
            return 0

        params_list = [
            (st.scan_task_id, st.repo_full_name, st.status or "pending")
            for st in subtasks
        ]

        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.executemany("""
                    INSERT INTO scan_subtask (scan_task_id, repo_full_name, status)
                    VALUES (%s, %s, %s)
                """, params_list)
                return cur.rowcount

    @staticmethod
    async def finalize_remaining_subtasks(scan_task_id: int, status: str = "failed",
                                           error_message: str = None) -> int:
        """将所有未完成的子任务标记为指定状态。"""
        updates = {"status": status, "completed_at": datetime.now()}
        if error_message:
            updates["error_message"] = error_message

        fields = ", ".join(f"{k} = %s" for k in updates.keys())
        values = list(updates.values()) + [scan_task_id]

        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"UPDATE scan_subtask SET {fields} WHERE scan_task_id = %s AND status NOT IN ('completed', 'failed')",
                    tuple(values)
                )
                return cur.rowcount

    @staticmethod
    async def pause_all_by_task(scan_task_id: int) -> int:
        """暂停所有运行中的子任务。

        Args:
            scan_task_id: 扫描任务 ID

        Returns:
            暂停的子任务数量
        """
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    UPDATE scan_subtask
                    SET status = 'paused'
                    WHERE scan_task_id = %s AND status = 'running'
                """, (scan_task_id,))
                return cur.rowcount

    @staticmethod
    async def get_pending_subtasks(scan_task_id: int, limit: int = 100) -> List[ScanSubTask]:
        """获取待执行的子任务。

        Args:
            scan_task_id: 扫描任务 ID
            limit: 最大返回数量

        Returns:
            待执行的子任务列表
        """
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("""
                    SELECT * FROM scan_subtask
                    WHERE scan_task_id = %s AND status = 'pending'
                    ORDER BY id
                    LIMIT %s
                """, (scan_task_id, limit))
                rows = await cur.fetchall()
                return [ScanSubTaskDAO._row_to_subtask(row) for row in rows]

    @staticmethod
    async def get_running_subtask(scan_task_id: int) -> Optional[ScanSubTask]:
        """获取正在运行的子任务。

        Args:
            scan_task_id: 扫描任务 ID

        Returns:
            正在运行的子任务（如果有）
        """
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("""
                    SELECT * FROM scan_subtask
                    WHERE scan_task_id = %s AND status = 'running'
                    LIMIT 1
                """, (scan_task_id,))
                row = await cur.fetchone()
                return ScanSubTaskDAO._row_to_subtask(row) if row else None

    @staticmethod
    async def list_by_scan_task(scan_task_id: int, status: str = None) -> List[ScanSubTask]:
        """获取扫描任务的所有子任务。

        Args:
            scan_task_id: 扫描任务 ID
            status: 可选状态过滤

        Returns:
            子任务列表
        """
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                if status:
                    await cur.execute(
                        "SELECT * FROM scan_subtask WHERE scan_task_id = %s AND status = %s ORDER BY id",
                        (scan_task_id, status)
                    )
                else:
                    await cur.execute(
                        "SELECT * FROM scan_subtask WHERE scan_task_id = %s ORDER BY id",
                        (scan_task_id,)
                    )
                rows = await cur.fetchall()
                return [ScanSubTaskDAO._row_to_subtask(row) for row in rows]

    @staticmethod
    async def get_progress(scan_task_id: int) -> Dict:
        """获取扫描进度统计。

        Args:
            scan_task_id: 扫描任务 ID

        Returns:
            进度统计字典
        """
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("""
                    SELECT status, COUNT(*) as count, SUM(findings_count) as findings,
                           SUM(high_severity_count) as high_severity
                    FROM scan_subtask WHERE scan_task_id = %s
                    GROUP BY status
                """, (scan_task_id,))
                rows = await cur.fetchall()

        result = {
            "total": 0,
            "completed": 0,
            "running": 0,
            "pending": 0,
            "failed": 0,
            "paused": 0,
            "cancelled": 0,
            "total_findings": 0,
            "high_severity_count": 0
        }

        for row in rows:
            status = row.get("status")
            count = row.get("count", 0)
            findings = row.get("findings", 0) or 0
            high_severity = row.get("high_severity", 0) or 0

            result["total"] += count
            if status in result:
                result[status] = count
            result["total_findings"] += findings
            result["high_severity_count"] += high_severity

        return result

    @staticmethod
    async def update_status_by_repo(repo_full_name: str, scan_task_id: int,
                                     status: str, findings_count: int = None,
                                     high_severity_count: int = None,
                                     error_message: str = None) -> bool:
        """更新子任务状态。

        Args:
            repo_full_name: 仓库全名
            scan_task_id: 扫描任务 ID
            status: 新状态
            findings_count: 发现数量
            high_severity_count: 高危数量
            error_message: 错误信息

        Returns:
            是否更新成功
        """
        updates = {"status": status}

        if status == "running":
            updates["started_at"] = datetime.now()
        elif status in ["completed", "failed", "cancelled"]:
            updates["completed_at"] = datetime.now()

        if findings_count is not None:
            updates["findings_count"] = findings_count
        if high_severity_count is not None:
            updates["high_severity_count"] = high_severity_count
        if error_message is not None:
            updates["error_message"] = error_message

        fields = ", ".join(f"{k} = %s" for k in updates.keys())
        values = list(updates.values()) + [repo_full_name, scan_task_id]

        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"UPDATE scan_subtask SET {fields} WHERE repo_full_name = %s AND scan_task_id = %s",
                    tuple(values)
                )
                return cur.rowcount > 0