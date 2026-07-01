"""告警渠道 DAO - 告警渠道配置数据访问层。"""

import aiomysql
from datetime import datetime
from typing import List, Optional, Dict, Any
from app.database.base import get_db_pool, parse_json_field, to_json_str, get_logger
from app.models import AlertChannel

logger = get_logger("alert_channel_dao")


class AlertChannelDAO:
    """告警渠道 DAO。"""

    @staticmethod
    async def create(channel_data: Dict[str, Any]) -> int:
        """创建告警渠道。

        Args:
            channel_data: 渠道数据字典

        Returns:
            渠道 ID
        """
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    INSERT INTO alert_channel (
                        name, channel_type, webhook_url, secret, description, enabled
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    channel_data.get("name"),
                    channel_data.get("channel_type"),
                    channel_data.get("webhook_url"),
                    channel_data.get("secret"),
                    channel_data.get("description"),
                    channel_data.get("enabled", True),
                ))
                channel_id = cur.lastrowid
                logger.info("alert_channel_created", channel_id=channel_id, name=channel_data.get("name"))
                return channel_id

    @staticmethod
    async def get_by_id(channel_id: int) -> Optional[AlertChannel]:
        """根据 ID 获取渠道。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("""
                    SELECT * FROM alert_channel WHERE id = %s
                """, (channel_id,))
                row = await cur.fetchone()
                if row:
                    return AlertChannel(
                        id=row["id"],
                        name=row["name"],
                        channel_type=row["channel_type"],
                        webhook_url=row["webhook_url"],
                        secret=row["secret"],
                        description=row["description"],
                        enabled=row["enabled"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                    )
                return None

    @staticmethod
    async def get_by_ids(channel_ids: List[int]) -> List[AlertChannel]:
        """根据 ID 列表获取多个渠道。"""
        if not channel_ids:
            return []

        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("""
                    SELECT * FROM alert_channel WHERE id IN (%s) AND enabled = TRUE
                """ % ",".join(str(id) for id in channel_ids))
                rows = await cur.fetchall()
                return [
                    AlertChannel(
                        id=row["id"],
                        name=row["name"],
                        channel_type=row["channel_type"],
                        webhook_url=row["webhook_url"],
                        secret=row["secret"],
                        description=row["description"],
                        enabled=row["enabled"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                    )
                    for row in rows
                ]

    @staticmethod
    async def list_all(channel_type: Optional[str] = None) -> List[AlertChannel]:
        """获取渠道列表（支持筛选）。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                if channel_type:
                    await cur.execute("""
                        SELECT * FROM alert_channel WHERE channel_type = %s
                        ORDER BY created_at DESC
                    """, (channel_type,))
                else:
                    await cur.execute("""
                        SELECT * FROM alert_channel ORDER BY created_at DESC
                    """)
                rows = await cur.fetchall()
                return [
                    AlertChannel(
                        id=row["id"],
                        name=row["name"],
                        channel_type=row["channel_type"],
                        webhook_url=row["webhook_url"],
                        secret=row["secret"],
                        description=row["description"],
                        enabled=row["enabled"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                    )
                    for row in rows
                ]

    @staticmethod
    async def list_enabled() -> List[AlertChannel]:
        """获取所有启用的渠道。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("""
                    SELECT * FROM alert_channel WHERE enabled = TRUE
                    ORDER BY name ASC
                """)
                rows = await cur.fetchall()
                return [
                    AlertChannel(
                        id=row["id"],
                        name=row["name"],
                        channel_type=row["channel_type"],
                        webhook_url=row["webhook_url"],
                        secret=row["secret"],
                        description=row["description"],
                        enabled=row["enabled"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                    )
                    for row in rows
                ]

    @staticmethod
    async def update(channel_id: int, updates: Dict[str, Any]) -> bool:
        """更新渠道。"""
        if not updates:
            return False

        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                set_clauses = []
                params = []

                for key, value in updates.items():
                    set_clauses.append(f"{key} = %s")
                    params.append(value)

                params.append(channel_id)
                await cur.execute(f"""
                    UPDATE alert_channel SET {', '.join(set_clauses)} WHERE id = %s
                """, params)
                logger.info("alert_channel_updated", channel_id=channel_id, updates=list(updates.keys()))
                return cur.rowcount > 0

    @staticmethod
    async def delete(channel_id: int) -> bool:
        """删除渠道。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM alert_channel WHERE id = %s", (channel_id,))
                logger.info("alert_channel_deleted", channel_id=channel_id)
                return cur.rowcount > 0

    @staticmethod
    async def enable(channel_id: int) -> bool:
        """启用渠道。"""
        return await AlertChannelDAO.update(channel_id, {"enabled": True})

    @staticmethod
    async def disable(channel_id: int) -> bool:
        """禁用渠道。"""
        return await AlertChannelDAO.update(channel_id, {"enabled": False})