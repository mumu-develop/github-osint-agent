"""进度追踪模块。

提供两种进度追踪器：
- ProgressTracker: 用于 Agent 实时扫描的进度追踪
- ScheduledTaskProgressTracker: 用于定时任务的进度追踪
"""

from app.progress.progress_tracker import (
    ProgressTracker,
    RepoStatus,
    get_progress_queue,
    remove_progress_queue,
    push_progress_event,
    set_current_session,
    get_current_session,
    create_progress_tracker,
)

from app.progress.scheduled_task_tracker import (
    ScheduledTaskProgressTracker,
    get_scheduled_task_queue,
    remove_scheduled_task_queue,
)

__all__ = [
    # ProgressTracker 相关
    "ProgressTracker",
    "RepoStatus",
    "get_progress_queue",
    "remove_progress_queue",
    "push_progress_event",
    "set_current_session",
    "get_current_session",
    "create_progress_tracker",
    # ScheduledTaskProgressTracker 相关
    "ScheduledTaskProgressTracker",
    "get_scheduled_task_queue",
    "remove_scheduled_task_queue",
]