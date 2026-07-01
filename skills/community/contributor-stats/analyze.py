"""
社区健康分析算法模块。

提供健康评分模型、活跃度分析、报告组装等功能。
这些是 Tool 无法直接实现的复杂算法逻辑。

使用方式：
1. Tool 获取数据 → get_issue_metrics, get_pr_metrics, get_contributor_activity
2. 调用本模块函数处理数据 → calculate_health_score, generate_community_report
"""

from datetime import datetime
from typing import Dict, Any, List, Optional


# ============================================================
# 健康评分模型
# ============================================================

# 评分权重配置
HEALTH_WEIGHTS = {
    "issue_response": 0.25,      # Issue 响应速度权重
    "pr_merge": 0.25,            # PR 合并速度权重
    "contributors": 0.20,        # 活跃贡献者权重
    "commits": 0.15,             # 近期提交数权重
    "issue_open_rate": 0.15,     # Issue 打开率权重
}

# 阈值配置
HEALTH_THRESHOLDS = {
    "issue_close_hours_fast": 24,      # 快速响应阈值（小时）
    "issue_close_hours_medium": 72,    # 中等响应阈值
    "issue_close_hours_slow": 168,     # 慢速响应阈值
    "pr_merge_hours_fast": 48,         # 快速合并阈值（小时）
    "pr_merge_hours_medium": 168,      # 中等合并阈值
    "pr_merge_hours_slow": 720,        # 慢速合并阈值
    "contributors_high": 20,            # 高贡献者阈值
    "contributors_medium": 10,          # 中贡献者阈值
    "contributors_low": 5,              # 低贡献者阈值
    "commits_high": 100,                # 高提交阈值
    "commits_medium": 50,               # 中提交阈值
    "commits_low": 20,                  # 低提交阈值
    "issue_open_rate_good": 10,         # 良好打开率阈值 (%)
    "issue_open_rate_medium": 20,       # 中等打开率阈值
}


