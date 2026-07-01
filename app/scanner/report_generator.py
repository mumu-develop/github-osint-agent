"""Agent报告生成器 - 扫描完成后调用Agent生成深度分析报告。"""

import os
import asyncio
from datetime import datetime
from typing import Dict, List, Any, Optional
from app.log_utils import get_logger
from app.models import Finding, ScanTask, ScanReport
from app.database import FindingDAO, ScanTaskDAO, ScanReportDAO, ScanSubTaskDAO

logger = get_logger("report_generator")


class AgentReportGenerator:
    """Agent报告生成器。

    功能：
    1. 扫描完成后，收集所有Finding
    2. 按类型和严重程度分类
    3. 调用Agent进行深度分析
    4. 生成包含修复建议的报告
    """

    REPORT_TYPES = {
        "deep_analysis": "深度分析报告 - 全面评估和修复建议",
        "security_audit": "安全审计报告 - 专注安全风险",
        "summary": "扫描摘要报告 - 快速概览"
    }

    async def generate_report(self, scan_task_id: int,
                              report_type: str = "deep_analysis") -> ScanReport:
        """生成扫描报告。

        Args:
            scan_task_id: 扫描任务ID
            report_type: 报告类型

        Returns:
            ScanReport对象
        """
        logger.info("report_generation_start", task_id=scan_task_id, type=report_type)

        # 1. 收集扫描结果
        findings = await self._collect_findings(scan_task_id)
        logger.info("report_findings_collected", task_id=scan_task_id, findings_count=len(findings))
        progress = await ScanSubTaskDAO.get_progress(scan_task_id)
        task = await ScanTaskDAO.get_by_id(scan_task_id)

        if not task:
            logger.warning("report_task_not_found", task_id=scan_task_id)
            return ScanReport(
                scan_task_id=scan_task_id,
                report_type=report_type,
                title="扫描报告 - 任务不存在",
                content="找不到对应的扫描任务",
                summary="任务不存在"
            )

        if not findings:
            logger.warning("no_findings_to_report", task_id=scan_task_id)
            return ScanReport(
                scan_task_id=scan_task_id,
                report_type=report_type,
                title="扫描报告 - 无发现",
                content="本次扫描未发现任何问题。",
                summary="扫描完成，无问题发现"
            )

        # 2. 分类统计
        stats = self._analyze_findings(findings)

        # 3. 构造分析内容
        analysis_content = await self._build_analysis_content(
            task, findings, stats, progress, report_type
        )

        # 4. 生成修复建议
        recommendations = await self._generate_recommendations(findings, stats)

        # 5. 创建报告
        report = ScanReport(
            scan_task_id=scan_task_id,
            report_type=report_type,
            title=f"{task.org_name if task else ''} - {self.REPORT_TYPES.get(report_type, '扫描报告')}",
            content=analysis_content,
            summary=self._generate_summary(stats),
            recommendations=recommendations
        )

        logger.info("report_creating", task_id=scan_task_id, title=report.title)
        report_id = await ScanReportDAO.create(report)
        report.id = report_id

        logger.info("report_generation_done", task_id=scan_task_id, report_id=report_id, content_len=len(analysis_content))

        return report

    async def _collect_findings(self, scan_task_id: int) -> List[Finding]:
        """收集扫描任务的所有Finding。"""
        findings = await FindingDAO.query(scan_task_id=scan_task_id, page_size=1000)
        return findings

    def _analyze_findings(self, findings: List[Finding]) -> Dict[str, Any]:
        """分析Finding统计。"""
        stats = {
            "total": len(findings),
            "by_severity": {},
            "by_type": {},
            "by_repo": {},
            "high_risk_repos": []
        }

        severity_order = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
        type_list = ["CVE", "SECRET", "LICENSE", "COMMUNITY", "TREND", "SUPPLY_CHAIN", "AGENT_ANALYSIS"]

        for f in findings:
            # 按严重程度
            stats["by_severity"][f.severity] = stats["by_severity"].get(f.severity, 0) + 1

            # 按类型
            stats["by_type"][f.finding_type] = stats["by_type"].get(f.finding_type, 0) + 1

            # 按仓库
            if f.repo_full_name not in stats["by_repo"]:
                stats["by_repo"][f.repo_full_name] = {"total": 0, "high_severity": 0}
            stats["by_repo"][f.repo_full_name]["total"] += 1
            if f.severity in ["CRITICAL", "HIGH"]:
                stats["by_repo"][f.repo_full_name]["high_severity"] += 1

        # 标记高危仓库
        for repo, repo_stats in stats["by_repo"].items():
            if repo_stats["high_severity"] > 0:
                stats["high_risk_repos"].append(repo)

        return stats

    async def _build_analysis_content(self, task: Optional[ScanTask],
                                        findings: List[Finding],
                                        stats: Dict,
                                        progress: Dict,
                                        report_type: str) -> str:
        """构造报告内容（Markdown格式，面向SRE）。"""
        now = datetime.now().strftime('%Y-%m-%d %H:%M')

        content = f"""# {task.org_name if task else '组织'} 安全扫描报告

> 本报告由 GitHub OSINT 情报系统自动生成，供 SRE/运维团队参考

## 📊 扫描概览

| 项目 | 数值 |
|------|------|
| 扫描时间 | {now} |
| 扫描类型 | {task.scan_type if task else '未知'} |
| 扫描仓库数 | {task.total_repos if task else 0} |
| 发现问题总数 | {stats['total']} |
| MEDIUM级别问题 | {stats['by_severity'].get('MEDIUM', 0)} |
| LOW级别问题 | {stats['by_severity'].get('LOW', 0)} |

### 问题分布统计

| 类型 | 数量 | 占比 | 说明 |
|------|------|------|------|
| CVE漏洞 | {stats['by_type'].get('CVE', 0)} | {stats['by_type'].get('CVE', 0)*100//stats['total'] if stats['total'] > 0 else 0}% | 依赖包漏洞 |
| 许可证 | {stats['by_type'].get('LICENSE', 0)} | {stats['by_type'].get('LICENSE', 0)*100//stats['total'] if stats['total'] > 0 else 0}% | 许可证合规风险 |
| 社区健康 | {stats['by_type'].get('COMMUNITY', 0)} | {stats['by_type'].get('COMMUNITY', 0)*100//stats['total'] if stats['total'] > 0 else 0}% | 项目活跃度评估 |

---

"""

        # === CVE详情 ===
        cve_findings = [f for f in findings if f.finding_type == "CVE"]
        if cve_findings:
            content += """## 🛡️ CVE漏洞详情

> 以下列出所有发现的依赖包漏洞，请按优先级更新依赖版本

### 漏洞汇总（按仓库分组）

"""
            # 按仓库分组CVE
            cve_by_repo = {}
            for f in cve_findings:
                if f.repo_full_name not in cve_by_repo:
                    cve_by_repo[f.repo_full_name] = []
                cve_by_repo[f.repo_full_name].append(f)

            for repo, repo_cves in list(cve_by_repo.items())[:30]:  # 最多30个仓库
                content += f"\n#### `{repo}` ({len(repo_cves)} 个漏洞)\n\n"

                # 漏洞表格
                content += "| CVE编号 | 依赖包 | 版本 | CVSS | 风险类型 | 修复版本 |\n"
                content += "|---------|--------|------|------|----------|----------|\n"

                for cve in repo_cves[:15]:  # 每个仓库最多15个漏洞
                    detail = cve.detail or {}
                    cve_id = detail.get('cve_id', '未知')
                    package = detail.get('package', '未知')
                    version = detail.get('version', '未知')
                    cvss = detail.get('cvss_score', 0)
                    cvss_str = f"{cvss:.1f}" if cvss > 0 else "-"
                    risk_type = detail.get('risk_type', '安全漏洞')
                    fixed_version = detail.get('fixed_version', '未知')

                    # 根据CVSS评分高亮
                    severity_icon = "🔴" if cvss >= 9.0 else "🟠" if cvss >= 7.0 else "🟡"
                    content += f"| {severity_icon} {cve_id} | `{package}` | `{version}` | {cvss_str} | {risk_type} | `{fixed_version}` |\n"

                content += "\n"

                # 添加漏洞详情描述（只显示前3个高危漏洞的详细描述）
                high_risk_cves = [c for c in repo_cves if (c.detail or {}).get('cvss_score', 0) >= 7.0][:3]
                if high_risk_cves:
                    content += "**高危漏洞风险说明：**\n\n"
                    for cve in high_risk_cves:
                        detail = cve.detail or {}
                        cve_id = detail.get('cve_id', '未知')
                        summary = detail.get('summary', '')
                        details = detail.get('details', '')
                        refs = detail.get('references', [])

                        content += f"- **{cve_id}**: {summary}\n"
                        if details:
                            content += f"  - 风险描述: {details[:150]}...\n"
                        if refs:
                            content += f"  - 参考: {refs[0]}\n"
                    content += "\n"

            # 添加修复命令示例
            content += """
### 🔧 快速修复命令

```bash
# Python 项目 - 更新单个依赖
pip install --upgrade <package_name>==<fixed_version>

# Node.js 项目 - 更新单个依赖
npm install <package_name>@<fixed_version>

# Maven 项目 - 查看需要更新的依赖
mvn versions:display-dependency-updates

# Go 项目 - 更新依赖
go get <package_name>@<fixed_version>
go mod tidy
```

### 📚 漏洞类型说明

| 风险类型 | 危害程度 | 处理建议 |
|----------|----------|----------|
| 远程代码执行 | 🔴 极高 | 立即更新，可能被攻击者利用执行任意代码 |
| 注入漏洞 | 🔴 极高 | 立即更新，可能导致数据泄露或系统被控制 |
| 权限提升 | 🟠 高 | 尽快更新，攻击者可能获取更高权限 |
| 认证绕过 | 🟠 高 | 尽快更新，可能导致未授权访问 |
| 信息泄露 | 🟡 中 | 本周处理，敏感数据可能被泄露 |
| 拒绝服务 | 🟡 中 | 本周处理，服务可能被中断 |
| 加密漏洞 | 🟡 中 | 关注加密强度，评估是否需要更新 |

---

"""

        # === 许可证详情 ===
        license_findings = [f for f in findings if f.finding_type == "LICENSE"]
        if license_findings:
            content += """## ⚖️ 许可证合规详情

> 检查许可证兼容性，避免法律风险

### 许可证分布

"""
            # 按许可证类型分组
            license_by_type = {}
            for f in license_findings:
                detail = f.detail or {}
                license_type = detail.get('license', '未知') or f.title
                if license_type not in license_by_type:
                    license_by_type[license_type] = {'count': 0, 'repos': []}
                license_by_type[license_type]['count'] += 1
                license_by_type[license_type]['repos'].append(f.repo_full_name)

            content += "| 许可证类型 | 数量 | 风险等级 | 涉及仓库 |\n"
            content += "|------------|------|----------|----------|\n"

            for lic_type, info in license_by_type.items():
                risk = self._get_license_risk(lic_type)
                repos_str = ', '.join(info['repos'][:3]) + ('...' if len(info['repos']) > 3 else '')
                content += f"| {lic_type} | {info['count']} | {risk} | {repos_str} |\n"

            content += """

### 许可证风险说明

| 许可证 | 风险 | 使用建议 |
|--------|------|----------|
| GPL-2.0/3.0 | 🔴 高 | 传染性许可证，商业项目需谨慎 |
| LGPL | 🟡 中 | 动态链接可规避，需咨询法务 |
| Apache-2.0 | 🟢 低 | 商业友好，推荐使用 |
| MIT | 🟢 低 | 最宽松，商业友好 |
| BSD | 🟢 低 | 商业友好 |
| 未声明 | 🟡 中 | 需联系作者确认使用权限 |

---

"""

        # === 社区健康度详情 ===
        community_findings = [f for f in findings if f.finding_type == "COMMUNITY"]
        if community_findings:
            content += """## 👥 社区健康度详情

> 评估项目活跃度，判断是否需要寻找替代方案

### 不活跃/风险仓库列表

"""
            content += "| 仓库 | 问题类型 | 详情 | 建议 |\n"
            content += "|------|----------|------|------|\n"

            for f in community_findings[:20]:
                detail = f.detail or {}
                issue_type = detail.get('issue_type', f.title[:30])
                detail_str = f.description[:50] if f.description else '-'
                suggestion = self._get_community_suggestion(issue_type)
                content += f"| `{f.repo_full_name}` | {issue_type} | {detail_str} | {suggestion} |\n"

            content += """

### 社区健康指标说明

| 指标 | 健康阈值 | 风险阈值 |
|------|----------|----------|
| 最近提交 | < 6个月 | > 1年 |
| Issue响应时间 | < 7天 | > 30天 |
| PR合并速度 | < 14天 | > 60天 |
| 贡献者数量 | > 5人 | < 2人 |

---

"""

        # === 优先级处理建议 ===
        content += """## 🎯 处理优先级建议

### 立即处理（P0）

"""
        # 找出最多问题的仓库
        repo_problem_count = {}
        for f in findings:
            repo_problem_count[f.repo_full_name] = repo_problem_count.get(f.repo_full_name, 0) + 1

        top_problem_repos = sorted(repo_problem_count.items(), key=lambda x: x[1], reverse=True)[:5]
        if top_problem_repos:
            content += "**问题最多的仓库（建议优先排查）：**\n\n"
            for repo, count in top_problem_repos:
                content += f"- `{repo}` - {count} 个问题\n"

        content += """

### 本周处理（P1）

- 审查所有 CVE 漏洞，更新高风险依赖
- 检查许可证合规性，确认商业使用权限

### 本月处理（P2）

- 关注不活跃仓库，评估替代方案
- 建立依赖更新流程，定期检查

---

"""

        # === 附录：完整仓库列表 ===
        content += """## 📋 附录：所有仓库扫描结果

"""
        content += "| 仓库 | CVE | 许可证 | 社区 | 总计 |\n"
        content += "|------|-----|--------|------|------|\n"

        for repo in stats["by_repo"].keys():
            cve_cnt = len([f for f in findings if f.repo_full_name == repo and f.finding_type == 'CVE'])
            lic_cnt = len([f for f in findings if f.repo_full_name == repo and f.finding_type == 'LICENSE'])
            comm_cnt = len([f for f in findings if f.repo_full_name == repo and f.finding_type == 'COMMUNITY'])
            total = stats["by_repo"][repo]["total"]
            content += f"| `{repo}` | {cve_cnt} | {lic_cnt} | {comm_cnt} | {total} |\n"

        content += f"""

---

*报告生成时间: {now}*
*扫描任务ID: {task.run_id if task else '未知'}*
"""

        return content

    def _get_license_risk(self, license_type: str) -> str:
        """获取许可证风险等级。"""
        high_risk = ['GPL', 'GPL-2.0', 'GPL-3.0', 'AGPL']
        medium_risk = ['LGPL', 'MPL', '未声明', 'Unknown', 'NOASSERTION']
        low_risk = ['MIT', 'Apache', 'BSD', 'Apache-2.0', 'BSD-2-Clause', 'BSD-3-Clause']

        for h in high_risk:
            if h in license_type:
                return "🔴 高"
        for m in medium_risk:
            if m in license_type:
                return "🟡 中"
        for l in low_risk:
            if l in license_type:
                return "🟢 低"
        return "🟡 中"

    def _get_community_suggestion(self, issue_type: str) -> str:
        """获取社区问题处理建议。"""
        if '不活跃' in issue_type or 'inactive' in issue_type.lower():
            return "评估替代方案"
        elif 'issue' in issue_type.lower():
            return "关注Issue处理"
        elif '贡献者' in issue_type:
            return "社区规模较小"
        elif '提交' in issue_type or 'commit' in issue_type.lower():
            return "近期无更新"
        else:
            return "持续关注"

    def _generate_summary(self, stats: Dict) -> str:
        """生成报告摘要。"""
        critical = stats["by_severity"].get("CRITICAL", 0)
        high = stats["by_severity"].get("HIGH", 0)

        if critical > 0:
            return f"⚠️ 发现 {critical} 个严重漏洞，{high} 个高危问题，需要立即处理！"
        elif high > 0:
            return f"发现 {high} 个高危问题，建议优先处理。"
        elif stats["total"] > 0:
            return f"扫描完成，发现 {stats['total']} 个问题，建议按优先级处理。"
        else:
            return "扫描完成，未发现问题。"

    async def _generate_recommendations(self, findings: List[Finding],
                                         stats: Dict) -> List[str]:
        """生成修复建议。"""
        recommendations = []

        # CVE相关建议
        if stats["by_type"].get("CVE", 0) > 0:
            recommendations.append("🛡️ **CVE漏洞**: 更新依赖版本，使用 `pip install --upgrade` 或 `npm update`")

        # Secret相关建议
        if stats["by_type"].get("SECRET", 0) > 0:
            recommendations.append("🔐 **敏感信息**: 立即撤销泄露的密钥，添加 .gitignore 接收敏感文件")

        # License相关建议
        if stats["by_type"].get("LICENSE", 0) > 0:
            recommendations.append("⚖️ **许可证合规**: 检查许可证兼容性，避免使用限制性许可证的依赖")

        # Community相关建议
        if stats["by_type"].get("COMMUNITY", 0) > 0:
            recommendations.append("👥 **社区健康**: 关注不活跃仓库，评估是否需要替代方案")

        # 高危仓库处理
        if stats["high_risk_repos"]:
            recommendations.append(f"🎯 **优先处理**: {len(stats['high_risk_repos'])} 个高危仓库需要立即关注")

        # Agent深度分析建议（如果有LLM维度）
        if stats["by_type"].get("SUPPLY_CHAIN", 0) > 0:
            recommendations.append("🔍 **深度分析**: Agent已完成供应链风险评估，请查看详细报告")

        return recommendations

    async def call_agent_for_deep_analysis(self, findings: List[Finding]) -> str:
        """调用Agent进行深度分析（可选）。"""
        try:
            from app.agent import create_agent

            agent, backend = await create_agent()

            # 构造分析请求
            high_risk_findings = [f for f in findings if f.severity in ["CRITICAL", "HIGH"]]
            if not high_risk_findings:
                return ""

            prompt = f"""请分析以下安全发现并提供修复建议：

发现数量: {len(high_risk_findings)}

主要问题:
"""
            for f in high_risk_findings[:10]:
                prompt += f"- {f.repo_full_name}: {f.title} ({f.severity})\n"

            prompt += """
请提供：
1. 风险评估
2. 修复优先级排序
3. 具体修复步骤
"""

            # TODO: 完整调用Agent
            logger.info("agent_deep_analysis_called", findings=len(high_risk_findings))

            return "Agent深度分析完成（详细内容待集成）"

        except Exception as e:
            logger.warning("agent_analysis_error", error=str(e))
            return ""


# ==================== 快捷函数 ====================

async def generate_scan_report(scan_task_id: int, report_type: str = "deep_analysis") -> ScanReport:
    """生成扫描报告。"""
    generator = AgentReportGenerator()
    return await generator.generate_report(scan_task_id, report_type)