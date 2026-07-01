"""进度推送模块。

提供仓库扫描状态的实时推送功能，通过 SSE 发送状态更新事件。
使用全局事件队列实现工具与 SSE 流的通信。
"""

import asyncio
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime
from contextvars import ContextVar

from app.log_utils import get_logger

logger = get_logger("progress_tracker")


# ============================================================
# 全局事件队列（用于工具推送进度）
# ============================================================

# 每个 session 一个事件队列
_progress_queues: Dict[str, asyncio.Queue] = {}

# 使用 ContextVar 替代全局变量，确保异步上下文正确传递
_current_session_ctx: ContextVar[str] = ContextVar("current_session", default="default")


def get_progress_queue(session_id: str) -> asyncio.Queue:
    """获取指定 session 的进度事件队列。"""
    if session_id not in _progress_queues:
        _progress_queues[session_id] = asyncio.Queue()
        logger.info("progress_queue_created", session_id=session_id)
    return _progress_queues[session_id]


def remove_progress_queue(session_id: str):
    """清理 session 的进度队列。"""
    if session_id in _progress_queues:
        del _progress_queues[session_id]


async def push_progress_event(session_id: str, event_type: str, data: dict):
    """推送进度事件到队列。"""
    queue = get_progress_queue(session_id)
    event = {
        "type": event_type,
        "data": data,
        "timestamp": datetime.now().isoformat()
    }
    await queue.put(event)
    logger.debug("progress_event_pushed", session_id=session_id, type=event_type)


# ============================================================
# 进度追踪器
# ============================================================

@dataclass
class RepoStatus:
    """单个仓库的状态。"""
    name: str
    status: str = "waiting"  # waiting, running, done, error
    phase: str = ""  # cve_scan, secret_scan, license_check, etc.
    findings: int = 0
    error: str = ""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class ProgressTracker:
    """进度追踪器，管理多个仓库的状态。"""

    def __init__(
        self,
        subagent: str,
        repos: List[str],
        session_id: str = None
    ):
        """
        Args:
            subagent: 子智能体名称
            repos: 仓库列表
            session_id: 会话ID（用于推送事件）
        """
        self.subagent = subagent
        self.repos = repos
        self.session_id = session_id
        self.statuses: Dict[str, RepoStatus] = {
            repo: RepoStatus(name=repo) for repo in repos
        }
        self.phase = ""
        self._lock = asyncio.Lock()

    async def update(
        self,
        repo: str,
        status: str,
        phase: str = "",
        findings: int = 0,
        error: str = ""
    ):
        """更新单个仓库的状态并推送。"""
        async with self._lock:
            if repo not in self.statuses:
                logger.warning("repo_not_in_tracker", repo=repo)
                return

            repo_status = self.statuses[repo]
            repo_status.status = status
            repo_status.phase = phase

            if status == "running" and repo_status.started_at is None:
                repo_status.started_at = datetime.now()

            if status == "done":
                repo_status.completed_at = datetime.now()
                repo_status.findings = findings

            if status == "error":
                repo_status.error = error

            if phase:
                self.phase = phase

            # 推送状态更新
            await self._push_update()

    async def _push_update(self):
        """推送状态更新到前端。"""
        if not self.session_id:
            return

        # 计算统计
        stats = {
            "done": sum(1 for s in self.statuses.values() if s.status == "done"),
            "running": sum(1 for s in self.statuses.values() if s.status == "running"),
            "waiting": sum(1 for s in self.statuses.values() if s.status == "waiting"),
            "error": sum(1 for s in self.statuses.values() if s.status == "error"),
        }

        # 构建状态列表
        repo_list = []
        for repo_name in self.repos:
            status = self.statuses[repo_name]
            repo_list.append({
                "name": repo_name,
                "status": status.status,
                "phase": status.phase,
                "findings": status.findings,
                "error": status.error[:30] if status.error else None,
            })

        event_data = {
            "subagent": self.subagent,
            "phase": self.phase,
            "repos": repo_list,
            "stats": stats,
        }

        await push_progress_event(self.session_id, "repo_status", event_data)

    def get_summary(self) -> Dict[str, Any]:
        """获取最终汇总。"""
        stats = {
            "done": sum(1 for s in self.statuses.values() if s.status == "done"),
            "running": 0,
            "waiting": 0,
            "error": sum(1 for s in self.statuses.values() if s.status == "error"),
        }

        total_findings = sum(s.findings for s in self.statuses.values())

        return {
            "subagent": self.subagent,
            "total_repos": len(self.repos),
            "completed": stats["done"],
            "errors": stats["error"],
            "total_findings": total_findings,
        }


# ============================================================
# Session ID 注入（工具中获取 session_id）
# ============================================================

def set_current_session(session_id: str):
    """设置当前 session ID（在 SSE 流开始时调用）。

    使用 ContextVar 确保在异步任务链中正确传递。
    """
    _current_session_ctx.set(session_id)
    logger.info("session_context_set", session_id=session_id)


def get_current_session() -> str:
    """获取当前 session ID。

    从 ContextVar 获取，确保能正确获取异步上下文中的 session_id。
    """
    return _current_session_ctx.get()


def create_progress_tracker(
    subagent: str,
    repos: List[str]
) -> ProgressTracker:
    """创建进度追踪器（使用当前 session）。"""
    session_id = get_current_session()
    logger.info("progress_tracker_created",
                subagent=subagent,
                repos_count=len(repos),
                session_id=session_id)
    return ProgressTracker(subagent, repos, session_id)