def calculate_health_score(
    issue_metrics: Dict[str, Any],
    pr_metrics: Dict[str, Any],
    contributor_activity: Dict[str, Any]
) -> Dict[str, Any]:
    """
    计算社区健康评分。

    Tool 获取数据后，调用此函数进行综合评分。

    Args:
        issue_metrics: Issue 统计（from get_issue_metrics）
        pr_metrics: PR 统计（from get_pr_metrics）
        contributor_activity: 贡献者活跃度（from get_contributor_activity）

    Returns:
        健康评分详情和总评分
    """
    scores = {}

    # Issue 响应速度得分
    avg_close_hours = issue_metrics.get("avg_close_hours", 0)
    if avg_close_hours == 0:  # 无关闭记录
        scores["issue_response"] = 5  # 中等分
    elif avg_close_hours < HEALTH_THRESHOLDS["issue_close_hours_fast"]:
        scores["issue_response"] = 10
    elif avg_close_hours < HEALTH_THRESHOLDS["issue_close_hours_medium"]:
        scores["issue_response"] = 7
    elif avg_close_hours < HEALTH_THRESHOLDS["issue_close_hours_slow"]:
        scores["issue_response"] = 4
    else:
        scores["issue_response"] = 2

    # PR 合并速度得分
    avg_merge_hours = pr_metrics.get("avg_merge_hours", 0)
    if avg_merge_hours == 0:
        scores["pr_merge"] = 5
    elif avg_merge_hours < HEALTH_THRESHOLDS["pr_merge_hours_fast"]:
        scores["pr_merge"] = 10
    elif avg_merge_hours < HEALTH_THRESHOLDS["pr_merge_hours_medium"]:
        scores["pr_merge"] = 7
    elif avg_merge_hours < HEALTH_THRESHOLDS["pr_merge_hours_slow"]:
        scores["pr_merge"] = 4
    else:
        scores["pr_merge"] = 2

    # 贡献者活跃度得分
    active_contributors = contributor_activity.get("active_contributors", 0)
    if active_contributors > HEALTH_THRESHOLDS["contributors_high"]:
        scores["contributors"] = 10
    elif active_contributors > HEALTH_THRESHOLDS["contributors_medium"]:
        scores["contributors"] = 7
    elif active_contributors > HEALTH_THRESHOLDS["contributors_low"]:
        scores["contributors"] = 4
    else:
        scores["contributors"] = 2

    # 近期提交数得分
    commits = contributor_activity.get("commits", 0)
    if commits > HEALTH_THRESHOLDS["commits_high"]:
        scores["commits"] = 10
    elif commits > HEALTH_THRESHOLDS["commits_medium"]:
        scores["commits"] = 7
    elif commits > HEALTH_THRESHOLDS["commits_low"]:
        scores["commits"] = 4
    else:
        scores["commits"] = 2

    # Issue 打开率得分
    total_issues = issue_metrics.get("total", 0)
    open_issues = issue_metrics.get("open", 0)
    if total_issues > 0:
        open_rate = (open_issues / total_issues) * 100
    else:
        open_rate = 0

    if open_rate < HEALTH_THRESHOLDS["issue_open_rate_good"]:
        scores["issue_open_rate"] = 10
    elif open_rate < HEALTH_THRESHOLDS["issue_open_rate_medium"]:
        scores["issue_open_rate"] = 7
    elif open_rate < 30:
        scores["issue_open_rate"] = 4
    else:
        scores["issue_open_rate"] = 2

    # 加权总分
    total_score = sum(
        scores[key] * HEALTH_WEIGHTS[key]
        for key in HEALTH_WEIGHTS
    )

    # 确定健康等级
    if total_score >= 80:
        level = "🟢 健康"
        status = "活跃维护，保持现状"
    elif total_score >= 60:
        level = "🟡 一般"
        status = "有待改进，关注响应速度"
    elif total_score >= 40:
        level = "🟠 警告"
        status = "维护不足，增加贡献者"
    else:
        level = "🔴 危险"
        status = "停滞风险，需要重新激活"

    return {
        "total_score": round(total_score, 2),
        "level": level,
        "status": status,
        "scores_detail": scores,
        "metrics": {
            "issue_avg_close_hours": avg_close_hours,
            "pr_avg_merge_hours": avg_merge_hours,
            "active_contributors": active_contributors,
            "recent_commits": commits,
            "issue_open_rate": round(open_rate, 2),
        },
    }


def generate_improvement_suggestions(health_result: Dict[str, Any]) -> List[str]:
    """
    根据健康评分生成改进建议。

    Args:
        health_result: 健康评分结果

    Returns:
        建议列表
    """
    suggestions = []
    scores_detail = health_result.get("scores_detail", {})

    # Issue 响应慢
    if scores_detail.get("issue_response", 10) < 7:
        suggestions.append("增加 Issue 处理人员或改进处理流程")

    # PR 合并慢
    if scores_detail.get("pr_merge", 10) < 7:
        suggestions.append("加快 PR 审核速度，增加审核人员")

    # 贡献者少
    if scores_detail.get("contributors", 10) < 7:
        suggestions.append("吸引更多开发者参与，改善贡献者引导文档")

    # 提交少
    if scores_detail.get("commits", 10) < 7:
        suggestions.append("鼓励社区提交，举办贡献活动")

    # Issue 打开率高
    if scores_detail.get("issue_open_rate", 10) < 7:
        suggestions.append("清理旧 Issue，关闭无效问题")

    if not suggestions:
        suggestions.append("继续保持当前维护水平")

    return suggestions


# ============================================================
# 报告组装
# ============================================================

