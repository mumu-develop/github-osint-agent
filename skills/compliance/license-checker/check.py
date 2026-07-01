"""
合规检查算法模块。

提供许可证兼容性分析、合规风险评估、报告组装等功能。
这些是 Tool 无法直接实现的复杂算法逻辑。

使用方式：
1. Tool 获取数据 → check_license, scan_copyright
2. 调用本模块函数处理数据 → analyze_compatibility, generate_compliance_report
"""

from datetime import datetime
from typing import Dict, Any, List, Optional


# ============================================================
# 许可证兼容性分析
# ============================================================

# 许可证类型定义
LICENSE_TYPES = {
    "MIT": {"type": "open", "commercial": True, "restrictions": ["保留声明"]},
    "Apache-2.0": {"type": "open", "commercial": True, "restrictions": ["保留声明", "专利授权"]},
    "BSD-3-Clause": {"type": "open", "commercial": True, "restrictions": ["保留声明"]},
    "BSD-2-Clause": {"type": "open", "commercial": True, "restrictions": ["保留声明"]},
    "LGPL-3.0": {"type": "semi-open", "commercial": True, "restrictions": ["动态链接可商用", "修改需开源"]},
    "LGPL-2.1": {"type": "semi-open", "commercial": True, "restrictions": ["动态链接可商用"]},
    "GPL-3.0": {"type": "restrictive", "commercial": False, "restrictions": ["必须开源"]},
    "GPL-2.0": {"type": "restrictive", "commercial": False, "restrictions": ["必须开源"]},
    "AGPL-3.0": {"type": "restrictive", "commercial": False, "restrictions": ["网络服务需开源"]},
    "MPL-2.0": {"type": "semi-open", "commercial": True, "restrictions": ["文件级开源"]},
    "Unlicense": {"type": "open", "commercial": True, "restrictions": []},
    "NO_LICENSE": {"type": "unknown", "commercial": False, "restrictions": ["默认版权保护"]},
}

# 许可证兼容性矩阵（上游 → 下游）
COMPATIBILITY_MATRIX = {
    "MIT": ["MIT", "Apache-2.0", "GPL-3.0", "BSD-3-Clause", "商业"],
    "Apache-2.0": ["Apache-2.0", "GPL-3.0", "商业"],
    "BSD-3-Clause": ["BSD-3-Clause", "MIT", "Apache-2.0", "GPL-3.0", "商业"],
    "LGPL-3.0": ["LGPL-3.0", "GPL-3.0"],
    "GPL-3.0": ["GPL-3.0"],
    "AGPL-3.0": ["AGPL-3.0"],
    "MPL-2.0": ["MPL-2.0", "GPL-3.0"],
}


def analyze_license_compatibility(
    upstream_license: str,
    downstream_license: Optional[str] = None
) -> Dict[str, Any]:
    """
    分析许可证兼容性。

    Args:
        upstream_license: 上游（被使用）项目的许可证
        downstream_license: 下游（使用）项目的许可证（可选）

    Returns:
        兼容性分析结果
    """
    license_type = LICENSE_TYPES.get(upstream_license, LICENSE_TYPES["NO_LICENSE"])

    result = {
        "license": upstream_license,
        "type": license_type["type"],
        "commercial_compatible": license_type["commercial"],
        "restrictions": license_type["restrictions"],
    }

    # 如果指定了下游许可证，检查兼容性
    if downstream_license:
        compatible_list = COMPATIBILITY_MATRIX.get(upstream_license, [])
        is_compatible = downstream_license in compatible_list or downstream_license == "商业"

        result["downstream_license"] = downstream_license
        result["is_compatible"] = is_compatible
        result["compatible_downstream"] = compatible_list

        if not is_compatible:
            result["compatibility_issue"] = (
                f"{upstream_license} 不兼容 {downstream_license}。"
                f"可选下游许可证: {compatible_list}"
            )

    return result


