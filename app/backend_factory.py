"""
Backend 配置和初始化模块。

参考 FaasMonitor_OpenClaw 的沙箱初始化逻辑。
"""

from __future__ import annotations

import asyncio
import datetime
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from deepagents.backends import CompositeBackend, StoreBackend
from opensandbox import SandboxSync
from opensandbox.config.connection_sync import ConnectionConfigSync

from app.backend import OpenSandboxBackend
from app.log_utils import get_logger

logger = get_logger("backend")


# ============================================================
# 沙箱目录配置（统一管理，一处修改）
# ============================================================
SANDBOX_DIRS = {
    "analysis": "/analysis",           # 分析结果临时存放
    "reports": "/reports",             # 生成的报告
    "memories": "/memories",           # Agent 长期记忆（StoreBackend 管理）
    "persisted_skills": "/persisted-skills",  # 持久化技能
    "workspace": "/workspace",         # 工作空间
}

# StoreBackend 路由路径（与 SANDBOX_DIRS 保持一致）
STORE_ROUTES = {
    "/memories/": StoreBackend(),
    "/persisted-skills/": StoreBackend(),
}

# 沙箱镜像（必须使用定制镜像，依赖已预装）
SANDBOX_IMAGE = os.getenv(
    "SANDBOX_IMAGE",
    "sandbox-registry.cn-zhangjiakou.cr.aliyuncs.com/osint/osint-sandbox:v1.0.0"
)

# 沙箱创建超时
SANDBOX_READY_TIMEOUT = datetime.timedelta(minutes=5)

# 复用沙箱验证重试次数（假死沙箱快速放弃）
REUSE_SANDBOX_RETRIES = int(os.getenv("REUSE_SANDBOX_RETRIES", "3"))

# 新沙箱创建最大等待次数（约 180 秒上限）
MAX_SANDBOX_WAIT_RETRIES = int(os.getenv("MAX_SANDBOX_WAIT_RETRIES", "36"))

# 运行时健康检查重试次数（执行命令时沙箱失效）
RUNTIME_HEALTH_RETRIES = int(os.getenv("RUNTIME_HEALTH_RETRIES", "2"))

# 是否通过 server 代理访问 execd（bridge 模式下建议设为 false）
USE_SERVER_PROXY = os.getenv("USE_SERVER_PROXY", "false").lower() == "true"

# 沙箱 ID 缓存文件
SANDBOX_ID_CACHE_FILE = Path(__file__).parent.parent / ".sandbox_id_cache.json"

# Skills Store Namespace
SKILLS_STORE_NAMESPACE = ("skills", "persisted")


# ============================================================
# 沙箱 ID 缓存管理
# ============================================================

def _save_sandbox_id(sandbox_id: str) -> None:
    """持久化沙箱 ID。"""
    logger.info("saving_sandbox_id", sandbox_id=sandbox_id)
    try:
        cache_data = {
            "sandbox_id": sandbox_id,
            "created_at": datetime.datetime.now().isoformat(),
            "image": SANDBOX_IMAGE,
        }
        SANDBOX_ID_CACHE_FILE.write_text(json.dumps(cache_data, indent=2), encoding="utf-8")
        logger.info("sandbox_id_saved", sandbox_id=sandbox_id)
    except Exception as e:
        logger.warning("save_sandbox_id_failed", error=str(e))