def generate_community_report(
    health_result: Dict[str, Any],
    owner: str,
    repo: str,
    suggestions: List[str]
) -> str:
    """
    组装社区健康报告（Markdown 格式）。

    Args:
        health_result: 健康评分结果
        owner: 仓库所有者
        repo: 仓库名
        suggestions: 改进建议

    Returns:
        Markdown 报告内容
    """
    report_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    metrics = health_result.get("metrics", {})
    scores_detail = health_result.get("scores_detail", {})

    lines = [
        f"# 社区健康分析报告",
        "",
        f"**仓库**: {owner}/{repo}",
        f"**生成时间**: {report_time}",
        "",
        "---",
        "",
        "## 健康评分",
        "",
        f"**总评分**: {health_result.get('total_score', 0)}/100",
        f"**健康等级**: {health_result.get('level', '')}",
        f"**状态描述**: {health_result.get('status', '')}",
        "",
        "### 评分明细",
        "",
        "| 指标 | 得分 | 权重 | 加权得分 |",
        "|------|------|------|----------|",
    ]

    for key, weight in HEALTH_WEIGHTS.items():
        score = scores_detail.get(key, 0)
        weighted = score * weight
        metric_name = {
            "issue_response": "Issue 响应速度",
            "pr_merge": "PR 合并速度",
            "contributors": "活跃贡献者数",
            "commits": "近期提交数",
            "issue_open_rate": "Issue 打开率",
        }.get(key, key)

        lines.append(
            f"| {metric_name} | {score}/10 | {weight * 100}% | {weighted:.2f} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 详细指标",
        "",
        f"- **Issue 平均关闭时间**: {metrics.get('issue_avg_close_hours', 0):.1f} 小时",
        f"- **PR 平均合并时间**: {metrics.get('pr_avg_merge_hours', 0):.1f} 小时",
        f"- **活跃贡献者数**: {metrics.get('active_contributors', 0)} 人",
        f"- **近期提交数**: {metrics.get('recent_commits', 0)} 次",
        f"- **Issue 打开率**: {metrics.get('issue_open_rate', 0):.1f}%",
        "",
        "---",
        "",
        "## 改进建议",
        "",
    ])

    for i, suggestion in enumerate(suggestions, 1):
        lines.append(f"{i}. {suggestion}")

    lines.extend([
        "",
        f"*报告生成于 {report_time}*",
    ])

    return "\n".join(lines)


__all__ = [
    "calculate_health_score",
    "generate_improvement_suggestions",
    "aggregate_multi_repo_community",
    "generate_community_report",
    "generate_multi_repo_community_report",
]


# ============================================================
# 多仓库聚合函数
# ============================================================

