"""数据库模块 - 连接管理 + DAO 操作。

模块结构:
- base.py: 连接池管理 + JSON工具函数
- dao/: 各模型的 DAO 实现
- tables.py: 表结构初始化

使用方式:
    from app.database import get_db_pool, ScheduledTaskDAO

    task = await ScheduledTaskDAO.get_by_id(task_id)
"""

# 连接管理
from app.database.base import (
    get_db_pool,
    close_db_pool,
    parse_json_field,
    to_json_str,
)

# 表初始化
from app.database.tables import init_business_tables

# DAO 类
from app.database.dao import (
    ScheduledTaskDAO,
    ScheduledTaskExecutionDAO,
    ScanTaskDAO,
    FindingDAO,
    ScanSubTaskDAO,
    ScanReportDAO,
    ScanHistoryDAO,
    AlertChannelDAO,
)

__all__ = [
    "get_db_pool",
    "close_db_pool",
    "parse_json_field",
    "to_json_str",
    "init_business_tables",
    "ScheduledTaskDAO",
    "ScheduledTaskExecutionDAO",
    "ScanTaskDAO",
    "FindingDAO",
    "ScanSubTaskDAO",
    "ScanReportDAO",
    "ScanHistoryDAO",
    "AlertChannelDAO",
]