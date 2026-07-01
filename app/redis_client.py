"""Redis 客户端模块 - 分布式锁支持。

提供:
- 全局连接池管理
- 延迟初始化
- 异步关闭

使用 redis-py 5.0+ 的异步客户端。
"""

import os
from typing import Optional
import redis.asyncio as aioredis
from redis.asyncio import Redis, ConnectionPool
from app.log_utils import get_logger

logger = get_logger("redis_client")

# 全局 Redis 连接池
_redis_pool: Optional[ConnectionPool] = None
_redis_client: Optional[Redis] = None


async def get_redis_client() -> Redis:
    """获取 Redis 客户端（延迟初始化）。

    Returns:
        Redis 客户端实例

    Raises:
        ConnectionError: Redis 连接失败
    """
    global _redis_pool, _redis_client

    if _redis_client is None:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

        logger.info("redis_pool_creating", url=redis_url)

        try:
            # 创建连接池
            _redis_pool = ConnectionPool.from_url(
                redis_url,
                max_connections=10,
                decode_responses=True,  # 自动解码为字符串
                socket_timeout=5,
                socket_connect_timeout=5
            )

            # 创建客户端
            _redis_client = Redis(connection_pool=_redis_pool)

            # 测试连接
            await _redis_client.ping()
            logger.info("redis_pool_created", url=redis_url)

        except Exception as e:
            logger.error("redis_connection_failed", url=redis_url, error=str(e))
            # 清理失败的连接
            _redis_client = None
            if _redis_pool:
                await _redis_pool.disconnect()
                _redis_pool = None
            raise

    return _redis_client


async def close_redis_pool():
    """关闭 Redis 连接池。"""
    global _redis_pool, _redis_client

    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("redis_client_closed")

    if _redis_pool is not None:
        await _redis_pool.aclose()
        _redis_pool = None
        logger.info("redis_pool_closed")


def is_redis_available() -> bool:
    """检查 Redis 客户端是否已初始化且可用。

    Returns:
        True 如果 Redis 可用，False 否则
    """
    return _redis_client is not None


async def check_redis_health() -> dict:
    """检查 Redis 健康状态。

    Returns:
        健康状态信息
    """
    try:
        client = await get_redis_client()
        await client.ping()
        info = await client.info("server")
        return {
            "status": "ok",
            "redis_version": info.get("redis_version"),
            "connected_clients": info.get("connected_clients"),
            "used_memory_human": info.get("used_memory_human")
        }
    except Exception as e:
        logger.warning("redis_health_check_failed", error=str(e))
        return {
            "status": "error",
            "error": str(e)
        }