"""
报告管理工具。

提供报告保存、列表和下载功能。

使用流程：
1. Agent 使用内置 write_file 将报告保存到沙箱 /reports/{session_id}/{type}/{id}.md
2. 使用 return_report_for_download 直接返回报告内容
3. 前端收到内容后自动触发浏览器下载
"""

import base64
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Annotated

from langchain_core.tools import tool, InjectedToolArg
from langchain_core.runnables import RunnableConfig

from app.log_utils import get_logger
from app.utils.session import get_session_id, get_session_report_path

logger = get_logger("report")

# 全局沙箱后端引用（由 main.py 设置）
_sandbox_backend = None


def set_sandbox_backend(backend):
    """设置沙箱后端实例，供工具读取文件。"""
    global _sandbox_backend
    _sandbox_backend = backend
    logger.info("sandbox_backend_set_for_report", backend_type=type(backend).__name__ if backend else None)

# 本地报告目录（非沙箱模式）
LOCAL_REPORTS_DIR = Path(__file__).parent.parent.parent / "reports"

# 报告类型目录
REPORT_TYPE_DIRS = {
    "trend": LOCAL_REPORTS_DIR / "trend",
    "security": LOCAL_REPORTS_DIR / "security",
    "community": LOCAL_REPORTS_DIR / "community",
    "compliance": LOCAL_REPORTS_DIR / "compliance",
}

# 沙箱报告路径模板（已弃用，使用 get_session_report_path 函数）
# SANDBOX_REPORT_PATH = "/reports/{report_type}/{report_id}.md"


def _ensure_local_dirs():
    """确保本地报告目录存在。"""
    for dir_path in REPORT_TYPE_DIRS.values():
        dir_path.mkdir(parents=True, exist_ok=True)


@tool
async def save_report_to_local(
    report_type: str,
    report_id: str,
    content: str,
    format: str = "md"
) -> Dict[str, Any]:
    """保存报告到本地目录（非沙箱模式使用）。

    Args:
        report_type: 报告类型 - "trend", "security", "community", "compliance"
        report_id: 报告唯一标识（如 "trend-20260622-001"）
        content: 报告内容（Markdown 格式）
        format: 文件格式 - "md", "txt", "json"

    Returns:
        保存结果，包含文件路径、大小等信息
    """
    _ensure_local_dirs()

    if report_type not in REPORT_TYPE_DIRS:
        return {
            "success": False,
            "error": f"无效的报告类型: {report_type}。有效类型: {list(REPORT_TYPE_DIRS.keys())}"
        }

    filename = f"{report_id}.{format}"
    file_path = REPORT_TYPE_DIRS[report_type] / filename

    try:
        file_path.write_text(str(content), encoding="utf-8")
        logger.info("report_saved_to_local", file_path=str(file_path), size=len(content))

        return {
            "success": True,
            "file_path": str(file_path),
            "file_size": len(content),
            "report_type": report_type,
            "report_id": report_id,
        }
    except Exception as e:
        logger.error("save_report_failed", error=str(e))
        return {"success": False, "error": str(e)}


@tool
async def list_local_reports(
    report_type: Optional[str] = None,
    limit: int = 50
) -> Dict[str, Any]:
    """列出本地已保存的报告。

    Args:
        report_type: 报告类型过滤（可选）
        limit: 最大返回数量

    Returns:
        报告列表和统计信息
    """
    _ensure_local_dirs()

    reports = []
    by_type = {}

    dirs_to_scan = {report_type: REPORT_TYPE_DIRS[report_type]} if report_type else REPORT_TYPE_DIRS

    if report_type and report_type not in REPORT_TYPE_DIRS:
        return {"reports": [], "total": 0, "error": f"无效的报告类型: {report_type}"}

    for rtype, directory in dirs_to_scan.items():
        if not directory.exists():
            continue
        count = 0
        for file in directory.iterdir():
            if file.is_file():
                stat = file.stat()
                reports.append({
                    "filename": file.name,
                    "report_type": rtype,
                    "file_size": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat()
                })
                count += 1
        by_type[rtype] = count

    reports.sort(key=lambda x: x["modified_at"], reverse=True)
    return {"reports": reports[:limit], "total": len(reports), "by_type": by_type}


