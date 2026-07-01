"""扫描报告 DAO。"""

import aiomysql
from app.database.base import get_db_pool, parse_json_field, to_json_str
from app.models import ScanReport


class ScanReportDAO:
    """扫描报告数据访问对象。"""

    @staticmethod
    def _row_to_report(row: dict) -> ScanReport:
        """将数据库行转换为 ScanReport 对象。"""
        recommendations = parse_json_field(row.get("recommendations"), [])
        return ScanReport(
            id=row.get("id"),
            scan_task_id=row.get("scan_task_id"),
            report_type=row.get("report_type"),
            title=row.get("title"),
            content=row.get("content"),
            summary=row.get("summary"),
            recommendations=recommendations,
            created_at=row.get("created_at")
        )

    @staticmethod
    async def create(report: ScanReport) -> int:
        """创建扫描报告。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    INSERT INTO scan_report (scan_task_id, report_type, title, content, summary, recommendations)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    report.scan_task_id,
                    report.report_type,
                    report.title,
                    report.content,
                    report.summary,
                    to_json_str(report.recommendations or [])
                ))
                return cur.lastrowid

    @staticmethod
    async def get_by_scan_task(scan_task_id: int) -> list:
        """获取扫描任务的报告列表。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("""
                    SELECT * FROM scan_report WHERE scan_task_id = %s
                    ORDER BY created_at DESC
                """, (scan_task_id,))
                rows = await cur.fetchall()
                return [ScanReportDAO._row_to_report(row) for row in rows]