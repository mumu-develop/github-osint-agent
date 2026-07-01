"""
安全漏洞分析算法模块。

提供风险评分汇总、漏洞分类、报告组装等功能。
这些是 Tool 无法直接实现的复杂算法逻辑。

使用方式：
1. Tool 获取数据 → get_dependency_files, check_cve, scan_secrets
2. 调用本模块函数处理数据 → aggregate_vulnerabilities, generate_security_report
"""

from datetime import datetime
from typing import Dict, Any, List, Optional


# ============================================================
# 风险评分与分类
# ============================================================

# CVSS 评分等级
RISK_LEVELS = {
    "critical": {"min": 9.0, "label": "严重", "emoji": "🔴"},
    "high": {"min": 7.0, "label": "高危", "emoji": "🟠"},
    "medium": {"min": 4.0, "label": "中危", "emoji": "🟡"},
    "low": {"min": 0.1, "label": "低危", "emoji": "🟢"},
    "none": {"min": 0, "label": "安全", "emoji": "✅"},
}


def classify_vulnerability(cvss_score: float) -> Dict[str, Any]:
    """
    根据 CVSS 评分分类漏洞风险等级。

    Args:
        cvss_score: CVSS 评分 (0-10)

    Returns:
        风险等级信息
    """
    for level, config in RISK_LEVELS.items():
        if cvss_score >= config["min"]:
            return {
                "level": level,
                "label": config["label"],
                "emoji": config["emoji"],
                "cvss": cvss_score,
            }
    return {"level": "none", "label": "安全", "emoji": "✅", "cvss": cvss_score}


