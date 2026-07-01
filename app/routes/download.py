"""
文件下载 API 路由。

将沙箱中的文件通过 HTTP Response 返回给用户浏览器。
支持 session 隔离，确保用户只能访问自己会话的文件。
"""

import logging
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/download", tags=["download"])

# 全局沙箱后端引用（由 main.py 设置）
_sandbox_backend = None


def set_sandbox_backend(backend):
    """设置沙箱后端实例。"""
    global _sandbox_backend
    _sandbox_backend = backend
    logger.info("sandbox_backend_set_for_download")


@router.get("/sandbox/{sandbox_path:path}")
async def download_sandbox_file(
    sandbox_path: str,
    filename: Optional[str] = Query(None, description="下载后的文件名"),
    session_id: Optional[str] = Query(None, description="会话ID，用于验证路径归属")
):
    """从沙箱下载文件到用户电脑。

    Args:
        sandbox_path: 沙箱中的文件路径（如 "reports/{session_id}/trend/report_20260622.md"）
        filename: 保存的文件名（可选，默认使用沙箱中的文件名）
        session_id: 会话ID（可选，用于验证路径归属，确保安全隔离）

    Returns:
        HTTP Response，浏览器自动下载文件
    """
    if _sandbox_backend is None:
        logger.error("sandbox_backend_not_available")
        # 返回更友好的错误信息
        return Response(
            content="沙箱服务不可用。请确保：\n1. OpenSandbox Server 正在运行 (localhost:8080)\n2. Agent 初始化成功\n\n请在对话中说'检查沙箱状态'来诊断问题。",
            media_type="text/plain",
            status_code=503
        )

    # 确保路径以 / 开头（沙箱后端要求绝对路径）
    if not sandbox_path.startswith("/"):
        sandbox_path = "/" + sandbox_path

    # session 验证（可选）：如果提供了 session_id，验证路径中的 session 是否匹配
    if session_id:
        path_parts = sandbox_path.split("/")
        # 路径格式：/reports/{session_id}/{type}/{id}.md 或 /analysis/{session_id}/{owner}-{repo}.md
        if len(path_parts) >= 3:
            path_session = path_parts[2]
            if path_session and path_session != session_id and path_session != "default":
                logger.warning("session_path_mismatch",
                               path_session=path_session,
                               requested_session=session_id,
                               sandbox_path=sandbox_path)
                return Response(
                    content=f"路径不属于当前会话，无法访问。路径中的 session: {path_session}，请求的 session: {session_id}",
                    media_type="text/plain",
                    status_code=403
                )

    logger.info("download_request", sandbox_path=sandbox_path, session_id=session_id, backend_type=type(_sandbox_backend).__name__)

    # 从沙箱下载文件
    try:
        results = _sandbox_backend.download_files([sandbox_path])
    except Exception as e:
        logger.error(f"从沙箱读取文件失败: {e}")
        return Response(
            content=f"从沙箱读取文件失败: {str(e)}\n\n请检查文件路径是否正确: {sandbox_path}",
            media_type="text/plain",
            status_code=500
        )

    if not results:
        return Response(
            content=f"文件不存在: {sandbox_path}",
            media_type="text/plain",
            status_code=404
        )

    dl = results[0]
    if dl.error:
        return Response(
            content=f"文件读取错误: {dl.error}",
            media_type="text/plain",
            status_code=404
        )

    content = dl.content
    if content is None:
        return Response(
            content="文件内容为空",
            media_type="text/plain",
            status_code=404
        )

    # 确定下载文件名
    if filename:
        download_filename = filename
    else:
        download_filename = Path(sandbox_path).name

    encoded_filename = quote(download_filename)

    # 硅定内容类型
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

    # 转换为 bytes
    if isinstance(content, str):
        content_bytes = content.encode("utf-8")
    elif isinstance(content, bytes):
        content_bytes = content
    else:
        content_bytes = str(content).encode("utf-8")

    logger.info("file_downloaded",
                sandbox_path=sandbox_path,
                filename=download_filename,
                size=len(content_bytes))

    return Response(
        content=content_bytes,
        media_type=content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
            "Content-Length": str(len(content_bytes)),
        }
    )


@router.get("/files")
async def list_sandbox_files(
    session_id: Optional[str] = Query(None, description="会话ID，用于过滤特定会话的文件"),
    path_prefix: Optional[str] = Query("/reports", description="路径前缀，默认为 /reports")
):
    """列出沙箱中可下载的文件。

    Args:
        session_id: 可选的会话ID，用于过滤特定会话的文件
        path_prefix: 路径前缀，默认为 /reports

    Returns:
        文件列表
    """
    if _sandbox_backend is None:
        raise HTTPException(status_code=503, detail="Sandbox backend not ready")

    try:
        # 确定要列出的路径
        if session_id:
            # 列出特定 session 的文件
            list_path = f"{path_prefix}/{session_id}/"
            logger.info("list_files_for_session", session_id=session_id, path=list_path)
        else:
            # 列出所有文件
            list_path = f"{path_prefix}/"
            logger.info("list_all_files", path=list_path)

        # 执行 ls 命令列出文件
        result = _sandbox_backend.execute(f"ls -laR {list_path}")

        if result.exit_code != 0:
            return {"files": [], "session_id": session_id, "path_prefix": path_prefix}

        # 解析输出，提取所有文件
        files = []
        lines = result.output.strip().split("\n")
        current_dir = ""

        for line in lines:
            if line.startswith(path_prefix):
                current_dir = line.rstrip(":")
            elif line and not line.startswith("total"):
                parts = line.split()
                if len(parts) >= 9 and parts[0].startswith("-"):
                    # 这是一个文件
                    filename = parts[-1]
                    full_path = current_dir + "/" + filename

                    # 从路径中提取 session_id
                    path_parts = current_dir.split("/")
                    file_session_id = path_parts[2] if len(path_parts) >= 3 else "default"

                    files.append({
                        "path": full_path,
                        "name": filename,
                        "session_id": file_session_id,
                        "size": parts[4],
                        "modified": parts[5] + " " + parts[6] + " " + parts[7]
                    })

        # 如果指定了 session_id，过滤文件
        if session_id:
            files = [f for f in files if f.get("session_id") == session_id]

        logger.info("files_listed", count=len(files), session_id=session_id)
        return {"files": files, "session_id": session_id, "path_prefix": path_prefix}

    except Exception as e:
        logger.error("list_files_failed", error=str(e))
        return {"files": [], "error": str(e)}


__all__ = ["router", "set_sandbox_backend"]