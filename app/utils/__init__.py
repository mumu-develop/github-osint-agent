"""Utils 模块 - 公共工具集合。"""

from app.utils.session import (
    get_session_id,
    get_session_path,
    get_session_report_path,
    get_session_analysis_path,
    get_session_workspace_path,
)

# 依赖解析工具
from app.utils.dep_parser import (
    DependencyParser,
    parse_dependencies,
    get_dep_ecosystem,
)

# OSV API 客户端
from app.utils.osv_client import (
    OSVClient,
    get_osv_client,
    query_osv,
)

# 严重程度映射
from app.utils.severity_mapper import (
    SeverityMapper,
    map_osv_severity,
    get_cvss_score,
    get_risk_type,
)

__all__ = [
    # Session 管理
    "get_session_id",
    "get_session_path",
    "get_session_report_path",
    "get_session_analysis_path",
    "get_session_workspace_path",
    # 依赖解析
    "DependencyParser",
    "parse_dependencies",
    "get_dep_ecosystem",
    # OSV 客户端
    "OSVClient",
    "get_osv_client",
    "query_osv",
    # 严重程度
    "SeverityMapper",
    "map_osv_severity",
    "get_cvss_score",
    "get_risk_type",
]