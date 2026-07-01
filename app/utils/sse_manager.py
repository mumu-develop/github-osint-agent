"""SSE 连接管理模块。

管理流式对话连接数限制，防止资源耗尽。

配置环境变量：
- SSE_MAX_CONNECTIONS: 最大并发连接数，默认 500
- SSE_IDLE_TIMEOUT: 连接空闲超时（秒），默认 300
"""

import os
import asyncio
from typing import Optional
from app.log_utils import get_logger

logger = get_logger("sse_manager")

# 全局 SSE 连接计数器
_sse_semaphore: Optional[asyncio.Semaphore] = None
_sse_active_count: int = 0


def get_sse_semaphore() -> asyncio.Semaphore:
    """获取 SSE 连接信号量。

    Returns:
        asyncio.Semaphore 实例
    """
    global _sse_semaphore
    if _sse_semaphore is None:
        max_connections = int(os.getenv("SSE_MAX_CONNECTIONS", "500"))
        _sse_semaphore = asyncio.Semaphore(max_connections)
        logger.info("sse_semaphore_created", max_connections=max_connections)
    return _sse_semaphore


def get_sse_active_count() -> int:
    """获取当前活跃 SSE 连接数。

    Returns:
        活跃连接数
    """
    return _sse_active_count


async def acquire_sse_connection(session_id: str) -> bool:
    """申请 SSE 连接槽位。

    Args:
        session_id: 会话 ID

    Returns:
        是否成功获取槽位
    """
    semaphore = get_sse_semaphore()
    try:
        # 尝试获取槽位（不阻塞，立即返回）
        acquired = semaphore.locked() is False
        if acquired:
            await semaphore.acquire()
            global _sse_active_count
            _sse_active_count += 1
            logger.info("sse_connection_acquired",
                       session_id=session_id,
                       active_count=_sse_active_count,
                       available=semaphore._value)
            return True
        else:
            logger.warning("sse_connection_limit_reached",
                          session_id=session_id,
                          active_count=_sse_active_count)
            return False
    except Exception as e:
        logger.error("sse_acquire_error", session_id=session_id, error=str(e))
        return False


async def release_sse_connection(session_id: str) -> None:
    """释放 SSE 连接槽位。

    Args:
        session_id: 会话 ID
    """
    semaphore = get_sse_semaphore()
    try:
        semaphore.release()
        global _sse_active_count
        _sse_active_count -= 1
        logger.info("sse_connection_released",
                   session_id=session_id,
                   active_count=_sse_active_count,
                   available=semaphore._value)
    except Exception as e:
        logger.warning("sse_release_error", session_id=session_id, error=str(e))


def get_sse_stats() -> dict:
    """获取 SSE 连接统计信息。

    Returns:
        统计信息字典
    """
    semaphore = get_sse_semaphore()
    max_connections = int(os.getenv("SSE_MAX_CONNECTIONS", "500"))
    return {
        "active_connections": _sse_active_count,
        "max_connections": max_connections,
        "available_slots": semaphore._value,
        "utilization": _sse_active_count / max_connections if max_connections > 0 else 0,
    }