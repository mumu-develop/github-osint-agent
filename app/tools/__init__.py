"""工具模块导出。

统一工具架构：
- 所有数据获取工具支持单仓库和多仓库
- 参数格式统一：repos="owner/repo" 或 repos="owner/repo1,owner/repo2"
"""

from app.tools.unified import (
    # 核心扫描工具
    scan_org,
    check_cve_repos,
    check_package_cve,
    scan_secrets,
    check_license,
    scan_copyright,
    check_community,
    # 统计工具
    get_issue_metrics,
    get_pr_metrics,
    get_contributor_activity,
    get_dependency_files,
    get_star_history,
    get_repo_stats,
    get_org_repos,
    # 计算工具
    calculate_growth_rate,
    # 工具分组
    scan_tools,
    metrics_tools,
    calc_tools,
    all_tools,
)

from app.tools.common import common_tools
from app.tools.skill_management import skill_tools
from app.tools.report import report_tools, get_sandbox_report_path

# 导出分组
__all__ = [
    # 统一扫描工具
    "scan_tools",
    "metrics_tools",
    "calc_tools",
    "all_tools",
    # 其他工具
    "common_tools",
    "skill_tools",
    "report_tools",
]

# 工具分组映射（供 loader.py 使用）
TOOL_GROUPS = {
    "scan": scan_tools,
    "metrics": metrics_tools,
    "calc": calc_tools,
    "common": common_tools,
    "skill": skill_tools,
    "report": report_tools,
}

# 按子智能体预配置的工具分组
SUBAGENT_TOOLS = {
    "security-analyzer": [
        scan_org,           # 组织级扫描
        check_cve_repos,    # CVE检查（仓库）
        check_package_cve,  # CVE查询（单包）
        scan_secrets,       # 敏感信息扫描
        get_dependency_files,  # 依赖文件获取
        get_sandbox_report_path,  # 报告路径生成
    ],
    "compliance-analyzer": [
        scan_org,           # 组织级扫描
        check_license,      # 许可证检查
        scan_copyright,     # 版权扫描
        get_sandbox_report_path,  # 报告路径生成
    ],
    "community-analyzer": [
        get_org_repos,      # 组织仓库列表（组织级任务必须）
        check_community,    # 社区健康检查
        get_issue_metrics,  # Issue统计
        get_pr_metrics,     # PR统计
        get_contributor_activity,  # 贡献者活跃度
        get_repo_stats,     # 仓库基本统计
        get_sandbox_report_path,  # 报告路径生成
    ],
    "trend-analyzer": [
        get_org_repos,      # 组织仓库列表
        get_star_history,   # Star历史
        get_repo_stats,     # 仓库统计
        calculate_growth_rate,  # 增长率计算
        get_sandbox_report_path,  # 报告路径生成
    ],
}