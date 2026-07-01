"""定时任务沙箱池 - 每个任务独立沙箱，执行完成后销毁。

与对话分析的区别：
- 对话分析：所有会话共用一个沙箱，需要保活、缓存ID、过期重建
- 定时任务：每个任务独立沙箱，执行完成立刻销毁，无需保活
"""

import asyncio
import datetime
import os
from typing import Dict, Optional
from pathlib import Path

from opensandbox import SandboxSync
from opensandbox.config.connection_sync import ConnectionConfigSync

from app.backend import OpenSandboxBackend
from app.log_utils import get_logger

logger = get_logger("sandbox_pool")

# 沙箱镜像
SANDBOX_IMAGE = os.getenv(
    "SANDBOX_IMAGE",
    "sandbox-registry.cn-zhangjiakou.cr.aliyuncs.com/osint/osint-sandbox:v1.0.0"
)

# 沙箱创建超时
SANDBOX_READY_TIMEOUT = datetime.timedelta(minutes=5)

# 定时任务沙箱最小目录
TASK_SANDBOX_DIRS = {
    "reports": "/reports",
    "skills": "/skills",
}


class TaskSandboxPool:
    """定时任务沙箱池 - 每个任务独立沙箱。

    特点：
    - 每个任务创建独立沙箱
    - 不缓存沙箱ID（用完即销毁）
    - 不需要保活检查
    - 执行完成立刻销毁
    """

    _instance: Optional["TaskSandboxPool"] = None
    _active_sandboxes: Dict[int, str] = {}  # task_id -> sandbox_id（仅用于跟踪，不持久化）

    def __init__(self):
        """初始化沙箱池。"""
        self._active_sandboxes = {}
        logger.info("task_sandbox_pool_initialized")

    @classmethod
    def get_instance(cls) -> "TaskSandboxPool":
        """获取单例实例。"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_connection_config(self) -> Optional[ConnectionConfigSync]:
        """获取 OpenSandbox 连接配置。"""
        api_key = os.getenv("OPEN_SANDBOX_API_KEY", "")
        domain = os.getenv("OPEN_SANDBOX_DOMAIN") or os.getenv("OPEN_SANDBOX_API_URL", "")
        domain = domain.replace("https://", "").replace("http://", "")

        if not domain:
            logger.warning("no_sandbox_config_for_task")
            return None

        logger.info("using_sandbox_config_for_task", domain=domain)
        return ConnectionConfigSync(
            api_key=api_key,
            domain=domain,
            request_timeout=datetime.timedelta(seconds=300),
            use_server_proxy=os.getenv("USE_SERVER_PROXY", "false").lower() == "true",
        )

    async def create_for_task(self, task_id: int) -> OpenSandboxBackend:
        """为任务创建独立沙箱。

        Args:
            task_id: 任务ID

        Returns:
            OpenSandboxBackend 实例
        """
        logger.info("creating_sandbox_for_task", task_id=task_id)

        connection_config = self._get_connection_config()

        # 创建新沙箱
        create_kwargs = {
            "image": SANDBOX_IMAGE,
            "ready_timeout": SANDBOX_READY_TIMEOUT,
            "skip_health_check": True,
        }
        if connection_config:
            create_kwargs["connection_config"] = connection_config

        # 同步创建沙箱（opensandbox 是同步API）
        sandbox = await asyncio.to_thread(SandboxSync.create, **create_kwargs)
        logger.info("sandbox_created_for_task", task_id=task_id, sandbox_id=sandbox.id, source="scheduled_task")

        # 验证沙箱就绪
        sandbox_ready = False
        for attempt in range(1, 6):
            try:
                result = await asyncio.to_thread(sandbox.commands.run, "echo 'sandbox_ready'")
                if result.exit_code == 0 or result.exit_code is None:
                    sandbox_ready = True
                    break
            except Exception as e:
                logger.warning("sandbox_test_error_for_task", task_id=task_id, attempt=attempt, error=str(e))
                await asyncio.sleep(2)

        if not sandbox_ready:
            raise RuntimeError(f"Sandbox not ready for task {task_id}")

        # 创建 backend
        backend = OpenSandboxBackend(sandbox=sandbox, timeout=600)

        # 创建必要目录
        await asyncio.to_thread(
            backend.execute,
            f"mkdir -p {' '.join(TASK_SANDBOX_DIRS.values())}"
        )

        # 上传必要文件（AGENTS.md、skills）
        await self._upload_files_for_task(backend)

        # 记录活动沙箱（仅用于跟踪，不持久化）
        self._active_sandboxes[task_id] = sandbox.id

        logger.info("sandbox_ready_for_task", task_id=task_id, sandbox_id=sandbox.id, source="scheduled_task")
        return backend

    async def _upload_files_for_task(self, backend: OpenSandboxBackend) -> None:
        """上传必要文件到任务沙箱。"""
        logger.info("uploading_files_for_task")

        # 1. 上传 AGENTS.md
        agents_md_local = Path(__file__).parent.parent.parent / "AGENTS.md"
        if agents_md_local.exists():
            try:
                content = await asyncio.to_thread(agents_md_local.read_text, encoding="utf-8")
                await asyncio.to_thread(backend.write, "/memories/AGENTS.md", content)
                logger.info("agents_md_uploaded_for_task")
            except Exception as e:
                logger.warning("agents_md_upload_failed_for_task", error=str(e))

        # 2. 上传技能目录（最小化，只上传必要的）
        skills_dir_local = Path(__file__).parent.parent.parent / "skills"
        if skills_dir_local.exists() and skills_dir_local.is_dir():
            try:
                await asyncio.to_thread(
                    backend.execute,
                    "mkdir -p /skills/main /skills/trend /skills/security /skills/community /skills/compliance"
                )

                uploaded_count = 0
                for scope_dir in skills_dir_local.iterdir():
                    if not scope_dir.is_dir():
                        continue

                    scope_name = scope_dir.name
                    sandbox_scope_dir = f"/skills/{scope_name}"

                    for skill_dir in scope_dir.iterdir():
                        if not skill_dir.is_dir():
                            continue

                        skill_name = skill_dir.name
                        sandbox_skill_dir = f"{sandbox_scope_dir}/{skill_name}"

                        await asyncio.to_thread(backend.execute, f"mkdir -p {sandbox_skill_dir}")

                        # 上传 SKILL.md
                        skill_md = skill_dir / "SKILL.md"
                        if skill_md.exists():
                            content = await asyncio.to_thread(skill_md.read_text, encoding="utf-8")
                            await asyncio.to_thread(backend.write, f"{sandbox_skill_dir}/SKILL.md", content)
                            uploaded_count += 1

                        # 上传 scripts 目录
                        scripts_dir = skill_dir / "scripts"
                        if scripts_dir.exists():
                            await asyncio.to_thread(backend.execute, f"mkdir -p {sandbox_skill_dir}/scripts")
                            for script_file in scripts_dir.glob("*.py"):
                                content = await asyncio.to_thread(script_file.read_text, encoding="utf-8")
                                await asyncio.to_thread(
                                    backend.write,
                                    f"{sandbox_skill_dir}/scripts/{script_file.name}",
                                    content
                                )
                                uploaded_count += 1

                logger.info("skills_uploaded_for_task", total_files=uploaded_count)
            except Exception as e:
                logger.warning("skills_upload_failed_for_task", error=str(e))

    async def destroy_for_task(self, task_id: int) -> None:
        """销毁任务沙箱。

        Args:
            task_id: 任务ID
        """
        sandbox_id = self._active_sandboxes.get(task_id)

        if not sandbox_id:
            logger.debug("no_sandbox_to_destroy", task_id=task_id)
            return

        logger.info("destroying_sandbox_for_task", task_id=task_id, sandbox_id=sandbox_id)

        try:
            connection_config = self._get_connection_config()

            # 连接并销毁沙箱（使用 kill 方法）
            connect_kwargs = {"sandbox_id": sandbox_id}
            if connection_config:
                connect_kwargs["connection_config"] = connection_config

            sandbox = await asyncio.to_thread(SandboxSync.connect, **connect_kwargs)
            # 使用 kill 方法销毁沙箱
            await asyncio.to_thread(sandbox.kill)

            logger.info("sandbox_destroyed_for_task", task_id=task_id, sandbox_id=sandbox_id, source="scheduled_task")

        except Exception as e:
            logger.warning("sandbox_destroy_failed_for_task", task_id=task_id, sandbox_id=sandbox_id, error=str(e))

        # 从活动列表中移除
        if task_id in self._active_sandboxes:
            del self._active_sandboxes[task_id]

    def get_active_count(self) -> int:
        """获取当前活动沙箱数量。"""
        return len(self._active_sandboxes)