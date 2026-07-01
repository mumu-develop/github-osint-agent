"""扫描历史 DAO。"""

import aiomysql
from app.database.base import get_db_pool, to_json_str, parse_json_field
from app.models import ScanHistory


class ScanHistoryDAO:
    """扫描历史数据访问对象。"""

    @staticmethod
    def _row_to_history(row: dict) -> ScanHistory:
        """将数据库行转换为 ScanHistory 对象。"""
        dimensions = parse_json_field(row.get("dimensions"))
        summary = parse_json_field(row.get("summary"))
        return ScanHistory(
            id=row.get("id"),
            org_name=row.get("org_name"),
            run_id=row.get("run_id"),
            scan_type=row.get("scan_type"),
            scan_mode=row.get("scan_mode"),
            trigger_by=row.get("trigger_by"),
            status=row.get("status"),
            total_repos=row.get("total_repos", 0),
            findings_count=row.get("findings_count", 0),
            high_severity_count=row.get("high_severity_count", 0),
            duration_seconds=row.get("duration_seconds", 0),
            success_rate=row.get("success_rate", 0.0),
            started_at=row.get("started_at"),
            completed_at=row.get("completed_at"),
            dimensions=dimensions,
            summary=summary,
            created_at=row.get("created_at")
        )

    @staticmethod
    async def get_by_org(org_name: str, limit: int = 10) -> list:
        """获取组织的扫描历史。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("""
                    SELECT * FROM scan_history WHERE org_name = %s
                    ORDER BY created_at DESC LIMIT %s
                """, (org_name, limit))
                rows = await cur.fetchall()
                return [ScanHistoryDAO._row_to_history(row) for row in rows]

    @staticmethod
    async def archive_from_task(task, dimensions=None, summary=None) -> int:
        """将扫描任务归档为历史记录。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    INSERT INTO scan_history (
                        org_name, run_id, scan_type, scan_mode, trigger_by, status,
                        total_repos, findings_count, high_severity_count,
                        duration_seconds, success_rate, started_at, completed_at,
                        dimensions, summary
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    task.org_name,
                    task.run_id,
                    task.scan_type,
                    task.scan_type.replace("HYBRID_", "").lower(),
                    task.trigger_by,
                    task.status,
                    task.total_repos,
                    task.findings_count,
                    0,
                    0,
                    0.0,
                    task.started_at,
                    task.completed_at,
                    to_json_str(dimensions),
                    to_json_str(summary)
                ))
                return cur.lastrowid

    @staticmethod
    async def create(history: ScanHistory) -> int:
        """创建扫描历史记录。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    INSERT INTO scan_history (
                        org_name, run_id, scan_type, scan_mode, trigger_by, status,
                        total_repos, findings_count, high_severity_count,
                        duration_seconds, success_rate, started_at, completed_at,
                        dimensions, summary
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    history.org_name,
                    history.run_id,
                    history.scan_type,
                    history.scan_mode,
                    history.trigger_by,
                    history.status,
                    history.total_repos,
                    history.findings_count,
                    history.high_severity_count,
                    history.duration_seconds,
                    history.success_rate,
                    history.started_at,
                    history.completed_at,
                    to_json_str(history.dimensions),
                    to_json_str(history.summary)
                ))
                return cur.lastrowid