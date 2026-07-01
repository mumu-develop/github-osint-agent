"""分布式锁服务 - 基于 Redis 实现原子性互斥控制。

功能:
- acquire_lock: 加锁（SET NX EX）
- release_lock: 释放锁（Lua 脚本保证原子性）
- get_lock_info: 查询锁信息
- 锁自动过期（防死锁）

设计细节:
- 锁 Key 格式: lock:scan:{org_name}
- 锁 Value: {run_id}:{timestamp}:{trigger_by}
- 锁过期时间: 默认 3600 秒（可通过环境变量配置）
"""

import os
import time
from typing import Optional, Dict, Any
from app.log_utils import get_logger
from app.redis_client import get_redis_client, is_redis_available

logger = get_logger("scan_lock")

# Lua 脱脚本：原子释放锁（只有持有者才能释放）
RELEASE_LOCK_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


class ScanLockService:
    """扫描分布式锁服务。

    使用 Redis SET NX EX 实现分布式锁，防止多实例重复扫描。
    """

    # 锁 Key 前缀
    LOCK_PREFIX = "lock:scan"

    # 默认锁过期时间（秒）
    DEFAULT_TIMEOUT = 3600

    def __init__(self, timeout: int = None):
        """初始化锁服务。

        Args:
            timeout: 锁过期时间（秒），默认从环境变量读取或 3600
        """
        self.timeout = timeout or int(os.getenv("REDIS_LOCK_TIMEOUT", self.DEFAULT_TIMEOUT))
        self._redis = None
        self._script_sha = None

    async def _get_redis(self):
        """获取 Redis 客户端（懒加载）。"""
        if self._redis is None:
            self._redis = await get_redis_client()
        return self._redis

    async def _load_script(self) -> str:
        """加载 Lua 脚本并返回 SHA。"""
        if self._script_sha is None:
            redis = await self._get_redis()
            self._script_sha = await redis.script_load(RELEASE_LOCK_SCRIPT)
            logger.debug("lock_script_loaded", sha=self._script_sha)
        return self._script_sha

    def _make_lock_key(self, org_name: str) -> str:
        """生成锁 Key。

        Args:
            org_name: 组织名称

        Returns:
            锁 Key 字符串
        """
        return f"{self.LOCK_PREFIX}:{org_name}"

    def _make_lock_value(self, run_id: str, trigger_by: str = "manual") -> str:
        """生成锁 Value。

        Args:
            run_id: 扫描任务 ID
            trigger_by: 触发方式

        Returns:
            锁 Value 字符串
        """
        timestamp = int(time.time())
        return f"{run_id}:{timestamp}:{trigger_by}"

    async def acquire_lock(self, org_name: str, run_id: str,
                           trigger_by: str = "manual") -> bool:
        """获取分布式锁。

        使用 Redis SET NX EX 原子操作：
        - NX: 仅当 Key 不存在时设置
        - EX: 设置过期时间

        Args:
            org_name: 组织名称
            run_id: 扫描任务 ID
            trigger_by: 触发方式（manual/scheduler）

        Returns:
            True 如果成功获取锁，False 如果锁已存在
        """
        # 检查 Redis 是否可用
        if not is_redis_available():
            try:
                await self._get_redis()
            except Exception as e:
                logger.warning("redis_unavailable_fallback_to_db",
                               org=org_name, error=str(e))
                # Redis 不可用时，回退到数据库检查（不使用分布式锁）
                return True  # 允许继续，依赖数据库幂等性检查

        lock_key = self._make_lock_key(org_name)
        lock_value = self._make_lock_value(run_id, trigger_by)

        try:
            redis = await self._get_redis()

            # SET NX EX - 原子加锁
            acquired = await redis.set(lock_key, lock_value, nx=True, ex=self.timeout)

            if acquired:
                logger.info("lock_acquired",
                           org=org_name,
                           run_id=run_id,
                           lock_key=lock_key,
                           timeout=self.timeout)
                return True
            else:
                # 锁已存在，获取当前锁信息用于日志
                current_value = await redis.get(lock_key)
                logger.warning("lock_acquire_failed",
                              org=org_name,
                              run_id=run_id,
                              lock_key=lock_key,
                              current_lock=current_value)
                return False

        except Exception as e:
            logger.error("lock_acquire_error",
                        org=org_name,
                        run_id=run_id,
                        error=str(e))
            # Redis 操作失败，回退到数据库检查
            return True

    async def release_lock(self, org_name: str, run_id: str = None) -> bool:
        """释放分布式锁。

        使用 Lua 脚本保证原子性：只有锁的持有者才能释放。

        Args:
            org_name: 组织名称
            run_id: 扫描任务 ID（用于验证锁持有者）

        Returns:
            True 如果成功释放锁，False 如果锁不存在或不属于当前持有者
        """
        # Redis 不可用时无需释放
        if not is_redis_available():
            logger.debug("redis_unavailable_skip_release", org=org_name)
            return True

        lock_key = self._make_lock_key(org_name)

        try:
            redis = await self._get_redis()

            # 获取当前锁值（用于释放验证）
            current_value = await redis.get(lock_key)

            if not current_value:
                logger.info("lock_not_found", org=org_name, lock_key=lock_key)
                return True

            # 如果指定了 run_id，验证锁持有者
            if run_id:
                expected_prefix = f"{run_id}:"
                if not current_value.startswith(expected_prefix):
                    logger.warning("lock_not_owner",
                                  org=org_name,
                                  run_id=run_id,
                                  current_lock=current_value)
                    return False

            # 使用 Lua 脚本原子释放
            script_sha = await self._load_script()
            released = await redis.evalsha(script_sha, 1, lock_key, current_value)

            if released:
                logger.info("lock_released",
                           org=org_name,
                           run_id=run_id,
                           lock_key=lock_key)
                return True
            else:
                logger.warning("lock_release_failed",
                              org=org_name,
                              run_id=run_id,
                              lock_key=lock_key)
                return False

        except Exception as e:
            logger.error("lock_release_error",
                        org=org_name,
                        run_id=run_id,
                        error=str(e))
            return False

    async def get_lock_info(self, org_name: str) -> Optional[Dict[str, Any]]:
        """获取锁信息（用于调试和监控）。

        Args:
            org_name: 组织名称

        Returns:
            锁信息字典，包含 run_id、timestamp、trigger_by、ttl
            如果锁不存在则返回 None
        """
        # Redis 不可用时返回 None
        if not is_redis_available():
            return None

        lock_key = self._make_lock_key(org_name)

        try:
            redis = await self._get_redis()

            # 获取锁值
            value = await redis.get(lock_key)
            if not value:
                return None

            # 获取剩余 TTL
            ttl = await redis.ttl(lock_key)

            # 解析锁值
            parts = value.split(":")
            if len(parts) >= 3:
                run_id = parts[0]
                timestamp = int(parts[1])
                trigger_by = parts[2]
            else:
                run_id = value
                timestamp = 0
                trigger_by = "unknown"

            return {
                "lock_key": lock_key,
                "run_id": run_id,
                "timestamp": timestamp,
                "trigger_by": trigger_by,
                "ttl": ttl,
                "value": value,
                "acquired_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))
            }

        except Exception as e:
            logger.error("lock_info_error", org=org_name, error=str(e))
            return None

    async def extend_lock(self, org_name: str, additional_seconds: int = 1800) -> bool:
        """延长锁的过期时间。

        用于长时间扫描任务，防止锁提前过期。

        Args:
            org_name: 组织名称
            additional_seconds: 额外的秒数

        Returns:
            True 如果成功延长，False 如果锁不存在
        """
        if not is_redis_available():
            return True

        lock_key = self._make_lock_key(org_name)

        try:
            redis = await self._get_redis()

            # 检查锁是否存在
            exists = await redis.exists(lock_key)
            if not exists:
                logger.warning("lock_extend_failed_not_exists", org=org_name)
                return False

            # 延长过期时间
            new_ttl = await redis.expire(lock_key, self.timeout + additional_seconds)

            if new_ttl:
                logger.info("lock_extended",
                           org=org_name,
                           additional_seconds=additional_seconds,
                           new_ttl=self.timeout + additional_seconds)
                return True
            else:
                return False

        except Exception as e:
            logger.error("lock_extend_error", org=org_name, error=str(e))
            return False

    async def force_release_lock(self, org_name: str) -> bool:
        """强制释放锁（谨慎使用）。

        用于处理异常状态下的锁清理。

        Args:
            org_name: 组织名称

        Returns:
            True 如果成功删除，False 如果锁不存在
        """
        if not is_redis_available():
            return True

        lock_key = self._make_lock_key(org_name)

        try:
            redis = await self._get_redis()

            # 直接删除（不验证持有者）
            deleted = await redis.delete(lock_key)

            if deleted:
                logger.warning("lock_force_released", org=org_name, lock_key=lock_key)
                return True
            else:
                return False

        except Exception as e:
            logger.error("lock_force_release_error", org=org_name, error=str(e))
            return False