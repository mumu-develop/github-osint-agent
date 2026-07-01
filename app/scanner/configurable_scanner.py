"""可配置化扫描器 - 根据scan_dimensions配置动态组合执行扫描模块。

重构说明:
- 移除了对 OrgConfig 和 OrgConfigDAO 的依赖
- 定时任务由 Agent 通过 scheduler_tools 创建
- SecretScanner 模块待实现，当前跳过
"""

from __future__ import annotations

import os
import asyncio
from datetime import datetime
from typing import Dict, List, Any, Optional
from github import Github, GithubException
from app.log_utils import get_logger
from app.models import Finding, ScanTask, SCAN_TEMPLATES
from app.database import FindingDAO, ScanTaskDAO, init_business_tables
from app.scanner.modules.cve_scanner import CVEScanner
from app.scanner.modules.license_scanner import LicenseScanner
from app.scanner.modules.community_scanner import CommunityScanner
from app.scanner.modules.llm_analyzer import LLMAnalyzer

logger = get_logger("configurable_scanner")


class ConfigurableScanner:
    """可配置化扫描器 - 根据配置动态组合执行扫描模块。

    支持的扫描维度：
    - cve: CVE漏洞扫描（依赖分析 + OSV.dev）
    - secret: 敏感信息检测
    - license: 许可证合规检查
    - community: 社区健康度检查
    - trend: 趋势分析（LLM维度）- 分析 Star 历史、提交趋势
    - supply_chain: 供应链风险分析（LLM维度）- 分析依赖可信度
    """

    # 基础维度（不使用LLM）
    BASE_DIMENSIONS = ["cve", "secret", "license", "community"]

    # LLM维度
    LLM_DIMENSIONS = ["trend", "supply_chain"]

    def __init__(self, dimensions: Dict[str, bool] = None, llm_enabled: bool = False,
                 github_token: str = None):
        """
        Args:
            dimensions: 扫描维度配置 {"cve": True, "secret": True, ...}
            llm_enabled: 是否启用LLM深度分析
            github_token: GitHub API token
        """
        self.dimensions = dimensions or self._get_default_dimensions()
        self.llm_enabled = llm_enabled
        self.github_token = github_token or os.getenv("GITHUB_TOKEN")
        self.github = Github(self.github_token)
        self._modules = {}

        # 按配置加载模块
        self._load_modules()

    def _get_default_dimensions(self) -> Dict[str, bool]:
        """获取默认扫描维度配置。"""
        return {
            "cve": True,
            "secret": True,
            "license": True,
            "community": False,
            "trend": False,
            "supply_chain": False
        }

    def _load_modules(self):
        """按配置加载扫描模块。"""
        if self.dimensions.get("cve"):
            self._modules["cve"] = CVEScanner(self.github_token)
        # TODO: SecretScanner 模块待实现
        if self.dimensions.get("license"):
            self._modules["license"] = LicenseScanner(self.github_token)
        if self.dimensions.get("community"):
            self._modules["community"] = CommunityScanner(self.github_token)

        # LLM维度模块
        if self.llm_enabled:
            llm_dims = [d for d in self.LLM_DIMENSIONS if self.dimensions.get(d)]
            if llm_dims:
                self._modules["llm"] = LLMAnalyzer(self.github_token, dimensions=llm_dims)

    async def close(self):
        """关闭所有模块资源。"""
        for module in self._modules.values():
            if hasattr(module, 'close'):
                await module.close()

    async def scan_repo(self, owner: str, repo: str) -> List[Finding]:
        """扫描单个仓库，返回发现列表。"""
        findings = []
        repo_full_name = f"{owner}/{repo}"

        logger.info("configurable_scan_repo_start", repo=repo_full_name,
                    dimensions=[k for k, v in self.dimensions.items() if v])

        try:
            repo_obj = await asyncio.to_thread(self.github.get_repo, repo_full_name)

            # 执行各个扫描模块
            for dim, module in self._modules.items():
                try:
                    logger.debug("running_module", module=dim, repo=repo_full_name)
                    module_findings = await module.scan(repo_obj)
                    findings.extend(module_findings)
                    logger.debug("module_done", module=dim, repo=repo_full_name, findings=len(module_findings))
                except Exception as e:
                    logger.warning("module_error", module=dim, repo=repo_full_name, error=str(e))

            logger.info("configurable_scan_repo_done", repo=repo_full_name, findings=len(findings))

        except GithubException as e:
            logger.warning("scan_repo_error", repo=repo_full_name, error=str(e))
            findings.append(Finding(
                repo_full_name=repo_full_name,
                finding_type="COMMUNITY",
                severity="INFO",
                title=f"仓库扫描失败: {str(e)}",
                description=f"无法访问仓库 {repo_full_name}"
            ))

        return findings

    async def scan_org(self, org_name: str, scan_task_id: int = None,
                       trigger_by: str = "manual", concurrency: int = 30) -> Dict[str, Any]:
        """扫描整个组织的所有仓库。"""
        logger.info("configurable_scan_org_start", org=org_name, concurrency=concurrency)

        await init_business_tables()

        # 获取组织下所有仓库
        try:
            org = await asyncio.to_thread(self.github.get_organization, org_name)
            repos = await asyncio.to_thread(lambda: list(org.get_repos()))
        except GithubException as e:
            logger.error("scan_org_failed", org=org_name, error=str(e))
            return {"error": str(e), "repos_scanned": 0, "findings": 0}

        total_repos = len(repos)
        logger.info("scan_org_repos_found", org=org_name, count=total_repos)

        # 确定扫描类型
        scan_type = "CONFIGURABLE"
        if self.llm_enabled:
            scan_type = "L3_DEEP"
        elif all(self.dimensions.get(d) for d in self.BASE_DIMENSIONS[:3]):
            scan_type = "L1_LIGHT"

        run_id = f"SCAN_{org_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        task = ScanTask(
            run_id=run_id,
            scan_type=scan_type,
            org_name=org_name,
            trigger_by=trigger_by,
            status="running",
            total_repos=total_repos
        )
        task_id = await ScanTaskDAO.create(task)

        # 并发扫描仓库
        semaphore = asyncio.Semaphore(concurrency)
        all_findings = []
        scanned_count = 0

        async def scan_with_semaphore(repo):
            async with semaphore:
                findings = await self.scan_repo(org_name, repo.name)
                nonlocal scanned_count
                scanned_count += 1

                for f in findings:
                    f.scan_task_id = task_id
                await FindingDAO.batch_create(findings)

                if scanned_count % 10 == 0:
                    await ScanTaskDAO.update_status(run_id, "running", scanned_count, len(all_findings))

                return findings

        tasks = [scan_with_semaphore(repo) for repo in repos]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                all_findings.extend(result)

        await ScanTaskDAO.update_status(run_id, "completed", scanned_count, len(all_findings))

        logger.info("configurable_scan_org_done", org=org_name,
                    repos_scanned=scanned_count, findings=len(all_findings))

        high_severity_findings = [f for f in all_findings if f.severity in ["CRITICAL", "HIGH"]]
        if high_severity_findings:
            logger.warning("high_severity_findings", count=len(high_severity_findings))

        return {
            "run_id": run_id,
            "org_name": org_name,
            "repos_scanned": scanned_count,
            "total_findings": len(all_findings),
            "high_severity_count": len(high_severity_findings),
            "task_id": task_id,
            "dimensions": self.dimensions,
            "llm_enabled": self.llm_enabled
        }

    @staticmethod
    def from_template(template_name: str, github_token: str = None) -> ConfigurableScanner:
        """从预设模板创建扫描器。

        Args:
            template_name: 模板名称 basic|standard|deep|compliance_only|security_focus
            github_token: GitHub API token
        """
        template = SCAN_TEMPLATES.get(template_name)
        if not template:
            raise ValueError(f"未知的扫描模板: {template_name}")

        return ConfigurableScanner(
            dimensions=template["dimensions"],
            llm_enabled=template["llm_enabled"],
            github_token=github_token
        )

    @staticmethod
    def from_dimensions(dimensions: Dict[str, bool], llm_enabled: bool = False,
                        github_token: str = None) -> ConfigurableScanner:
        """从维度配置创建扫描器。

        新架构：直接接收维度配置，不依赖 OrgConfig。

        Args:
            dimensions: 扫描维度配置 {"cve": True, "license": True, ...}
            llm_enabled: 是否启用 LLM 分析
            github_token: GitHub API token
        """
        return ConfigurableScanner(
            dimensions=dimensions,
            llm_enabled=llm_enabled,
            github_token=github_token
        )