@tool
async def get_report_content(report_type: str, report_id: str) -> Dict[str, Any]:
    """获取本地报告内容。

    Args:
        report_type: 报告类型
        report_id: 报告标识

    Returns:
        报告内容
    """
    if report_type not in REPORT_TYPE_DIRS:
        return {"success": False, "error": f"无效的报告类型: {report_type}"}

    file_path = REPORT_TYPE_DIRS[report_type] / f"{report_id}.md"

    if not file_path.exists():
        return {"success": False, "error": "报告不存在"}

    try:
        content = file_path.read_text(encoding="utf-8")
        return {"success": True, "content": content, "file_size": len(content)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
async def return_report_for_download(
    sandbox_path: str,
    config: Annotated[RunnableConfig, InjectedToolArg]
) -> Dict[str, Any]:
    """读取沙箱报告内容并返回，供前端直接触发浏览器下载。

    此工具会直接读取沙箱中的文件内容，前端收到后可直接触发下载，
    不需要额外的 HTTP 请求。

    路径必须包含当前 session_id，确保会话隔离安全。

    Args:
        sandbox_path: 沙箱中的绝对文件路径（如 "/reports/{session_id}/trend/report-20260622.md"）
        config: RunnableConfig（自动注入，用于验证 session_id）

    Returns:
        包含文件内容的字典，前端使用返回的 content 字段触发下载
    """
    # 获取当前 session_id
    session_id = get_session_id(config)

    if not sandbox_path or not sandbox_path.startswith("/"):
        return {"success": False, "error": f"路径必须以 / 开头: {sandbox_path}"}

    # 验证路径中的 session_id（安全检查）
    # 检查路径是否包含 session 目录层级
    path_parts = sandbox_path.split("/")
    # 路径格式：/reports/{session_id}/{type}/{id}.md 或 /analysis/{session_id}/{owner}-{repo}.md
    if len(path_parts) >= 3:
        path_session = path_parts[2]  # 获取路径中的 session_id
        # 如果路径包含 session 目录，验证是否匹配当前 session
        if path_session and path_session != session_id:
            logger.warning("session_path_mismatch",
                           path_session=path_session,
                           current_session=session_id,
                           sandbox_path=sandbox_path)
            return {
                "success": False,
                "error": f"路径不属于当前会话，无法访问",
                "filename": Path(sandbox_path).name,
                "sandbox_path": sandbox_path,
            }

    filename = Path(sandbox_path).name

    logger.info("return_report_for_download_start",
                sandbox_path=sandbox_path,
                filename=filename,
                session_id=session_id)

    # 检查沙箱后端是否可用
    if _sandbox_backend is None:
        logger.warning("sandbox_backend_not_available")
        return {
            "success": False,
            "error": "沙箱服务不可用，无法读取文件内容",
            "filename": filename,
            "sandbox_path": sandbox_path,
        }

    # 从沙箱读取文件内容
    try:
        results = _sandbox_backend.download_files([sandbox_path])
        logger.info("sandbox_download_result", count=len(results) if results else 0)
    except Exception as e:
        logger.error("sandbox_read_failed", error=str(e))
        return {
            "success": False,
            "error": f"从沙箱读取文件失败: {str(e)}",
            "filename": filename,
            "sandbox_path": sandbox_path,
        }

    if not results:
        logger.warning("file_not_found", sandbox_path=sandbox_path)
        return {
            "success": False,
            "error": f"文件不存在: {sandbox_path}",
            "filename": filename,
        }

    dl = results[0]
    if dl.error:
        logger.warning("file_read_error", error=dl.error)
        return {
            "success": False,
            "error": f"文件读取错误: {dl.error}",
            "filename": filename,
        }

    content = dl.content
    if content is None:
        logger.warning("file_content_empty")
        return {
            "success": False,
            "error": "文件内容为空",
            "filename": filename,
        }

    # 确定内容类型
    content_type = "application/octet-stream"
    if sandbox_path.endswith(".md"):
        content_type = "text/markdown"
    elif sandbox_path.endswith(".txt"):
        content_type = "text/plain"
    elif sandbox_path.endswith(".json"):
        content_type = "application/json"
    elif sandbox_path.endswith(".csv"):
        content_type = "text/csv"
    elif sandbox_path.endswith(".html"):
        content_type = "text/html"

    # 将内容转为 bytes，然后 base64 编码
    if isinstance(content, str):
        content_bytes = content.encode("utf-8")
    elif isinstance(content, bytes):
        content_bytes = content
    else:
        content_bytes = str(content).encode("utf-8")

    content_b64 = base64.b64encode(content_bytes).decode("utf-8")

    logger.info("file_content_read_success",
                sandbox_path=sandbox_path,
                filename=filename,
                size=len(content_bytes),
                content_type=content_type)

    return {
        "success": True,
        "action": "download",
        "filename": filename,
        "sandbox_path": sandbox_path,
        "content_type": content_type,
        "content_b64": content_b64,  # base64 编码的文件内容
        "size": len(content_bytes),
        "message": f"报告已读取，文件名: {filename}，大小: {len(content_bytes)} 字节",
    }


@tool
async def get_sandbox_report_path(
    report_type: str,
    report_id: str,
    config: Annotated[RunnableConfig, InjectedToolArg]
) -> Dict[str, Any]:
    """获取沙箱报告的标准路径。

    用于配合 Agent 的内置 write_file 功能保存报告。
    路径已包含 session_id，确保不同会话的报告隔离存储。

    Args:
        report_type: 报告类型 - "trend", "security", "community", "compliance"
        report_id: 报告唯一标识
        config: RunnableConfig（自动注入，包含 session_id）

    Returns:
        包含路径信息的字典
        {
            "path": "/reports/{session_id}/{report_type}/{report_id}.md",
            "session_id": "session_id",
            "report_type": "trend",
            "report_id": "report-id"
        }
    """
    session_id = get_session_id(config)

    valid_types = ["trend", "security", "community", "compliance"]
    if report_type not in valid_types:
        return {
            "error": f"无效的报告类型，可选: {valid_types}",
            "valid_types": valid_types
        }

    path = get_session_report_path(report_type, report_id, session_id)

    logger.info("sandbox_report_path_generated",
                path=path,
                session_id=session_id,
                report_type=report_type,
                report_id=report_id)

    return {
        "path": path,
        "session_id": session_id,
        "report_type": report_type,
        "report_id": report_id,
        "message": f"报告路径已生成，请使用 write_file 保存到此路径"
    }


# 导出
report_tools = [
    save_report_to_local,
    list_local_reports,
    get_report_content,
    return_report_for_download,
    get_sandbox_report_path,
]

__all__ = ["report_tools", "set_sandbox_backend"]