def _load_cached_sandbox_id() -> Optional[str]:
    """加载缓存的沙箱 ID。"""
    logger.info("loading_cached_sandbox_id", cache_file=str(SANDBOX_ID_CACHE_FILE))

    if not SANDBOX_ID_CACHE_FILE.exists():
        logger.info("no_cached_sandbox_id")
        return None

    try:
        cache_data = json.loads(SANDBOX_ID_CACHE_FILE.read_text(encoding="utf-8"))
        sandbox_id = cache_data.get("sandbox_id")
        cached_image = cache_data.get("image")
        created_at_str = cache_data.get("created_at")

        if not sandbox_id or not created_at_str:
            logger.warning("invalid_cache_data")
            return None

        if cached_image != SANDBOX_IMAGE:
            logger.info("image_mismatch", cached=cached_image, expected=SANDBOX_IMAGE)
            return None

        created_at = datetime.datetime.fromisoformat(created_at_str)
        max_age_hours = int(os.getenv("SANDBOX_MAX_AGE_HOURS", "1"))
        age_hours = (datetime.datetime.now() - created_at).total_seconds() / 3600

        if age_hours > max_age_hours:
            logger.info("sandbox_expired", age_hours=age_hours, max_hours=max_age_hours)
            return None

        logger.info("cached_sandbox_found", sandbox_id=sandbox_id, age_hours=age_hours)
        return sandbox_id

    except Exception as e:
        logger.warning("load_cache_failed", error=str(e))
        return None


def _clear_sandbox_cache() -> None:
    """清除沙箱缓存。"""
    logger.info("clearing_sandbox_cache")
    try:
        if SANDBOX_ID_CACHE_FILE.exists():
            SANDBOX_ID_CACHE_FILE.unlink()
            logger.info("sandbox_cache_cleared")
    except Exception as e:
        logger.warning("clear_cache_failed", error=str(e))


def _get_connection_config() -> Optional[ConnectionConfigSync]:
    """获取 OpenSandbox 连接配置。"""
    api_key = os.getenv("OPEN_SANDBOX_API_KEY", "")
    domain = os.getenv("OPEN_SANDBOX_DOMAIN") or os.getenv("OPEN_SANDBOX_API_URL", "")

    # 去掉协议前缀
    domain = domain.replace("https://", "").replace("http://", "")

    if not domain:
        logger.warning("no_sandbox_config")
        return None

    logger.info("using_sandbox_config", domain=domain, use_server_proxy=USE_SERVER_PROXY)
    return ConnectionConfigSync(
        api_key=api_key,
        domain=domain,
        request_timeout=datetime.timedelta(seconds=300),  # 调整为 5 分钟，支持大组织扫描
        use_server_proxy=USE_SERVER_PROXY,
    )


# ============================================================
# Backend 创建
# ============================================================

