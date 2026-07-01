"""GitHub API 速率限制管理模块。

防止 GitHub API 速率限制触发，自动监控和管理请求频率。
"""

import os
import asyncio
from datetime import datetime, timedelta
from typing import Optional
from github import Github, RateLimitExceededException
from app.log_utils import get_logger
from app.scanner.scan_config import ScanConfig

logger = get_logger("rate_limiter")


class GitHubRateLimiter:
    """GitHub API 速率限制管理器。

    功能：
    1. 监控剩余请求次数
    2. 在接近限制时自动暂停
    3. 记录限制重置时间，等待恢复
    """

    _instance = None
    _rate_limit_hit = False
    _reset_time: Optional[datetime] = None
    _remaining_requests: int = 5000
    _last_check_time: Optional[datetime] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self.github_token = ScanConfig.get_github_token()
        self.threshold = ScanConfig.get_rate_limit_threshold()
        self.wait_minutes = ScanConfig.get_rate_limit_wait_minutes()
        self.enabled = ScanConfig.get_enable_rate_limit_check()

    async def check_rate_limit(self) -> bool:
        """检查速率限制状态。

        Returns:
            True 如果可以继续请求，False 如果应该暂停
        """
        if not self.enabled:
            return True

        # 如果已标记速率限制
        if GitHubRateLimiter._rate_limit_hit:
            if GitHubRateLimiter._reset_time:
                now = datetime.now()
                if now < GitHubRateLimiter._reset_time:
                    wait_seconds = (GitHubRateLimiter._reset_time - now).total_seconds()
                    logger.warning("rate_limit_waiting",
                                   remaining_seconds=int(wait_seconds),
                                   reset_time=GitHubRateLimiter._reset_time.isoformat())
                    return False
                else:
                    # 重置时间已过
                    GitHubRateLimiter._rate_limit_hit = False
                    GitHubRateLimiter._reset_time = None
                    logger.info("rate_limit_reset_cleared")
                    return True
            return False

        # 检查是否需要更新状态（每 30 秒检查一次）
        now = datetime.now()
        if GitHubRateLimiter._last_check_time:
            if (now - GitHubRateLimiter._last_check_time).total_seconds() < 30:
                # 使用缓存的剩余请求数
                if GitHubRateLimiter._remaining_requests < self.threshold:
                    logger.warning("rate_limit_approaching",
                                   remaining=GitHubRateLimiter._remaining_requests,
                                   threshold=self.threshold)
                    return False
                return True

        # 实际查询 GitHub API 速率限制状态
        try:
            github = Github(self.github_token)
            rate_limit = await asyncio.to_thread(github.get_rate_limit)

            core_limit = rate_limit.core
            GitHubRateLimiter._remaining_requests = core_limit.remaining
            GitHubRateLimiter._reset_time = core_limit.reset.timestamp() if hasattr(core_limit.reset, 'timestamp') else None
            if GitHubRateLimiter._reset_time:
                GitHubRateLimiter._reset_time = datetime.fromtimestamp(GitHubRateLimiter._reset_time)
            GitHubRateLimiter._last_check_time = now

            logger.info("rate_limit_checked",
                       remaining=core_limit.remaining,
                       limit=core_limit.limit,
                       reset_time=str(core_limit.reset))

            if core_limit.remaining < self.threshold:
                logger.warning("rate_limit_low",
                              remaining=core_limit.remaining,
                              threshold=self.threshold)
                GitHubRateLimiter._rate_limit_hit = True
                return False

            return True

        except Exception as e:
            logger.warning("rate_limit_check_failed", error=str(e))
            return True  # 查询失败时允许继续

    def mark_rate_limit_hit(self, reset_time: Optional[datetime] = None):
        """标记速率限制已触发。

        Args:
            reset_time: 限制重置时间（可选）
        """
        GitHubRateLimiter._rate_limit_hit = True
        if reset_time:
            GitHubRateLimiter._reset_time = reset_time
        else:
            GitHubRateLimiter._reset_time = datetime.now() + timedelta(minutes=self.wait_minutes)

        logger.warning("rate_limit_marked",
                      reset_time=GitHubRateLimiter._reset_time.isoformat() if GitHubRateLimiter._reset_time else "unknown")

    def clear_rate_limit(self):
        """清除速率限制标记。"""
        GitHubRateLimiter._rate_limit_hit = False
        GitHubRateLimiter._reset_time = None
        logger.info("rate_limit_cleared")

    @property
    def is_rate_limited(self) -> bool:
        """是否处于速率限制状态。"""
        return GitHubRateLimiter._rate_limit_hit

    @property
    def remaining_requests(self) -> int:
        """剩余请求次数。"""
        return GitHubRateLimiter._remaining_requests


# 全局实例
_rate_limiter: Optional[GitHubRateLimiter] = None


def get_rate_limiter() -> GitHubRateLimiter:
    """获取速率限制管理器实例。"""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = GitHubRateLimiter()
    return _rate_limiter


async def check_can_request() -> bool:
    """检查是否可以发起 GitHub API 请求。

    快捷函数，供扫描器使用。
    """
    limiter = get_rate_limiter()
    return await limiter.check_rate_limit()


def mark_rate_limited(reset_time: Optional[datetime] = None):
    """标记速率限制已触发。

    快捷函数，供扫描器使用。
    """
    limiter = get_rate_limiter()
    limiter.mark_rate_limit_hit(reset_time)