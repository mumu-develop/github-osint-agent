"""L1 轻量扫描器 - 纯 GitHub API + OSV.dev，不调用 LLM。

重构说明:
- 使用 modules 层的专项扫描器，消除重复代码
- 保持公开接口不变，确保业务兼容
"""

import os
import asyncio
from datetime import datetime
from typing import Dict, List, Any
from github import Github, GithubException
from app.log_utils import get_logger
from app.models import Finding, ScanTask
from app.database import FindingDAO, ScanTaskDAO, init_business_tables
from app.scanner.modules import CVEScanner, LicenseScanner, CommunityScanner

logger = get_logger("light_scanner")


class LightScanner:
    """L1 轻量扫描器 - 不调用 LLM，纯 API 扫描。

    使用 modules 层的专项扫描器进行实际检查，
    本层只负责组合调用和结果汇总。

    公开接口保持不变：
    - scan_repo(owner, repo) -> List[Finding]
    - scan_org(org_name, ...) -> Dict[str, Any]
    - run_l1_scan(org_name) -> Dict[str, Any]
    """

    def __init__(self, github_token: str = None):
        self.github_token = github_token or os.getenv("GITHUB_TOKEN")
        self.github = Github(self.github_token)

        # 模块扫描器实例（延迟初始化）
        self._cve_scanner = None
        self._license_scanner = None
        self._community_scanner = None

    def _get_cve_scanner(self) -> CVEScanner:
        """获取 CVE 扫描器实例。"""
        if self._cve_scanner is None:
            self._cve_scanner = CVEScanner(self.github_token)
        return self._cve_scanner

    def _get_license_scanner(self) -> LicenseScanner:
        """获取许可证扫描器实例。"""
        if self._license_scanner is None:
            self._license_scanner = LicenseScanner(self.github_token)
        return self._license_scanner

    def _get_community_scanner(self) -> CommunityScanner:
        """获取社区健康度扫描器实例。"""
        if self._community_scanner is None:
            self._community_scanner = CommunityScanner(self.github_token)
        return self._community_scanner

    async def close(self):
        """关闭资源。"""
        if self._cve_scanner:
            await self._cve_scanner.close()
        if self._community_scanner:
            await self._community_scanner.close()

    async def scan_repo(self, owner: str, repo: str) -> List[Finding]:
        """扫描单个仓库，返回发现列表。

        Args:
            owner: 仓库所属组织/用户
            repo: 仓库名称

        Returns:
            Finding 列表
        """
        findings = []
        repo_full_name = f"{owner}/{repo}"

        logger.info("scan_repo_start", repo=repo_full_name)

        try:
            repo_obj = await asyncio.to_thread(self.github.get_repo, repo_full_name)

            # CVE扫描 - 使用 CVEScanner 模块
            cve_scanner = self._get_cve_scanner()
            cve_findings = await cve_scanner.scan(repo_obj)
            findings.extend(cve_findings)

            # 许可证检查 - 使用 LicenseScanner 模块
            license_scanner = self._get_license_scanner()
            license_findings = await license_scanner.scan(repo_obj)
            findings.extend(license_findings)

            # 社区健康度检查 - 使用 CommunityScanner 模块（包含 PR/Issue 详情）
            community_scanner = self._get_community_scanner()
            community_findings = await community_scanner.scan(repo_obj)
            findings.extend(community_findings)

            logger.info("scan_repo_done", repo=repo_full_name, findings=len(findings))

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
        """扫描整个组织的所有仓库。

        Args:
            org_name: 组织名称
            scan_task_id: 扫描任务 ID（可选）
            trigger_by: 触发方式
            concurrency: 并发数

        Returns:
            扫描结果字典
        """
        logger.info("scan_org_start", org=org_name, concurrency=concurrency)

        await init_business_tables()

        try:
            org = await asyncio.to_thread(self.github.get_organization, org_name)
            repos = await asyncio.to_thread(lambda: list(org.get_repos()))
        except GithubException as e:
            logger.error("scan_org_failed", org=org_name, error=str(e))
            return {"error": str(e), "repos_scanned": 0, "findings": 0}

        total_repos = len(repos)
        logger.info("scan_org_repos_found", org=org_name, count=total_repos)

        run_id = f"SCAN_{org_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        task = ScanTask(
            run_id=run_id,
            scan_type="L1_LIGHT",
            org_name=org_name,
            trigger_by=trigger_by,
            status="running",
            total_repos=total_repos
        )
        task_id = await ScanTaskDAO.create(task)

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

        logger.info("scan_org_done", org=org_name, repos_scanned=scanned_count, findings=len(all_findings))

        high_severity_findings = [f for f in all_findings if f.severity in ["CRITICAL", "HIGH"]]
        if high_severity_findings:
            logger.warning("high_severity_findings", count=len(high_severity_findings))

        return {
            "run_id": run_id,
            "org_name": org_name,
            "repos_scanned": scanned_count,
            "total_findings": len(all_findings),
            "high_severity_count": len(high_severity_findings),
            "task_id": task_id
        }

    async def run_l1_scan(self, org_name: str = None, repo_names: List[str] = None) -> Dict[str, Any]:
        """执行 L1 扫描。

        新架构说明：
        - 定时扫描任务由 Agent 通过 scheduler_tools 创建
        - 此方法接收显式的 org_name 或 repo_names 参数
        - 不再依赖 OrgConfigDAO

        Args:
            org_name: 组织名称（扫描整个组织）
            repo_names: 仓库列表（扫描指定仓库）

        Returns:
            扫描结果字典
        """
        await init_business_tables()

        if org_name:
            result = await self.scan_org(org_name)
            return {"scanned_orgs": 1, "results": [result]}

        if repo_names:
            findings = []
            for repo_full_name in repo_names:
                parts = repo_full_name.split("/")
                if len(parts) == 2:
                    repo_findings = await self.scan_repo(parts[0], parts[1])
                    findings.extend(repo_findings)
            return {"repos_scanned": len(repo_names), "total_findings": len(findings)}

        logger.info("l1_scan_no_targets")
        return {"message": "未指定扫描目标"}