def assess_compliance_risk(
    license_info: Dict[str, Any],
    copyright_info: Dict[str, Any]
) -> Dict[str, Any]:
    """
    评估合规风险等级。

    Args:
        license_info: 许可证信息（from check_license）
        copyright_info: 版权信息（from scan_copyright）

    Returns:
        风险评估结果
    """
    risks = []
    risk_level = "compliant"

    # 检查许可证是否存在
    license_type = license_info.get("license", "NO_LICENSE")
    if license_type == "NO_LICENSE" or not license_info.get("has_license", True):
        risks.append("无许可证文件，默认受版权保护")
        risk_level = "high"

    # 检查许可证类型风险
    license_config = LICENSE_TYPES.get(license_type, LICENSE_TYPES["NO_LICENSE"])
    if license_config["type"] == "restrictive":
        risks.append(f"{license_type} 许可证要求开源，商用需谨慎")
        risk_level = max(risk_level, "medium", key=lambda x: ["compliant", "low", "medium", "high"].index(x))

    # 检查版权声明
    if not copyright_info.get("found", False):
        risks.append("缺少版权声明文件")
        risk_level = max(risk_level, "low", key=lambda x: ["compliant", "low", "medium", "high"].index(x))

    # 风险等级映射
    risk_labels = {
        "high": "🔴 高风险",
        "medium": "🟠 中风险",
        "low": "🟡 低风险",
        "compliant": "🟢 合规",
    }

    return {
        "risk_level": risk_level,
        "risk_label": risk_labels.get(risk_level, "未知"),
        "risks": risks,
        "license_type": license_config["type"],
        "commercial_compatible": license_config["commercial"],
        "restrictions": license_config["restrictions"],
    }


# ============================================================
# 报告组装
# ============================================================

def generate_compliance_report(
    license_info: Dict[str, Any],
    copyright_info: Dict[str, Any],
    risk_assessment: Dict[str, Any],
    owner: str,
    repo: str
) -> str:
    """
    组装合规分析报告（Markdown 格式）。

    Args:
        license_info: 许可证信息
        copyright_info: 版权信息
        risk_assessment: 风险评估
        owner: 仓库所有者
        repo: 仓库名

    Returns:
        Markdown 报告内容
    """
    report_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        f"# 合规审计报告",
        "",
        f"**仓库**: {owner}/{repo}",
        f"**生成时间**: {report_time}",
        f"**合规状态**: {risk_assessment.get('risk_label', '')}",
        "",
        "---",
        "",
        "## 许可证信息",
        "",
        f"- **许可证类型**: {license_info.get('license', '无')}",
        f"- **许可证类型**: {risk_assessment.get('license_type', '未知')}",
        f"- **商用兼容**: {'✅ 允许' if risk_assessment.get('commercial_compatible', False) else '❌ 禁止'}",
        "",
    ]

    restrictions = risk_assessment.get("restrictions", [])
    if restrictions:
        lines.extend([
            "### 使用限制",
            "",
        ])
        for restriction in restrictions:
            lines.append(f"- {restriction}")
        lines.append("")

    # 版权声明部分
    lines.extend([
        "---",
        "",
        "## 版权声明",
        "",
    ])

    if copyright_info.get("found", False):
        holders = copyright_info.get("holders", [])
        files_count = copyright_info.get("files_count", 0)

        lines.extend([
            f"- **状态**: ✅ 有版权声明",
            f"- **版权归属**: {', '.join(holders) if holders else '未知'}",
            f"- **声明文件数**: {files_count}",
            "",
        ])
    else:
        lines.extend([
            f"- **状态**: ⚠️ 缺少版权声明",
            f"- **建议**: 添加版权声明文件，明确归属",
            "",
        ])

    # 兼容性分析
    if license_info.get("license"):
        compat = analyze_license_compatibility(license_info.get("license", ""))

        lines.extend([
            "---",
            "",
            "## 许可证兼容性",
            "",
            f"- **许可证**: {compat.get('license', '')}",
            f"- **类型**: {compat.get('type', '')}",
            "",
            "### 可兼容的下游许可证",
            "",
        ])

        for downstream in compat.get("compatible_downstream", []):
            lines.append(f"- {downstream}")

        lines.append("")

    # 风险与建议
    lines.extend([
        "---",
        "",
        "## 风险与建议",
        "",
    ])

    risks = risk_assessment.get("risks", [])
    if risks:
        lines.append("### 发现的风险")
        lines.append("")
        for risk in risks:
            lines.append(f"- {risk}")
        lines.append("")

    lines.extend([
        "### 建议",
        "",
    ])

    if risk_assessment.get("risk_level") == "high":
        lines.append("1. 🔴 立即添加许可证文件")
        lines.append("2. 明确版权归属")
        lines.append("3. 如需商用，选择兼容许可证")
    elif risk_assessment.get("risk_level") == "medium":
        lines.append("1. 🟠 评估商用场景的合规性")
        lines.append("2. 确认开源义务范围")
    elif risk_assessment.get("risk_level") == "low":
        lines.append("1. 🟡 补充版权声明文件")
    else:
        lines.append("1. ✅ 保持当前合规状态")

    lines.extend([
        "",
        f"*报告生成于 {report_time}*",
    ])

    return "\n".join(lines)


