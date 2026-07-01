"""
Session 辅助模块。

提供 session_id 获取和 session 路径生成功能。
"""

from typing import Dict, Any, Optional


def get_session_id(config: Optional[Dict[str, Any]] = None) -> str:
    """从 config 中获取 session_id/thread_id。

    Args:
        config: RunnableConfig 配置对象

    Returns:
        session_id，如果没有则返回 "default"
    """
    if config is None:
        return "default"

    # 从 configurable 中获取 thread_id
    configurable = config.get("configurable", {})
    thread_id = configurable.get("thread_id")

    if thread_id:
        return thread_id

    return "default"


def get_session_path(base_path: str, session_id: str, *parts) -> str:
    """生成带 session 的路径。

    Args:
        base_path: 基础路径（如 "/reports"）
        session_id: 会话标识
        *parts: 路径的其他部分

    Returns:
        带 session 的完整路径

    Examples:
        >>> get_session_path("/reports", "session-123", "trend", "report.md")
        "/reports/session-123/trend/report.md"
    """
    if parts:
        parts_str = "/".join(parts)
        return f"{base_path}/{session_id}/{parts_str}"
    else:
        return f"{base_path}/{session_id}"


def get_session_report_path(report_type: str, report_id: str, session_id: str) -> str:
    """获取带 session 的报告路径。

    Args:
        report_type: 报告类型 - "trend", "security", "community", "compliance"
        report_id: 报告唯一标识
        session_id: 会话标识

    Returns:
        沙箱报告路径

    Examples:
        >>> get_session_report_path("trend", "report-20260622", "session-123")
        "/reports/session-123/trend/report-20260622.md"
    """
    valid_types = ["trend", "security", "community", "compliance"]
    if report_type not in valid_types:
        report_type = "general"

    return f"/reports/{session_id}/{report_type}/{report_id}.md"


def get_session_analysis_path(owner: str, repo: str, session_id: str) -> str:
    """获取带 session 的分析报告路径。

    Args:
        owner: 仓库 owner
        repo: 仓库名称
        session_id: 会话标识

    Returns:
        分析报告路径

    Examples:
        >>> get_session_analysis_path("octocat", "Hello-World", "session-123")
        "/analysis/session-123/octocat-Hello-World.md"
    """
    return f"/analysis/{session_id}/{owner}-{repo}.md"


def get_session_workspace_path(session_id: str, *parts) -> str:
    """获取带 session 的工作空间路径。

    Args:
        session_id: 会话标识
        *parts: 路径的其他部分

    Returns:
        工作空间路径

    Examples:
        >>> get_session_workspace_path("session-123", "uploads", "file.txt")
        "/workspace/session-123/uploads/file.txt"
    """
    return get_session_path("/workspace", session_id, *parts)


__all__ = [
    "get_session_id",
    "get_session_path",
    "get_session_report_path",
    "get_session_analysis_path",
    "get_session_workspace_path",
]