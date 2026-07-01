"""发现记录 DAO。

保持静态方法调用方式以兼容旧代码。
"""

import aiomysql
from datetime import datetime
from typing import Optional, List, Dict
from app.database.base import get_db_pool, parse_json_field, to_json_str
from app.models import Finding


# finding 表字段顺序（用于 tuple 转 dict）
FINDING_FIELDS = [
    "id", "repo_full_name", "finding_type", "severity", "title", "description",
    "detail", "is_acknowledged", "acknowledged_by", "acknowledged_at", "scan_task_id",
    "created_at", "updated_at"
]


class FindingDAO:
    """发现记录数据访问对象 - 使用静态方法保持兼容。"""

    @staticmethod
    def _row_to_finding(row) -> Finding:
        """将数据库行转换为 Finding 对象。"""
        if isinstance(row, tuple):
            row = dict(zip(FINDING_FIELDS, row))

        detail = parse_json_field(row.get("detail"), {})

        return Finding(
            id=row.get("id"),
            repo_full_name=row.get("repo_full_name"),
            finding_type=row.get("finding_type"),
            severity=row.get("severity"),
            title=row.get("title"),
            description=row.get("description"),
            detail=detail,
            is_acknowledged=row.get("is_acknowledged", False),
            acknowledged_by=row.get("acknowledged_by"),
            acknowledged_at=row.get("acknowledged_at"),
            scan_task_id=row.get("scan_task_id"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at")
        )

    @staticmethod
    async def create(finding: Finding) -> int:
        """创建单个发现记录。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    INSERT INTO finding (repo_full_name, finding_type, severity, title, description,
                                          detail, is_acknowledged, scan_task_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    finding.repo_full_name,
                    finding.finding_type,
                    finding.severity,
                    finding.title,
                    finding.description,
                    to_json_str(finding.detail),
                    finding.is_acknowledged,
                    finding.scan_task_id
                ))
                return cur.lastrowid

    @staticmethod
    async def batch_create(findings: List[Finding]) -> int:
        """批量创建发现记录。"""
        if not findings:
            return 0

        params_list = [
            (
                f.repo_full_name,
                f.finding_type,
                f.severity,
                f.title,
                f.description,
                to_json_str(f.detail),
                f.is_acknowledged,
                f.scan_task_id
            )
            for f in findings
        ]

        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.executemany("""
                    INSERT INTO finding (repo_full_name, finding_type, severity, title, description,
                                          detail, is_acknowledged, scan_task_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, params_list)
                return cur.rowcount

    @staticmethod
    async def query(repo_full_name: str = None, finding_type: str = None,
                    severity: str = None, is_acknowledged: bool = None,
                    scan_task_id: int = None, created_after: datetime = None,
                    page: int = 1, page_size: int = 50) -> List[Finding]:
        """多条件查询发现记录。"""
        conditions = []
        params = []

        if repo_full_name:
            conditions.append("repo_full_name = %s")
            params.append(repo_full_name)
        if finding_type:
            conditions.append("finding_type = %s")
            params.append(finding_type)
        if severity:
            conditions.append("severity = %s")
            params.append(severity)
        if is_acknowledged is not None:
            conditions.append("is_acknowledged = %s")
            params.append(is_acknowledged)
        if scan_task_id:
            conditions.append("scan_task_id = %s")
            params.append(scan_task_id)
        if created_after:
            conditions.append("created_at >= %s")
            params.append(created_after)

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        offset = (page - 1) * page_size

        sql = f"SELECT * FROM finding WHERE {where_clause} ORDER BY created_at DESC LIMIT %s OFFSET %s"
        params.extend([page_size, offset])

        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql, tuple(params))
                rows = await cur.fetchall()
                return [FindingDAO._row_to_finding(row) for row in rows]

    @staticmethod
    async def get_by_scan_task(scan_task_id: int) -> List[Finding]:
        """获取扫描任务的所有发现。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT * FROM finding WHERE scan_task_id = %s ORDER BY severity, created_at DESC",
                    (scan_task_id,)
                )
                rows = await cur.fetchall()
                return [FindingDAO._row_to_finding(row) for row in rows]

    @staticmethod
    async def get_by_scan_task_grouped(scan_task_id: int) -> Dict[str, List[Dict]]:
        """获取扫描任务的发现（按仓库分组）。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("""
                    SELECT id, repo_full_name, finding_type, severity, title, description, detail
                    FROM finding WHERE scan_task_id = %s ORDER BY severity DESC
                """, (scan_task_id,))
                rows = await cur.fetchall()

        result = {}
        for row in rows:
            repo = row.get("repo_full_name")
            if repo not in result:
                result[repo] = []
            result[repo].append({
                "id": row.get("id"),
                "finding_type": row.get("finding_type"),
                "severity": row.get("severity"),
                "title": row.get("title"),
                "description": row.get("description"),
                "detail": parse_json_field(row.get("detail"), {})
            })

        return result

    @staticmethod
    async def acknowledge(finding_id: int, acknowledged_by: str) -> bool:
        """标记发现为已确认。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    UPDATE finding SET is_acknowledged = TRUE, acknowledged_by = %s, acknowledged_at = NOW()
                    WHERE id = %s
                """, (acknowledged_by, finding_id))
                return cur.rowcount > 0

    @staticmethod
    async def count(repo_full_name: str = None, finding_type: str = None,
                    severity: str = None, is_acknowledged: bool = None,
                    scan_task_id: int = None, created_after: datetime = None) -> int:
        """多条件统计发现记录数量。"""
        conditions = []
        params = []

        if repo_full_name:
            conditions.append("repo_full_name = %s")
            params.append(repo_full_name)
        if finding_type:
            conditions.append("finding_type = %s")
            params.append(finding_type)
        if severity:
            conditions.append("severity = %s")
            params.append(severity)
        if is_acknowledged is not None:
            conditions.append("is_acknowledged = %s")
            params.append(is_acknowledged)
        if scan_task_id:
            conditions.append("scan_task_id = %s")
            params.append(scan_task_id)
        if created_after:
            conditions.append("created_at >= %s")
            params.append(created_after)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        sql = f"SELECT COUNT(*) as total FROM finding WHERE {where_clause}"

        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql, tuple(params))
                row = await cur.fetchone()
                return row.get("total", 0) if row else 0

    @staticmethod
    async def count_by_severity(scan_task_id: int = None) -> Dict[str, int]:
        """按严重程度统计数量。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                if scan_task_id:
                    await cur.execute(
                        "SELECT severity, COUNT(*) as count FROM finding WHERE scan_task_id = %s GROUP BY severity",
                        (scan_task_id,)
                    )
                else:
                    await cur.execute(
                        "SELECT severity, COUNT(*) as count FROM finding GROUP BY severity"
                    )
                rows = await cur.fetchall()

        return {row.get("severity"): row.get("count") for row in rows}