def aggregate_multi_repo_community(
    findings_by_repo: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """
    聚合多仓库的社区健康数据，按仓库和健康等级双重分类。

    Args:
        findings_by_repo: 按仓库分组的数据
            {
                "sofastack/sofa-rpc": {
                    "issue_metrics": {...},
                    "pr_metrics": {...},
                    "contributor_activity": {...}
                },
                ...
            }

    Returns:
        聚合结果，包含：
        - by_repo: 每个仓库的健康数据
        - total_summary: 所有仓库汇总统计
        - health_distribution: 健康等级分布
    """
    by_repo: Dict[str, Dict] = {}
    health_counts = {"健康": 0, "一般": 0, "警告": 0, "危险": 0}
    total_score = 0

    for repo_name, findings in findings_by_repo.items():
        issue_metrics = findings.get("issue_metrics", {})
        pr_metrics = findings.get("pr_metrics", {})
        contributor_activity = findings.get("contributor_activity", {})

        # 单仓库健康评分
        health_result = calculate_health_score(issue_metrics, pr_metrics, contributor_activity)
        suggestions = generate_improvement_suggestions(health_result)

        by_repo[repo_name] = {
            "health_result": health_result,
            "suggestions": suggestions,
            "metrics": {
                "issue_avg_close_hours": health_result.get("metrics", {}).get("issue_avg_close_hours", 0),
                "pr_avg_merge_hours": health_result.get("metrics", {}).get("pr_avg_merge_hours", 0),
                "active_contributors": health_result.get("metrics", {}).get("active_contributors", 0),
            }
        }

        # 累计健康等级
        level = health_result.get("level", "🟡 一般")
        level_key = level.replace("🟢 ", "").replace("🟡 ", "").replace("🟠 ", "").replace("🔴 ", "")
        health_counts[level_key] = health_counts.get(level_key, 0) + 1
        total_score += health_result.get("total_score", 0)

    # 计算平均健康评分
    avg_score = total_score / len(findings_by_repo) if findings_by_repo else 0

    # 找出低健康仓库
    low_health_repos = [
        (repo, data["health_result"]["total_score"])
        for repo, data in by_repo.items()
        if data["health_result"]["total_score"] < 60
    ]
    low_health_repos.sort(key=lambda x: x[1], reverse=False)

    return {
        "by_repo": by_repo,
        "total_summary": {
            "repos_analyzed": len(findings_by_repo),
            "avg_health_score": round(avg_score, 2),
            "health_counts": health_counts,
        },
        "health_distribution": health_counts,
        "low_health_repos": low_health_repos[:5],
    }


def generate_multi_repo_community_report(
    aggregated: Dict[str, Any],
    repos: List[str]
) -> str:
    """
    组装多仓库社区健康汇总报告（Markdown 格式）。

    Args:
        aggregated: 多仓库聚合数据
        repos: 仓库列表

    Returns:
        Markdown 报告内容
    """
    report_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_summary = aggregated.get("total_summary", {})
    by_repo = aggregated.get("by_repo", {})
    health_dist = aggregated.get("health_distribution", {})
    low_health = aggregated.get("low_health_repos", [])

    avg_score = total_summary.get("avg_health_score", 0)
    if avg_score >= 80:
        status = "✅ 整体健康"
    elif avg_score >= 60:
        status = "🟡 存在风险"
    else:
        status = "🔴 需关注"

    lines = [
        f"# 多仓库社区健康汇总报告",
        "",
        f"**分析仓库数**: {len(repos)}",
        f"**生成时间**: {report_time}",
        f"**平均健康评分**: {avg_score}/100",
        f"**整体状态**: {status}",
        "",
        "---",
        "",
        "## 健康等级分布",
        "",
        f"- 🟢 健康: {health_dist.get('健康', 0)} 个仓库",
        f"- 🟡 一般: {health_dist.get('一般', 0)} 个仓库",
        f"- 🟠 警告: {health_dist.get('警告', 0)} 个仓库",
        f"- 🔴 危险: {health_dist.get('危险', 0)} 个仓库",
        "",
    ]

    # 低健康仓库
    if low_health:
        lines.extend([
            "---",
            "",
            "## 需关注的仓库",
            "",
            "| 仓库 | 健康评分 | 主要问题 |",
            "|------|----------|----------|",
        ])
        for repo, score in low_health[:10]:
            repo_data = by_repo.get(repo, {})
            suggestions = repo_data.get("suggestions", [])
            main_issue = suggestions[0] if suggestions else "未知"
            lines.append(f"| {repo} | {score}/100 | {main_issue[:30]} |")
        lines.append("")

    # 各仓库详情
    lines.extend([
        "---",
        "",
        "## 各仓库健康状态",
        "",
    ])

    for repo_name in repos:
        repo_data = by_repo.get(repo_name, {})
        health_result = repo_data.get("health_result", {})
        score = health_result.get("total_score", 0)
        level = health_result.get("level", "🟡 一般")

        lines.append(
            f"- {level} **{repo_name}**: {score}/100"
        )

    # 总结建议
    lines.extend([
        "",
        "---",
        "",
        "## 总结与建议",
        "",
    ])

    if avg_score < 60:
        lines.extend([
            "⚠️ **社区健康风险较高，建议：**",
            "",
            f"1. 优先激活 {len(low_health)} 个低健康仓库",
            f"2. 增加 Issue 和 PR 处理人员",
            f"3. 吸引更多贡献者参与",
        ])
    elif avg_score < 80:
        lines.append("🟡 **部分仓库社区活跃度不足，建议改进响应速度。**")
    else:
        lines.append("✅ **多仓库整体社区健康状态良好。**")

    lines.extend([
        "",
        f"*报告生成于 {report_time}*",
    ])

    return "\n".join(lines)