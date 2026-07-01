"""
趋势分析算法模块。

提供高潜力项目识别、增长趋势预测、报告组装等功能。
这些是 Tool 无法直接实现的复杂算法逻辑。

使用方式：
1. Tool 获取数据 → get_org_repos, get_star_history
2. 调用本模块函数处理数据 → calculate_potential_score, generate_trend_report

或者沙箱执行：
execute("python /skills/trend/repo-trend-analysis/analyze.py --data '{json}'")
"""

from datetime import datetime
from typing import Dict, Any, List, Optional


# ============================================================
# 高潜力项目评分模型
# ============================================================

# 评分权重配置
SCORE_WEIGHTS = {
    "growth_rate": 0.40,      # 增长率权重
    "stars": 0.20,            # Star 数权重
    "forks": 0.15,            # Fork 数权重
    "contributors": 0.15,     # 贡献者权重
    "recent_activity": 0.10,  # 近期活跃权重
}

# 指标阈值配置
THRESHOLDS = {
    "growth_rate_high": 10,    # 高增长率阈值 (%/周)
    "growth_rate_medium": 5,   # 中增长率阈值
    "stars_high": 1000,        # 高 Star 阈值
    "stars_medium": 100,       # 中 Star 阈值
    "forks_high": 100,         # 高 Fork 阈值
    "forks_medium": 20,        # 中 Fork 阈值
    "contributors_high": 50,   # 高贡献者阈值
    "contributors_medium": 10, # 中贡献者阈值
}


def calculate_potential_score(
    repo_data: Dict[str, Any],
    growth_rate: float,
    activity_score: float = 1.0
) -> Dict[str, Any]:
    """
    计算仓库的潜力评分。

    Tool 获取数据后，调用此函数进行综合评分。

    Args:
        repo_data: 仓库基本信息（from get_repo_stats）
        growth_rate: 增长率（from calculate_growth_rate）
        activity_score: 近期活跃评分（0-1）

    Returns:
        评分详情和总评分
    """
    # 各指标得分（0-10）
    scores = {}

    # 增长率得分
    if growth_rate > THRESHOLDS["growth_rate_high"]:
        scores["growth_rate"] = 10
    elif growth_rate > THRESHOLDS["growth_rate_medium"]:
        scores["growth_rate"] = 7
    elif growth_rate > 0:
        scores["growth_rate"] = 5
    else:
        scores["growth_rate"] = 0

    # Star 得分
    stars = repo_data.get("stars", 0)
    if stars > THRESHOLDS["stars_high"]:
        scores["stars"] = 10
    elif stars > THRESHOLDS["stars_medium"]:
        scores["stars"] = 7
    elif stars > 10:
        scores["stars"] = 5
    else:
        scores["stars"] = 3

    # Fork 得分
    forks = repo_data.get("forks", 0)
    if forks > THRESHOLDS["forks_high"]:
        scores["forks"] = 10
    elif forks > THRESHOLDS["forks_medium"]:
        scores["forks"] = 7
    elif forks > 5:
        scores["forks"] = 5
    else:
        scores["forks"] = 3

    # 贡献者得分
    contributors = repo_data.get("contributors_count", 0)
    if contributors > THRESHOLDS["contributors_high"]:
        scores["contributors"] = 10
    elif contributors > THRESHOLDS["contributors_medium"]:
        scores["contributors"] = 7
    elif contributors > 3:
        scores["contributors"] = 5
    else:
        scores["contributors"] = 3

    # 近期活跃得分
    scores["recent_activity"] = activity_score * 10

    # 加权总分
    total_score = sum(
        scores[key] * SCORE_WEIGHTS[key]
        for key in SCORE_WEIGHTS
    )

    # 确定潜力等级
    if total_score >= 8:
        level = "极高潜力"
    elif total_score >= 6:
        level = "高潜力"
    elif total_score >= 4:
        level = "中等潜力"
    else:
        level = "低潜力"

    return {
        "repo_name": repo_data.get("name", ""),
        "total_score": round(total_score, 2),
        "level": level,
        "scores_detail": scores,
        "stars": stars,
        "forks": forks,
        "growth_rate": growth_rate,
        "contributors": contributors,
    }


def rank_repos_by_potential(
    repo_scores: List[Dict[str, Any]],
    top_n: int = 10
) -> List[Dict[str, Any]]:
    """
    按潜力评分排序仓库。

    Args:
        repo_scores: 各仓库的评分列表
        top_n: 返回前 N 个

    Returns:
        排序后的高潜力项目列表
    """
    sorted_repos = sorted(
        repo_scores,
        key=lambda x: x.get("total_score", 0),
        reverse=True
    )
    return sorted_repos[:top_n]