__all__ = [
    "analyze_license_compatibility",
    "assess_compliance_risk",
    "aggregate_multi_repo_compliance",
    "generate_compliance_report",
    "generate_multi_repo_compliance_report",
]


# ============================================================
# 多仓库聚合函数
# ============================================================

def aggregate_multi_repo_compliance(
    findings_by_repo: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """
    聚合多仓库的合规数据，按仓库和风险等级双重分类。

    Args:
        findings_by_repo: 按仓库分组的数据
            {
                "sofastack/sofa-rpc": {
                    "license_findings": [...],
                    "copyright_info": {...}
                },
                ...
            }

    Returns:
        聚合结果，包含：
        - by_repo: 每个仓库的合规数据
        - total_summary: 所有仓库汇总统计
        - license_distribution: 许可证分布统计
    """
    by_repo: Dict[str, Dict] = {}
    license_counts: Dict[str, int] = {}
    risk_counts = {"high": 0, "medium": 0, "low": 0, "compliant": 0}

    for repo_name, findings in findings_by_repo.items():
        license_info = findings.get("license_info", findings.get("license_findings", {}))
        copyright_info = findings.get("copyright_info", {})

        # 单仓库风险评估
        risk_assessment = assess_compliance_risk(license_info, copyright_info)
        by_repo[repo_name] = {
            "license_info": license_info,
            "copyright_info": copyright_info,
            "risk_assessment": risk_assessment,
        }

        # 累计许可证类型
        license_type = license_info.get("license", "NO_LICENSE")
        license_counts[license_type] = license_counts.get(license_type, 0) + 1

        # 累计风险等级
        risk_level = risk_assessment.get("risk_level", "compliant")
        risk_counts[risk_level] = risk_counts.get(risk_level, 0) + 1

    # 计算合规评分
    total_repos = len(findings_by_repo)
    compliant_rate = risk_counts.get("compliant", 0) / total_repos if total_repos > 0 else 0

    # 找出高风险仓库
    high_risk_repos = [
        (repo, data["risk_assessment"]["risk_level"])
        for repo, data in by_repo.items()
        if data["risk_assessment"]["risk_level"] in ["high", "medium"]
    ]

    return {
        "by_repo": by_repo,
        "total_summary": {
            "repos_analyzed": total_repos,
            "compliant_rate": compliant_rate,
            "risk_counts": risk_counts,
        },
        "license_distribution": license_counts,
        "high_risk_repos": high_risk_repos,
    }


def generate_multi_repo_compliance_report(
    aggregated: Dict[str, Any],
    repos: List[str]
) -> str:
    """
    组装多仓库合规汇总报告（Markdown 格式）。

    Args:
        aggregated: 多仓库聚合数据
        repos: 仓库列表

    Returns:
        Markdown 报告内容
    """
    report_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_summary = aggregated.get("total_summary", {})
    license_dist = aggregated.get("license_distribution", {})
    by_repo = aggregated.get("by_repo", {})
    high_risk = aggregated.get("high_risk_repos", [])

    compliant_rate = total_summary.get("compliant_rate", 0)
    if compliant_rate >= 0.8:
        status = "✅ 整体合规"
    elif compliant_rate >= 0.6:
        status = "🟡 存在风险"
    else:
        status = "🔴 高风险"

    lines = [
        f"# 多仓库合规汇总报告",
        "",
        f"**分析仓库数**: {len(repos)}",
        f"**生成时间**: {report_time}",
        f"**合规率**: {compliant_rate * 100:.1f}%",
        f"**整体状态**: {status}",
        "",
        "---",
        "",
        "## 汇总统计",
        "",
        f"- 🔴 高风险: {total_summary.get('risk_counts', {}).get('high', 0)} 个仓库",
        f"- 🟠 中风险: {total_summary.get('risk_counts', {}).get('medium', 0)} 个仓库",
        f"- 🟡 低风险: {total_summary.get('risk_counts', {}).get('low', 0)} 个仓库",
        f"- 🟢 合规: {total_summary.get('risk_counts', {}).get('compliant', 0)} 个仓库",
        "",
    ]

    # 许可证分布
    if license_dist:
        lines.extend([
            "---",
            "",
            "## 许可证分布",
            "",
            "| 许可证 | 仓库数 |",
            "|--------|--------|",
        ])
        for license_type, count in sorted(license_dist.items(), key=lambda x: -x[1]):
            lines.append(f"| {license_type} | {count} |")
        lines.append("")

    # 高风险仓库
    if high_risk:
        lines.extend([
            "---",
            "",
            "## 需关注的仓库",
            "",
            "| 仓库 | 风险等级 | 主要问题 |",
            "|------|----------|----------|",
        ])
        for repo, risk_level in high_risk[:10]:
            repo_data = by_repo.get(repo, {})
            risks = repo_data.get("risk_assessment", {}).get("risks", [])
            main_issue = risks[0] if risks else "未知"
            lines.append(f"| {repo} | {risk_level} | {main_issue[:30]} |")
        lines.append("")

    # 各仓库详情摘要
    lines.extend([
        "---",
        "",
        "## 各仓库合规状态",
        "",
    ])

    risk_labels = {
        "high": "🔴",
        "medium": "🟠",
        "low": "🟡",
        "compliant": "🟢",
    }

    for repo_name in repos:
        repo_data = by_repo.get(repo_name, {})
        risk_level = repo_data.get("risk_assessment", {}).get("risk_level", "compliant")
        license_type = repo_data.get("license_info", {}).get("license", "未知")

        lines.append(
            f"- {risk_labels.get(risk_level, '⚪')} **{repo_name}**: {license_type}"
        )

    # 总结建议
    lines.extend([
        "",
        "---",
        "",
        "## 总结与建议",
        "",
    ])

    if compliant_rate < 0.6:
        lines.extend([
            "⚠️ **合规风险较高，建议：**",
            "",
            f"1. 立即为 {total_summary.get('risk_counts', {}).get('high', 0)} 个无许可证仓库添加 LICENSE",
            f"2. 检查 GPL 类许可证仓库的商用合规性",
            f"3. 补充版权声明文件",
        ])
    elif compliant_rate < 0.8:
        lines.append("🟡 **部分仓库存在合规风险，建议在下版本发布前修复。**")
    else:
        lines.append("✅ **多仓库整体合规状态良好。**")

    lines.extend([
        "",
        f"*报告生成于 {report_time}*",
    ])

    return "\n".join(lines)