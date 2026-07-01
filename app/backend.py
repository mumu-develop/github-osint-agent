"""
OpenSandbox 沙箱后端实现。

继承 BaseSandbox，提供代码执行和文件操作能力。
支持运行时健康检查和自动重连机制。
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import cast, List, Tuple, Optional, TYPE_CHECKING

from opensandbox import SandboxSync
from opensandbox.models import WriteEntry

from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
)
from deepagents.backends.sandbox import BaseSandbox

from app.log_utils import get_logger

if TYPE_CHECKING:
    from app.backend_factory import SandboxManager

logger = get_logger("sandbox")


SyncPollingInterval = float | Callable[[float], float]
PollingStrategy = Callable[[float], float]


class OpenSandboxBackend(BaseSandbox):
    """基于 OpenSandbox 的沙箱后端。"""

    # PATH 环境变量
    SANDBOX_PATH = (
        "/opt/skills-venv/bin:"
        "/opt/python/versions/cpython-3.11.14-linux-x86_64-gnu/bin:"
        "/opt/go/1.25.5/bin:"
        "/opt/node/v22.2.0/bin:"
        "/usr/lib/jvm/java-21-openjdk-amd64/bin:"
        "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    )

    def __init__(
        self,
        *,
        sandbox: SandboxSync,
        timeout: int = 60 * 60,
        sync_polling_interval: SyncPollingInterval = 0.1,
        sandbox_manager: Optional["SandboxManager"] = None,
    ) -> None:
        """初始化 OpenSandbox 后端。

        Args:
            sandbox: OpenSandbox 实例
            timeout: 默认执行超时时间
            sync_polling_interval: 同步轮询间隔
            sandbox_manager: 沙箱管理器（用于重连）
        """
        logger.info("sandbox_backend_init_start", sandbox_id=sandbox.id, timeout=timeout)

        self._sandbox = sandbox
        self._default_timeout = timeout
        self._sandbox_manager = sandbox_manager
        self._is_alive = True  # 沙箱存活状态标记

        if callable(sync_polling_interval):
            polling_strategy = cast("PollingStrategy", sync_polling_interval)
        else:
            def polling_strategy(_elapsed: float) -> float:
                return sync_polling_interval

        self._sync_polling_interval = polling_strategy
        logger.info("sandbox_backend_initialized", sandbox_id=sandbox.id)

    @property
    def id(self) -> str:
        """返回沙盒 ID。"""
        return self._sandbox.id

    @property
    def is_alive(self) -> bool:
        """返回沙箱是否存活。"""
        return self._is_alive

    def check_health(self) -> bool:
        """检查沙箱健康状态。

        Returns:
            True if sandbox is healthy, False otherwise
        """
        try:
            # 使用线程超时保护，防止健康检查挂起
            # opensandbox 的 commands.run() 不支持 timeout 参数
            health_result = {"success": False, "error": None}

            def _do_health_check():
                try:
                    result = self._sandbox.commands.run("echo 'health_check'")
                    health_result["success"] = result.exit_code == 0 or result.exit_code is None
                except Exception as e:
                    health_result["error"] = str(e)

            check_thread = threading.Thread(target=_do_health_check, daemon=True)
            check_thread.start()
            check_thread.join(timeout=30)  # 30秒超时（沙箱命令可能需要较长时间）

            if check_thread.is_alive():
                # 线程还在运行，说明超时了
                logger.warning("sandbox_health_check_timeout", sandbox_id=self.id)
                self._is_alive = False
                return False

            if health_result["error"]:
                error_msg = health_result["error"]
                self._is_alive = False
                if "404" in error_msg or "not found" in error_msg.lower():
                    logger.error("sandbox_not_found", sandbox_id=self.id, error=error_msg)
                else:
                    logger.warning("sandbox_health_check_error", sandbox_id=self.id, error=error_msg)
                return False

            is_healthy = health_result["success"]
            self._is_alive = is_healthy
            if is_healthy:
                logger.debug("sandbox_health_ok", sandbox_id=self.id)
            else:
                logger.warning("sandbox_health_failed", sandbox_id=self.id)
            return is_healthy

        except Exception as e:
            error_msg = str(e)
            self._is_alive = False
            logger.warning("sandbox_health_check_error", sandbox_id=self.id, error=error_msg)
            return False

    def execute(
        self,
        command: str,
        *,
        timeout: int | None = None,
    ) -> ExecuteResponse:
        """在沙盒内执行 Shell 命令。

        如果沙箱失效，会尝试通过 sandbox_manager 重新创建。
        """
        effective_timeout = timeout if timeout is not None else self._default_timeout

        # 注入 PATH
        wrapped = f'export PATH="{self.SANDBOX_PATH}:$PATH" && {command}'
        logger.info("execute_command",
                    sandbox_id=self.id,
                    command=command[:100],
                    timeout=effective_timeout)

        # 尝试执行命令
        result = self._execute_command(wrapped, timeout=effective_timeout)

        # 如果执行失败且可能是沙箱失效，尝试重连
        if result.exit_code != 0 and self._should_try_reconnect(result.output):
            logger.warning("sandbox_maybe_dead_attempting_reconnect", sandbox_id=self.id)
            if self._try_reconnect():
                # 重连成功，重新执行命令
                logger.info("sandbox_reconnected_retrying_command", sandbox_id=self.id)
                result = self._execute_command(wrapped, timeout=effective_timeout)

        logger.info("execute_result",
                    sandbox_id=self.id,
                    exit_code=result.exit_code,
                    output_length=len(result.output))

        return result

    def _should_try_reconnect(self, error_output: str) -> bool:
        """判断是否应该尝试重连沙箱。"""
        reconnect_keywords = ["404", "not found", "connection refused", "timeout", "sandbox_dead"]
        return any(kw in error_output.lower() for kw in reconnect_keywords)

    def _try_reconnect(self) -> bool:
        """尝试重新连接或创建沙箱。

        Returns:
            True if reconnect successful, False otherwise
        """
        if self._sandbox_manager is None:
            logger.warning("no_sandbox_manager_cannot_reconnect", sandbox_id=self.id)
            return False

        try:
            logger.info("attempting_sandbox_reconnect", sandbox_id=self.id)
            new_backend = self._sandbox_manager.recreate_sandbox()

            if new_backend and new_backend.is_alive:
                self._sandbox = new_backend._sandbox
                self._is_alive = True
                logger.info("sandbox_reconnect_success", new_sandbox_id=self.id)
                return True
            else:
                logger.error("sandbox_reconnect_failed", sandbox_id=self.id)
                return False
        except Exception as e:
            logger.error("sandbox_reconnect_error", sandbox_id=self.id, error=str(e))
            return False

    def _execute_command(
        self,
        command: str,
        *,
        timeout: int,
    ) -> ExecuteResponse:
        """执行命令。"""
        try:
            logger.debug("executing_via_api", sandbox_id=self.id)
            result = self._sandbox.commands.run(command)

            stdout = ""
            stderr = ""

            if result.logs.stdout:
                stdout = "\n".join([log.text for log in result.logs.stdout])

            if result.logs.stderr:
                stderr = "\n".join([log.text for log in result.logs.stderr])

            output = stdout
            if stderr and stderr.strip():
                output += f"\n<stderr>{stderr.strip()}</stderr>"

            logger.debug("command_completed",
                         sandbox_id=self.id,
                         exit_code=result.exit_code or 0)

            return ExecuteResponse(
                output=output,
                exit_code=result.exit_code or 0,
                truncated=False,
            )

        except Exception as e:
            error_msg = str(e)
            logger.error("execute_error",
                         sandbox_id=self.id,
                         error=error_msg)

            if "timeout" in error_msg.lower():
                return ExecuteResponse(
                    output=f"命令在 {timeout} 秒后超时",
                    exit_code=124,
                    truncated=False,
                )

            return ExecuteResponse(
                output=f"执行错误: {error_msg}",
                exit_code=1,
                truncated=False,
            )

    def download_files(self, paths: List[str]) -> List[FileDownloadResponse]:
        """从沙箱下载文件。"""
        logger.info("download_files_start",
                    sandbox_id=self.id,
                    file_count=len(paths),
                    paths=paths[:5])

        responses: List[FileDownloadResponse] = []

        for path in paths:
            if not path.startswith("/"):
                logger.warning("invalid_path", sandbox_id=self.id, path=path)
                responses.append(FileDownloadResponse(path=path, content=None, error="invalid_path"))
                continue

            try:
                logger.debug("downloading_file", sandbox_id=self.id, path=path)
                content = self._sandbox.files.read_file(path)
                content_bytes = content.encode("utf-8") if isinstance(content, str) else content
                responses.append(FileDownloadResponse(path=path, content=content_bytes, error=None))
                logger.info("file_downloaded", sandbox_id=self.id, path=path, size=len(content_bytes))
            except Exception as e:
                logger.warning("download_failed", sandbox_id=self.id, path=path, error=str(e))
                responses.append(FileDownloadResponse(path=path, content=None, error="file_not_found"))

        logger.info("download_files_complete",
                    sandbox_id=self.id,
                    success_count=sum(1 for r in responses if r.error is None))

        return responses

    def upload_files(self, files: List[Tuple[str, bytes]]) -> List[FileUploadResponse]:
        """上传文件到沙箱。"""
        logger.info("upload_files_start",
                    sandbox_id=self.id,
                    file_count=len(files))

        responses: List[FileUploadResponse] = []
        upload_entries: List[WriteEntry] = []

        for path, content in files:
            if not path.startswith("/"):
                logger.warning("invalid_upload_path", sandbox_id=self.id, path=path)
                responses.append(FileUploadResponse(path=path, error="invalid_path"))
                continue

            try:
                logger.debug("preparing_upload", sandbox_id=self.id, path=path)

                if isinstance(content, bytes):
                    try:
                        content_str = content.decode("utf-8")
                    except UnicodeDecodeError:
                        content_str = content.decode("latin-1")
                else:
                    content_str = str(content)

                upload_entries.append(WriteEntry(path=path, data=content_str, mode=0o644))
                responses.append(FileUploadResponse(path=path, error=None))
            except Exception as e:
                logger.warning("upload_prepare_failed", sandbox_id=self.id, path=path, error=str(e))
                responses.append(FileUploadResponse(path=path, error=str(e)))

        if upload_entries:
            try:
                logger.info("writing_files_to_sandbox",
                            sandbox_id=self.id,
                            entry_count=len(upload_entries))
                self._sandbox.files.write_files(upload_entries)
                logger.info("upload_complete",
                            sandbox_id=self.id,
                            success_count=len(upload_entries))
            except Exception as e:
                logger.error("upload_write_failed", sandbox_id=self.id, error=str(e))
                for resp in responses:
                    if resp.error is None:
                        resp.error = f"upload_failed: {e}"

        return responses

    def write(self, path: str, content: str | bytes) -> None:
        """写入文件到沙箱。

        Args:
            path: 文件路径（必须以 / 开头）
            content: 文件内容
        """
        if not path.startswith("/"):
            logger.warning("invalid_write_path", sandbox_id=self.id, path=path)
            raise ValueError(f"Path must start with /: {path}")

        try:
            logger.debug("writing_file", sandbox_id=self.id, path=path)

            if isinstance(content, bytes):
                try:
                    content_str = content.decode("utf-8")
                except UnicodeDecodeError:
                    content_str = content.decode("latin-1")
            else:
                content_str = str(content)

            write_entry = WriteEntry(path=path, data=content_str, mode=0o644)
            self._sandbox.files.write_files([write_entry])

            logger.info("file_written", sandbox_id=self.id, path=path, size=len(content_str))
        except Exception as e:
            logger.error("write_error", sandbox_id=self.id, path=path, error=str(e))
            raise

    def read(self, path: str) -> str:
        """从沙箱读取文件。

        Args:
            path: 文件路径（必须以 / 开头）

        Returns:
            文件内容
        """
        if not path.startswith("/"):
            logger.warning("invalid_read_path", sandbox_id=self.id, path=path)
            raise ValueError(f"Path must start with /: {path}")

        try:
            logger.debug("reading_file", sandbox_id=self.id, path=path)
            content = self._sandbox.files.read_file(path)
            logger.info("file_read", sandbox_id=self.id, path=path, size=len(content) if content else 0)
            return content if isinstance(content, str) else content.decode("utf-8")
        except Exception as e:
            logger.error("read_error", sandbox_id=self.id, path=path, error=str(e))
            raise

    def kill(self):
        """关闭沙箱。"""
        logger.info("killing_sandbox", sandbox_id=self.id)

        try:
            kill_result = {"success": False, "error": None}

            def _do_kill():
                try:
                    self._sandbox.kill()
                    kill_result["success"] = True
                    logger.info("sandbox_kill_success", sandbox_id=self.id)
                except Exception as e:
                    kill_result["error"] = str(e)
                    logger.warning("sandbox_kill_failed", sandbox_id=self.id, error=str(e))

            kill_thread = threading.Thread(target=_do_kill, daemon=True)
            kill_thread.start()
            kill_thread.join(timeout=10)

            if kill_thread.is_alive():
                logger.warning("sandbox_kill_timeout", sandbox_id=self.id)
            elif kill_result["success"]:
                logger.info("sandbox_closed", sandbox_id=self.id)
            else:
                logger.warning("sandbox_close_failed", sandbox_id=self.id, error=kill_result['error'])

        except Exception as e:
            logger.warning("kill_error", sandbox_id=self.id, error=str(e))