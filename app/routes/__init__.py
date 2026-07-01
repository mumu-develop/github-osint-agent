"""API 路由模块。"""

from app.routes.download import router as download_router, set_sandbox_backend
from app.routes.scanner import router as scanner_router
from app.routes.findings import router as findings_router
from app.routes.scheduled_task import router as scheduled_task_router
from app.routes.channel import router as channel_router

__all__ = ["download_router", "set_sandbox_backend", "scanner_router", "findings_router", "scheduled_task_router", "channel_router"]