def aggregate_vulnerabilities(
    vulnerabilities: List[Dict[str, Any]],
    secrets_found: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    汇总漏洞和敏感信息，按风险等级分类。

    Tool 获取数据后，调用此函数进行汇总分析。

    Args:
        vulnerabilities: 漏洞列表（from check_cve）
        secrets_found: 敏感信息列表（from scan_secrets）

    Returns:
        汇总结果
    """
    # 漏洞分类统计
    vuln_by_level = {"critical": [], "high": [], "medium": [], "low": []}

    for vuln in vulnerabilities:
        cvss = vuln.get("cvss", 0) or vuln.get("severity", 0)
        classification = classify_vulnerability(cvss)

        vuln_entry = {
            "package": vuln.get("package", vuln.get("name", "")),
            "version": vuln.get("version", ""),
            "cve_id": vuln.get("id", vuln.get("cve_id", "")),
            "cvss": cvss,
            "risk_level": classification["level"],
            "risk_label": classification["label"],
            "description": vuln.get("summary", vuln.get("description", "")),
            "fixed_version": vuln.get("fixed_version", vuln.get("affected_versions", "")),
        }

        if classification["level"] in vuln_by_level:
            vuln_by_level[classification["level"]].append(vuln_entry)

    # 敏感信息处理（统一标记为高危）
    secrets_processed = []
    for secret in secrets_found:
        secrets_processed.append({
            "file": secret.get("file", secret.get("filename", "")),
            "pattern": secret.get("pattern", secret.get("name", "")),
            "risk_level": "high",  # 密钥泄露统一高危
            "risk_label": "高危",
            "type": classify_secret_type(secret.get("pattern", "")),
        })

    # 统计汇总
    summary = {
        "total_vulnerabilities": len(vulnerabilities),
        "total_secrets": len(secrets_found),
        "vuln_counts": {
            "critical": len(vuln_by_level["critical"]),
            "high": len(vuln_by_level["high"]),
            "medium": len(vuln_by_level["medium"]),
            "low": len(vuln_by_level["low"]),
        },
        "highest_risk": max(
            ["critical", "high", "medium", "low"],
            key=lambda x: len(vuln_by_level[x]) if vuln_by_level[x] else -1
        ) if vulnerabilities else "none",
    }

    # 计算安全评分
    safe_score = 100
    safe_score -= summary["vuln_counts"]["critical"] * 20
    safe_score -= summary["vuln_counts"]["high"] * 10
    safe_score -= summary["vuln_counts"]["medium"] * 5
    safe_score -= summary["vuln_counts"]["low"] * 2
    safe_score -= len(secrets_found) * 15
    safe_score = max(0, safe_score)

    summary["security_score"] = safe_score

    return {
        "vulnerabilities_by_level": vuln_by_level,
        "secrets": secrets_processed,
        "summary": summary,
    }


def classify_secret_type(pattern: str) -> str:
    """
    分类敏感信息类型。

    Args:
        pattern: 匹配的模式名

    Returns:
        类型描述
    """
    type_map = {
        "aws_key": "AWS 访问密钥",
        "github_token": "GitHub Token",
        "private_key": "私钥文件",
        "api_key": "API 密钥",
        "password": "密码",
    }
    return type_map.get(pattern, f"未知类型 ({pattern})")


def get_fix_recommendations(vuln_entry: Dict[str, Any]) -> str:
    """
    生成漏洞修复建议。

    Args:
        vuln_entry: 漏洞信息

    Returns:
        修复建议文本
    """
    package = vuln_entry.get("package", "")
    fixed_version = vuln_entry.get("fixed_version", "")

    if fixed_version:
        return f"升级 {package} 至 {fixed_version} 或更高版本"
    return f"关注 {package} 的安全更新，或考虑替换依赖"


# ============================================================
# 报告组装
# ============================================================

def generate_security_report(
    aggregated: Dict[str, Any],
    owner: str,
    repo: str
) -> str:
    """
    组装安全分析报告（Markdown 格式）。

    Args:
        aggregated: 汇总后的安全数据
        owner: 仓库所有者
        repo: 仓库名

    Returns:
        Markdown 报告内容
    """
    report_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    summary = aggregated.get("summary", {})
    vuln_by_level = aggregated.get("vulnerabilities_by_level", {})
    secrets = aggregated.get("secrets", [])

    # 安全状态判断
    security_score = summary.get("security_score", 100)
    if security_score >= 80:
        status = "✅ 安全"
    elif security_score >= 60:
        status = "🟡 有风险"
    elif security_score >= 40:
        status = "🟠 高风险"
    else:
        status = "🔴 严重风险"

    lines = [
        f"# 安全分析报告",
        "",
        f"**仓库**: {owner}/{repo}",
        f"**生成时间**: {report_time}",
        f"**安全评分**: {security_score}/100",
        f"**安全状态**: {status}",
        "",
        "---",
        "",
        "## 漏洞统计",
        "",
        f"- 🔴 严重: {summary.get('vuln_counts', {}).get('critical', 0)} 个",
        f"- 🟠 高危: {summary.get('vuln_counts', {}).get('high', 0)} 个",
        f"- 🟡 中危: {summary.get('vuln_counts', {}).get('medium', 0)} 个",
        f"- 🟢 低危: {summary.get('vuln_counts', {}).get('low', 0)} 个",
        "",
    ]

    # 敏感信息统计
    if secrets:
        lines.extend([
            "## 敏感信息泄露",
            "",
            f"发现 {len(secrets)} 处潜在敏感信息泄露：",
            "",
            "| 文件 | 类型 | 风险等级 |",
            "|------|------|----------|",
        ])

        for secret in secrets:
            lines.append(
                f"| {secret.get('file', '')} | {secret.get('type', '')} | "
                f"{secret.get('risk_label', '')} |"
            )

        lines.extend([
            "",
            "**建议**:",
            "- 立即移除泄露的密钥并更换",
            "- 检查 Git 历史，确保密钥不在提交记录中",
            "- 使用密钥管理服务替代硬编码",
            "",
        ])

    # 严重和高危漏洞详情
    critical_high = vuln_by_level.get("critical", []) + vuln_by_level.get("high", [])
    if critical_high:
        lines.extend([
            "---",
            "",
            "## 高危漏洞详情",
            "",
            "| 包名 | 版本 | CVE | CVSS | 修复版本 |",
            "|------|------|-----|------|----------|",
        ])

        for vuln in critical_high:
            lines.append(
                f"| {vuln.get('package', '')} | {vuln.get('version', '')} | "
                f"{vuln.get('cve_id', '')} | {vuln.get('cvss', '')} | "
                f"{vuln.get('fixed_version', '待发布')} |"
            )

        lines.extend([
            "",
            "**修复建议**:",
        ])

        for vuln in critical_high[:5]:
            lines.append(f"- {get_fix_recommendations(vuln)}")

        lines.append("")

    # 总结建议
    lines.extend([
        "---",
        "",
        "## 总结与建议",
        "",
    ])

    if security_score < 60:
        lines.append("⚠️ **该仓库存在较高安全风险，建议立即处理高危漏洞和敏感信息泄露。**")
    elif security_score < 80:
        lines.append("🟡 **该仓库存在部分安全风险，建议在下版本发布前修复。**")
    else:
        lines.append("✅ **该仓库安全状态良好，继续保持安全扫描习惯。**")

    lines.extend([
        "",
        f"*报告生成于 {report_time}*",
    ])

    return "\n".join(lines)


__all__ = [
    "classify_vulnerability",
    "aggregate_vulnerabilities",
    "aggregate_multi_repo_vulnerabilities",
    "classify_secret_type",
    "get_fix_recommendations",
    "generate_security_report",
    "generate_multi_repo_report",
]


# ============================================================
# 多仓库聚合函数
# ============================================================

def aggregate_multi_repo_vulnerabilities(
    findings_by_repo: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """
    聚合多仓库的安全数据，按仓库和风险等级双重分类。

    Args:
        findings_by_repo: 按仓库分组的数据
            {
                "sofastack/sofa-rpc": {
                    "cve_findings": [...],
                    "secret_findings": [...]
                },
                "sofastack/sofa-boot": {
                    "cve_findings": [...],
                    "secret_findings": [...]
                }
            }

    Returns:
        聚合结果，包含：
        - by_repo: 每个仓库的聚合数据
        - total_summary: 所有仓库汇总统计
        - top_problematic_repos: 问题最多的仓库
    """
    by_repo: Dict[str, Dict] = {}
    total_vulns = 0
    total_secrets = 0
    total_by_level = {"critical": 0, "high": 0, "medium": 0, "low": 0}

    for repo_name, findings in findings_by_repo.items():
        cve_findings = findings.get("cve_findings", findings.get("vulnerabilities", []))
        secret_findings = findings.get("secret_findings", findings.get("secrets", []))

        # 单仓库聚合
        repo_aggregated = aggregate_vulnerabilities(cve_findings, secret_findings)
        by_repo[repo_name] = repo_aggregated

        # 累计统计
        total_vulns += repo_aggregated["summary"]["total_vulnerabilities"]
        total_secrets += repo_aggregated["summary"]["total_secrets"]
        for level in ["critical", "high", "medium", "low"]:
            total_by_level[level] += repo_aggregated["summary"]["vuln_counts"].get(level, 0)

    # 计算总体安全评分
    total_score = 100
    total_score -= total_by_level["critical"] * 20
    total_score -= total_by_level["high"] * 10
    total_score -= total_by_level["medium"] * 5
    total_score -= total_by_level["low"] * 2
    total_score -= total_secrets * 15
    total_score = max(0, total_score)

    # 找出问题最多的仓库
    repo_scores = [
        (repo, data["summary"]["security_score"])
        for repo, data in by_repo.items()
    ]
    top_problematic = sorted(repo_scores, key=lambda x: x[1], reverse=False)[:5]

    return {
        "by_repo": by_repo,
        "total_summary": {
            "repos_analyzed": len(findings_by_repo),
            "total_vulnerabilities": total_vulns,
            "total_secrets": total_secrets,
            "vuln_counts": total_by_level,
            "security_score": total_score,
        },
        "top_problematic_repos": [
            {"repo": repo, "score": score, "issues": by_repo[repo]["summary"]["total_vulnerabilities"]}
            for repo, score in top_problematic
        ],
    }


def generate_multi_repo_report(
    aggregated: Dict[str, Any],
    repos: List[str]
) -> str:
    """
    组装多仓库安全汇总报告（Markdown 格式）。

    Args:
        aggregated: 多仓库聚合数据
        repos: 仓库列表

    Returns:
        Markdown 报告内容
    """
    report_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_summary = aggregated.get("total_summary", {})
    by_repo = aggregated.get("by_repo", {})
    top_problematic = aggregated.get("top_problematic_repos", [])

    security_score = total_summary.get("security_score", 100)
    if security_score >= 80:
        status = "✅ 整体安全"
    elif security_score >= 60:
        status = "🟡 存在风险"
    elif security_score >= 40:
        status = "🟠 高风险"
    else:
        status = "🔴 严重风险"

    lines = [
        f"# 多仓库安全汇总报告",
        "",
        f"**分析仓库数**: {len(repos)}",
        f"**生成时间**: {report_time}",
        f"**整体安全评分**: {security_score}/100",
        f"**整体状态**: {status}",
        "",
        "---",
        "",
        "## 汇总统计",
        "",
        f"- 🔴 严重漏洞: {total_summary.get('vuln_counts', {}).get('critical', 0)} 个",
        f"- 🟠 高危漏洞: {total_summary.get('vuln_counts', {}).get('high', 0)} 个",
        f"- 🟡 中危漏洞: {total_summary.get('vuln_counts', {}).get('medium', 0)} 个",
        f"- 🟢 低危漏洞: {total_summary.get('vuln_counts', {}).get('low', 0)} 个",
        f"- 🔐 敏感信息泄露: {total_summary.get('total_secrets', 0)} 处",
        "",
    ]

    # 问题最多的仓库
    if top_problematic:
        lines.extend([
            "---",
            "",
            "## 问题最多的仓库",
            "",
            "| 仓库 | 安全评分 | 问题数 |",
            "|------|----------|--------|",
        ])
        for item in top_problematic:
            lines.append(
                f"| {item['repo']} | {item['score']}/100 | {item['issues']} |"
            )
        lines.append("")

    # 各仓库详情摘要
    lines.extend([
        "---",
        "",
        "## 各仓库安全状态",
        "",
    ])

    for repo_name in repos:
        repo_data = by_repo.get(repo_name, {})
        repo_summary = repo_data.get("summary", {})
        repo_score = repo_summary.get("security_score", 100)

        if repo_score >= 80:
            repo_status = "✅"
        elif repo_score >= 60:
            repo_status = "🟡"
        elif repo_score >= 40:
            repo_status = "🟠"
        else:
            repo_status = "🔴"

        lines.append(
            f"- {repo_status} **{repo_name}**: {repo_score}/100 "
            f"(漏洞 {repo_summary.get('total_vulnerabilities', 0)}, "
            f"敏感信息 {repo_summary.get('total_secrets', 0)})"
        )

    # 高危问题汇总
    all_critical_high = []
    for repo_name, repo_data in by_repo.items():
        vuln_by_level = repo_data.get("vulnerabilities_by_level", {})
        for vuln in vuln_by_level.get("critical", []) + vuln_by_level.get("high", []):
            vuln["repo"] = repo_name
            all_critical_high.append(vuln)

    if all_critical_high:
        lines.extend([
            "",
            "---",
            "",
            "## 高危问题详情（前10）",
            "",
            "| 仓库 | 包名 | CVE | CVSS |",
            "|------|------|-----|------|",
        ])

        for vuln in all_critical_high[:10]:
            lines.append(
                f"| {vuln.get('repo', '')} | {vuln.get('package', '')} | "
                f"{vuln.get('cve_id', '')} | {vuln.get('cvss', '')} |"
            )
        lines.append("")

    # 总结建议
    lines.extend([
        "---",
        "",
        "## 总结与建议",
        "",
    ])

    if security_score < 60:
        lines.extend([
            "⚠️ **多仓库整体安全风险较高，建议优先处理：**",
            "",
            f"1. 立即修复 {top_problematic[0]['repo'] if top_problematic else '问题最严重的仓库'}",
            f"2. 处理 {total_summary.get('vuln_counts', {}).get('critical', 0)} 个严重漏洞",
            f"3. 移除 {total_summary.get('total_secrets', 0)} 处敏感信息泄露",
        ])
    elif security_score < 80:
        lines.append("🟡 **部分仓库存在安全风险，建议在下版本发布前修复。**")
    else:
        lines.append("✅ **多仓库整体安全状态良好，继续保持安全扫描习惯。**")

    lines.extend([
        "",
        f"*报告生成于 {report_time}*",
    ])

    return "\n".join(lines)