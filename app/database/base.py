"""数据库基础模块 - 连接管理和 BaseDAO。

提供:
- 全局连接池管理
- BaseDAO 抽象类（统一 CRUD 操作）
- JSON 字段解析工具
"""

import os
import json
import aiomysql
from typing import Optional, List, Dict, Any, TypeVar, Generic
from abc import ABC, abstractmethod
from app.log_utils import get_logger

logger = get_logger("database_base")

# 泛型类型
T = TypeVar("T")

# 全局数据库连接池
_db_pool: Optional[aiomysql.Pool] = None


async def get_db_pool() -> aiomysql.Pool:
    """获取数据库连接池（延迟初始化）。"""
    global _db_pool
    if _db_pool is None:
        mysql_host = os.getenv("MYSQL_HOST", "127.0.0.1")
        mysql_port = int(os.getenv("MYSQL_PORT", "3306"))
        mysql_user = os.getenv("MYSQL_USER", "root")
        mysql_password = os.getenv("MYSQL_PASSWORD", "123456")
        mysql_db = os.getenv("MYSQL_DB_NAME", "osint")

        logger.info("db_pool_creating", host=mysql_host, db=mysql_db)
        _db_pool = await aiomysql.create_pool(
            host=mysql_host,
            port=mysql_port,
            user=mysql_user,
            password=mysql_password,
            db=mysql_db,
            charset="utf8mb4",
            autocommit=True,
            minsize=5,
            maxsize=50,
        )
        logger.info("db_pool_created")
    return _db_pool


async def close_db_pool():
    """关闭数据库连接池。"""
    global _db_pool
    if _db_pool is not None:
        _db_pool.close()
        await _db_pool.wait_closed()
        _db_pool = None
        logger.info("db_pool_closed")


# ==================== JSON 字段工具 ====================

def parse_json_field(value: Any, default: Any = None) -> Any:
    """解析 JSON 字段（支持字符串和已解析的字典）。

    Args:
        value: 字段值（可能是字符串或已解析的对象）
        default: 默认值

    Returns:
        解析后的对象
    """
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def to_json_str(value: Any) -> Optional[str]:
    """转换为 JSON 字符串（用于存储）。

    Args:
        value: 对象值

    Returns:
        JSON 字符串，或 None
    """
    if value is None:
        return None
    return json.dumps(value)


# ==================== BaseDAO 抽象类 ====================

class BaseDAO(ABC, Generic[T]):
    """数据访问对象基类。

    提供统一的 CRUD 操作:
    - _execute: 执行 SQL
    - _query_one: 查询单条
    - _query_all: 查询多条
    - _row_to_model: 行转模型（子类实现）
    """

    @staticmethod
    async def _execute(sql: str, params: tuple = None) -> int:
        """执行 SQL 语句，返回影响行数或 lastrowid。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                return cur.lastrowid or cur.rowcount

    @staticmethod
    async def _execute_many(sql: str, params_list: List[tuple]) -> int:
        """批量执行 SQL 语句。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.executemany(sql, params_list)
                return cur.rowcount

    @staticmethod
    async def _query_one(sql: str, params: tuple = None) -> Optional[Dict]:
        """查询单条记录（返回字典）。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql, params)
                return await cur.fetchone()

    @staticmethod
    async def _query_all(sql: str, params: tuple = None, limit: int = None) -> List[Dict]:
        """查询多条记录（返回字典列表）。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                if limit:
                    sql += f" LIMIT {limit}"
                await cur.execute(sql, params)
                return await cur.fetchall()

    @staticmethod
    async def _query_count(sql: str, params: tuple = None) -> int:
        """查询计数。"""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                result = await cur.fetchone()
                return result[0] if result else 0

    @abstractmethod
    def _row_to_model(self, row: Dict) -> T:
        """将数据库行转换为模型对象（子类实现）。"""
        pass

    async def get_by_id(self, id: int) -> Optional[T]:
        """根据 ID 获取记录。"""
        row = await self._query_one(f"SELECT * FROM {self._table_name()} WHERE id = %s", (id,))
        if row:
            return self._row_to_model(row)
        return None

    async def list_all(self, limit: int = 100) -> List[T]:
        """获取所有记录。"""
        rows = await self._query_all(f"SELECT * FROM {self._table_name()} ORDER BY id DESC LIMIT %s", (limit,))
        return [self._row_to_model(row) for row in rows]

    async def count(self) -> int:
        """获取记录总数。"""
        return await self._query_count(f"SELECT COUNT(*) FROM {self._table_name()}")

    async def delete_by_id(self, id: int) -> bool:
        """根据 ID 删除记录。"""
        affected = await self._execute(f"DELETE FROM {self._table_name()} WHERE id = %s", (id,))
        return affected > 0

    @abstractmethod
    def _table_name(self) -> str:
        """返回表名（子类实现）。"""
        pass