def predict_growth_trend(
    history: List[Dict[str, Any]],
    days: int = 30
) -> Dict[str, Any]:
    """
    基于历史数据预测增长趋势。

    Args:
        history: Star 历史数据（from get_star_history）
        days: 预测天数

    Returns:
        预测结果
    """
    if not history or len(history) < 3:
        return {"prediction": "数据不足", "confidence": 0}

    # 计算平均增长速度
    total_stars = history[-1].get("stars", 0)
    first_stars = history[0].get("stars", 0)
    total_days = len(history)

    if total_days == 0 or first_stars == 0:
        return {"prediction": "无法预测", "confidence": 0}

    daily_growth = (total_stars - first_stars) / total_days

    # 预测未来增长
    predicted_growth = daily_growth * days
    predicted_total = total_stars + predicted_growth

    # 计算置信度（基于数据量）
    confidence = min(len(history) / 30, 1.0)  # 30天数据置信度最高

    # 判断趋势
    if daily_growth > 0.5:
        trend = "快速增长"
    elif daily_growth > 0.1:
        trend = "稳定增长"
    elif daily_growth > 0:
        trend = "缓慢增长"
    else:
        trend = "停滞"

    return {
        "current_stars": total_stars,
        "predicted_stars": round(predicted_total),
        "predicted_growth": round(predicted_growth),
        "daily_growth_rate": round(daily_growth, 2),
        "trend": trend,
        "confidence": round(confidence, 2),
        "prediction_period_days": days,
    }


# ============================================================
# 报告组装
# ============================================================

def generate_trend_report(
    ranked_repos: List[Dict[str, Any]],
    org_name: str,
    predictions: Optional[List[Dict[str, Any]]] = None
) -> str:
    """
    组装趋势分析报告（Markdown 格式）。

    Args:
        ranked_repos: 排序后的高潜力项目列表
        org_name: 组织名称
        predictions: 各项目的预测结果

    Returns:
        Markdown 报告内容
    """
    report_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        f"# 技术趋势分析报告",
        "",
        f"**组织**: {org_name}",
        f"**生成时间**: {report_time}",
        f"**分析仓库数**: {len(ranked_repos)}",
        "",
        "---",
        "",
        "## 高潜力项目排名",
        "",
        "| 排名 | 仓库名 | 潜力评分 | 潜力等级 | Star数 | Fork数 | 增长率 |",
        "|------|--------|----------|----------|--------|--------|--------|",
    ]

    for i, repo in enumerate(ranked_repos, 1):
        lines.append(
            f"| {i} | {repo.get('repo_name', '')} | "
            f"{repo.get('total_score', 0)} | {repo.get('level', '')} | "
            f"{repo.get('stars', 0)} | {repo.get('forks', 0)} | "
            f"{repo.get('growth_rate', 0):.1f}% |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 详细分析",
        "",
    ])

    for repo in ranked_repos[:3]:  # 前3个详细分析
        lines.extend([
            f"### {repo.get('repo_name', '')}",
            "",
            f"- **潜力评分**: {repo.get('total_score', 0)} ({repo.get('level', '')})",
            f"- **Star 数**: {repo.get('stars', 0)}",
            f"- **Fork 数**: {repo.get('forks', 0)}",
            f"- **贡献者数**: {repo.get('contributors', 0)}",
            f"- **增长率**: {repo.get('growth_rate', 0):.1f}%/周",
            "",
            "**评分明细**:",
        ])

        scores_detail = repo.get("scores_detail", {})
        for metric, score in scores_detail.items():
            lines.append(f"- {metric}: {score}/10")

        lines.append("")

    # 趋势预测部分
    if predictions:
        lines.extend([
            "---",
            "",
            "## 趋势预测",
            "",
        ])

        for pred in predictions[:3]:
            lines.extend([
                f"**{pred.get('repo_name', '')}**:",
                f"- 当前 Star: {pred.get('current_stars', 0)}",
                f"- 30天预测: {pred.get('predicted_stars', 0)}",
                f"- 趋势判断: {pred.get('trend', '')}",
                f"- 置信度: {pred.get('confidence', 0) * 100:.0f}%",
                "",
            ])

    lines.extend([
        "---",
        "",
        "## 建议",
        "",
        "1. 重点关注高潜力项目，考虑投入更多资源",
        "2. 跟踪快速增长项目的技术演进",
        "3. 分析潜力项目的成功因素",
        "",
        f"*报告生成于 {report_time}*",
    ])

    return "\n".join(lines)


__all__ = [
    "calculate_potential_score",
    "rank_repos_by_potential",
    "predict_growth_trend",
    "generate_trend_report",
]