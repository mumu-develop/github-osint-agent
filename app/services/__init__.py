"""服务层模块。

提供业务服务组件:
- ScanLockService: 分布式锁服务
"""

from app.services.scan_lock import ScanLockService

__all__ = ["ScanLockService"]