class SandboxManager:
    """沙箱生命周期管理器。

    负责：
    - 维护当前沙箱实例
    - 检测沙箱失效
    - 自动重新创建沙箱
    - 定期健康检查（保活）
    """

    _instance: Optional["SandboxManager"] = None
    _current_backend: Optional[OpenSandboxBackend] = None
    _config: Dict[str, Any] = {}
    _health_check_task: Optional[asyncio.Task] = None  # 健康检查任务
    _health_check_paused: bool = False  # 健康检查是否暂停

    def __init__(self, config: Dict[str, Any] = None):
        """初始化管理器。"""
        self._config = config or {"timeout": 60 * 60}
        self._health_check_paused = False
        logger.info("sandbox_manager_initialized")

    @classmethod
    def get_instance(cls) -> "SandboxManager":
        """获取单例实例。"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_backend(self, backend: OpenSandboxBackend) -> None:
        """设置当前沙箱 backend。"""
        self._current_backend = backend
        logger.info("sandbox_manager_backend_set", sandbox_id=backend.id)
        # 启动健康检查（保活）
        self._start_health_check()

    def get_backend(self) -> Optional[OpenSandboxBackend]:
        """获取当前沙箱 backend。"""
        return self._current_backend

    def _start_health_check(self) -> None:
        """启动定期健康检查（保活）。"""
        if self._health_check_task is not None:
            self._health_check_task.cancel()

        async def health_check_loop():
            """定期检查沙箱健康状态，必要时重新创建。"""
            while True:
                try:
                    await asyncio.sleep(120)  # 每120秒检查一次（避免频繁打断流式对话）

                    # 如果健康检查被暂停，跳过本次检查
                    if self._health_check_paused:
                        logger.debug("health_check_skipped_paused")
                        continue

                    if self._current_backend is None:
                        continue

                    # 执行健康检查
                    is_healthy = self._current_backend.check_health()
                    if not is_healthy:
                        logger.warning("sandbox_health_check_failed",
                                       sandbox_id=self._current_backend.id,
                                       action="recreating")
                        # 尝试重新创建
                        new_backend = self.recreate_sandbox()
                        if new_backend:
                            logger.info("sandbox_recreated_after_health_failure",
                                        new_id=new_backend.id)
                except asyncio.CancelledError:
                    logger.info("health_check_task_cancelled")
                    break
                except Exception as e:
                    logger.error("health_check_error", error=str(e))

        self._health_check_task = asyncio.create_task(health_check_loop())
        logger.info("sandbox_health_check_started", interval_seconds=120)

    def pause_health_check(self) -> None:
        """暂停健康检查（流式对话期间调用）。"""
        self._health_check_paused = True
        logger.info("health_check_paused")

    def resume_health_check(self) -> None:
        """恢复健康检查（流式对话结束后调用）。"""
        self._health_check_paused = False
        logger.info("health_check_resumed")

    def stop_health_check(self) -> None:
        """停止健康检查。"""
        if self._health_check_task is not None:
            self._health_check_task.cancel()
            self._health_check_task = None
            self._health_check_paused = False
            logger.info("sandbox_health_check_stopped")

    def recreate_sandbox(self) -> Optional[OpenSandboxBackend]:
        """重新创建沙箱（同步版本，用于运行时调用）。

        当沙箱失效时调用，会：
        1. 清除旧缓存
        2. 创建新沙箱
        3. 更新管理器中的 backend 引用

        Returns:
            新的 OpenSandboxBackend 实例，或 None 如果失败
        """
        logger.info("sandbox_manager_recreate_start")

        # 清除旧缓存
        _clear_sandbox_cache()

        try:
            # 创建新沙箱（同步方式）
            connection_config = _get_connection_config()

            logger.info("creating_new_sandbox_on_reconnect", image=SANDBOX_IMAGE)
            create_kwargs = {
                "image": SANDBOX_IMAGE,
                "ready_timeout": SANDBOX_READY_TIMEOUT,
                "skip_health_check": True,
            }
            if connection_config:
                create_kwargs["connection_config"] = connection_config

            sandbox = SandboxSync.create(**create_kwargs)
            logger.info("new_sandbox_created", sandbox_id=sandbox.id, source="conversation")

            # 验证新沙箱
            for attempt in range(1, 3):
                try:
                    result = sandbox.commands.run("echo 'sandbox_ready'")
                    if result.exit_code == 0 or result.exit_code is None:
                        break
                except Exception:
                    import time
                    time.sleep(2)

            # 保存新缓存
            _save_sandbox_id(sandbox.id)

            # 创建新 backend
            new_backend = OpenSandboxBackend(
                sandbox=sandbox,
                timeout=self._config.get("timeout", 60 * 60),
                sandbox_manager=self
            )

            # 创建工作目录
            new_backend.execute(f"mkdir -p {' '.join(SANDBOX_DIRS.values())}")

            # 上传必要文件
            _upload_files_to_sandbox(new_backend)

            # 更新引用
            self._current_backend = new_backend
            logger.info("sandbox_recreate_success", new_sandbox_id=sandbox.id)

            return new_backend

        except Exception as e:
            logger.error("sandbox_recreate_failed", error=str(e))
            return None

    async def recreate_sandbox_async(self) -> Optional[OpenSandboxBackend]:
        """异步重新创建沙箱。"""
        return self.recreate_sandbox()


async def create_backend(
    config: Dict[str, Any] = None,
) -> CompositeBackend:
    """创建沙箱 Backend（强制使用沙箱模式）。

    Args:
        config: 配置字典，包含 timeout 等参数

    Returns:
        CompositeBackend 工厂函数

    Raises:
        RuntimeError: 如果沙箱创建失败（必须成功才能继续）
    """
    logger.info("create_backend_start")

    if config is None:
        config = {"timeout": 60 * 60}

    # 获取沙箱管理器单例
    manager = SandboxManager.get_instance()
    manager._config = config

    # 强制使用沙箱 backend
    logger.info("creating_sandbox_backend_required")
    default_backend = await _create_sandbox_backend(config)

    # 设置到管理器，并注入管理器引用
    manager.set_backend(default_backend)
    default_backend._sandbox_manager = manager

    logger.info("backend_created",
                backend_type=type(default_backend).__name__,
                sandbox_id=default_backend.id)

    # 组合 backend（每次调用都返回同一个 backend 实例）
    def backend_factory(runtime):
        logger.info("creating_composite_backend")
        # 如果当前 backend 失效，尝试重连
        current_backend = manager.get_backend()
        if current_backend and not current_backend.is_alive:
            logger.warning("backend_dead_before_factory_call")
            if current_backend._try_reconnect():
                logger.info("backend_reconnected_in_factory")
        return CompositeBackend(
            default=current_backend or default_backend,
            routes=STORE_ROUTES,
        )

    return backend_factory


async def _create_sandbox_backend(config: Dict[str, Any]) -> OpenSandboxBackend:
    """创建 OpenSandbox backend。"""
    logger.info("_create_sandbox_backend_start")

    connection_config = _get_connection_config()
    sandbox_id = _load_cached_sandbox_id()
    sandbox_created_new = False

    # 复用或创建沙箱
    if sandbox_id:
        logger.info("reusing_cached_sandbox", sandbox_id=sandbox_id)
        try:
            sandbox = SandboxSync.connect(
                sandbox_id=sandbox_id,
                connection_config=connection_config,
                skip_health_check=True,
            )

            # 验证沙箱是否存活
            reuse_ready = False
            for attempt in range(1, REUSE_SANDBOX_RETRIES + 1):
                try:
                    result = sandbox.commands.run("echo 'sandbox_ok'")
                    if result.exit_code == 0 or result.exit_code is None:
                        reuse_ready = True
                        break
                except Exception as e:
                    logger.warning("reuse_test_error", attempt=attempt, error=str(e))
                    import time
                    time.sleep(2)

            if reuse_ready:
                logger.info("sandbox_reused", sandbox_id=sandbox.id)
            else:
                logger.warning("cached_sandbox_dead", sandbox_id=sandbox_id)
                _clear_sandbox_cache()
                sandbox_id = None

        except Exception as e:
            logger.warning("sandbox_reuse_failed", error=str(e))
            _clear_sandbox_cache()
            sandbox_id = None

    if sandbox_id is None:
        logger.info("creating_new_sandbox", image=SANDBOX_IMAGE)
        try:
            # 创建沙箱（公共参数）
            create_kwargs = {
                "image": SANDBOX_IMAGE,
                "ready_timeout": SANDBOX_READY_TIMEOUT,
                "skip_health_check": True,
            }
            if connection_config:
                create_kwargs["connection_config"] = connection_config

            sandbox = SandboxSync.create(**create_kwargs)
            logger.info("sandbox_created", sandbox_id=sandbox.id, source="conversation")
            _save_sandbox_id(sandbox.id)

            # 验证沙箱是否就绪
            sandbox_ready = False
            for attempt in range(1, MAX_SANDBOX_WAIT_RETRIES + 1):
                logger.info("sandbox_validation_attempt", sandbox_id=sandbox.id, attempt=attempt)
                try:
                    result = sandbox.commands.run("echo 'sandbox_ready'")
                    if result.exit_code == 0 or result.exit_code is None:
                        sandbox_ready = True
                        break
                except Exception as e:
                    logger.warning("sandbox_test_error", attempt=attempt, error=str(e))

                if not sandbox_ready:
                    import time
                    time.sleep(5)

            if not sandbox_ready:
                raise RuntimeError(f"Sandbox not ready after {MAX_SANDBOX_WAIT_RETRIES} attempts")

            logger.info("sandbox_finally_ready", sandbox_id=sandbox.id, attempts=attempt)

        except Exception as e:
            error_msg = str(e)
            logger.error("sandbox_creation_failed", error=error_msg)

            if "not found" in error_msg.lower() or "image" in error_msg.lower():
                raise RuntimeError(f"镜像不存在: {SANDBOX_IMAGE}\n请先构建: cd docker && bash build.sh")

            raise RuntimeError(f"Sandbox creation failed: {error_msg}")

    logger.info("sandbox_ready", sandbox_id=sandbox.id)

    # 创建 backend
    backend = OpenSandboxBackend(sandbox=sandbox, timeout=config.get("timeout", 60 * 60))
    logger.info("sandbox_backend_created", sandbox_id=sandbox.id)

    # 创建工作目录
    backend.execute(f"mkdir -p {' '.join(SANDBOX_DIRS.values())}")
    logger.info("work_directories_created")

    # 上传必要文件
    _upload_files_to_sandbox(backend)

    return backend


def _upload_files_to_sandbox(backend: OpenSandboxBackend) -> None:
    """上传必要文件到沙箱。"""
    logger.info("uploading_files_to_sandbox")

    # 1. 上传 AGENTS.md（长期记忆指令）
    agents_md_local = Path(__file__).parent.parent / "AGENTS.md"
    if agents_md_local.exists():
        try:
            content = agents_md_local.read_text(encoding="utf-8")
            backend.write("/memories/AGENTS.md", content)
            logger.info("agents_md_uploaded", local_path=str(agents_md_local), sandbox_path="/memories/AGENTS.md")
        except Exception as e:
            logger.warning("agents_md_upload_failed", error=str(e))
    else:
        logger.warning("agents_md_not_found", path=str(agents_md_local))

    # 2. 上传技能目录（整个 skills/ 目录）
    skills_dir_local = Path(__file__).parent.parent / "skills"
    if skills_dir_local.exists() and skills_dir_local.is_dir():
        try:
            # 创建沙箱技能目录结构
            backend.execute("mkdir -p /skills/main /skills/trend /skills/security /skills/community /skills/compliance")

            # 递归上传所有技能
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

                    # 创建目录
                    backend.execute(f"mkdir -p {sandbox_skill_dir}")

                    # 上传 SKILL.md
                    skill_md = skill_dir / "SKILL.md"
                    if skill_md.exists():
                        content = skill_md.read_text(encoding="utf-8")
                        backend.write(f"{sandbox_skill_dir}/SKILL.md", content)
                        uploaded_count += 1
                        logger.info("skill_md_uploaded", skill_name=skill_name, scope=scope_name)

                    # 上传 scripts 目录中的脚本
                    scripts_dir = skill_dir / "scripts"
                    if scripts_dir.exists() and scripts_dir.is_dir():
                        backend.execute(f"mkdir -p {sandbox_skill_dir}/scripts")
                        for script_file in scripts_dir.glob("*.py"):
                            content = script_file.read_text(encoding="utf-8")
                            backend.write(f"{sandbox_skill_dir}/scripts/{script_file.name}", content)
                            uploaded_count += 1
                            logger.info("skill_script_uploaded", script=script_file.name, skill=skill_name)

            logger.info("skills_uploaded", total_files=uploaded_count)
        except Exception as e:
            logger.warning("skills_upload_failed", error=str(e))
    else:
        logger.info("skills_dir_not_found", path=str(skills_dir_local))

    logger.info("files_upload_completed")