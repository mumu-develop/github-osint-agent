"""批量扫描工具 - 快速收集数据层（无LLM调用）。

重构说明:
- 使用 modules 层的专项扫描器，消除重复代码
- 保持公开接口不变，确保业务兼容
- 保留进度追踪和速率限制功能
"""

import os
import asyncio
import aiohttp
from typing import Dict, List, Any
from github import Github, GithubException
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from app.log_utils import get_logger
from app.models import Finding
from app.scanner.scan_config import github_api_timeout, get_batch_concurrency
from app.scanner.rate_limiter import check_can_request, mark_rate_limited
from app.progress import ProgressTracker
from app.scanner.modules import CVEScanner, LicenseScanner, CommunityScanner

logger = get_logger("batch_tools")


class BatchScanTools:
    """批量扫描工具集 - 快速数据收集层。

    使用 modules 层的专项扫描器进行实际检查，
    本层只负责批量并发编排和进度追踪。

    公开接口保持不变：
    - batch_cve_check(repos, progress_tracker) -> Dict[str, List[Finding]]
    - batch_secret_scan(repos, progress_tracker) -> Dict[str, List[Finding]]
    - batch_license_check(repos, progress_tracker) -> Dict[str, List[Finding]]
    - batch_community_check(repos, progress_tracker) -> Dict[str, List[Finding]]
    """

    def __init__(self, github_token: str = None, concurrency: int = None):
        """
        Args:
            github_token: GitHub API token
            concurrency: 最大并发数（默认从配置读取）
        """
        self.github_token = github_token or os.getenv("GITHUB_TOKEN")
        self.concurrency = concurrency or get_batch_concurrency()

        # 配置大连接池（解决 "Connection pool is full" 问题）
        import requests
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=self.concurrency,
            pool_maxsize=self.concurrency
        )
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        # 创建 Github 实例并替换内部 session
        self.github = Github(self.github_token, timeout=github_api_timeout())
        self.github._Github__requester._Requester__session = session

        logger.info("batch_tools_initialized", concurrency=self.concurrency, pool_size=self.concurrency)

        # 模块扫描器实例（延迟初始化）
        self._cve_scanner = None
        self._license_scanner = None
        self._community_scanner = None

        self._session = None

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

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取 aiohttp session（延迟初始化）。"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15),
                connector=aiohttp.TCPConnector(limit=self.concurrency)
            )
        return self._session

    async def close(self):
        """关闭资源。"""
        if self._session and not self._session.closed:
            await self._session.close()
        if self._cve_scanner:
            await self._cve_scanner.close()

    # ==================== 批量CVE检查 ====================

    async def batch_cve_check(
        self,
        repos: List[Dict],
        progress_tracker: ProgressTracker = None
    ) -> Dict[str, List[Finding]]:
        """批量CVE漏洞检查 - 调用 CVEScanner 模块。

        Args:
            repos: 仓库列表 [{"owner": "xxx", "repo": "yyy"}, ...]
            progress_tracker: 进度追踪器（可选）

        Returns:
            {repo_full_name: [Finding, ...]}
        """
        logger.info("batch_cve_check_start", repo_count=len(repos))
        results = {}

        scanner = self._get_cve_scanner()
        semaphore = asyncio.Semaphore(self.concurrency)

        async def check_repo(repo_info):
            async with semaphore:
                owner, repo_name = repo_info["owner"], repo_info["repo"]
                repo_full_name = f"{owner}/{repo_name}"

                # 检查速率限制
                if not await check_can_request():
                    logger.warning("rate_limit_skip_repo", repo=repo_full_name)
                    if progress_tracker:
                        await progress_tracker.update(
                            repo_full_name, "paused", "cve_scan",
                            error="速率限制，暂停扫描"
                        )
                    return repo_full_name, []

                if progress_tracker:
                    await progress_tracker.update(repo_full_name, "running", "cve_scan")

                findings = []

                try:
                    repo_obj = await asyncio.to_thread(self.github.get_repo, repo_full_name)
                    findings = await scanner.scan(repo_obj)

                    if progress_tracker:
                        await progress_tracker.update(
                            repo_full_name, "done", "cve_scan",
                            findings=len(findings)
                        )

                except GithubException as e:
                    if e.status == 403:
                        logger.warning("github_rate_limit_hit", repo=repo_full_name)
                        mark_rate_limited()
                        if progress_tracker:
                            await progress_tracker.update(
                                repo_full_name, "paused", "cve_scan",
                                error="速率限制触发"
                            )
                    else:
                        logger.warning("batch_cve_repo_error", repo=repo_full_name, error=str(e))
                        if progress_tracker:
                            await progress_tracker.update(
                                repo_full_name, "error", "cve_scan",
                                error=str(e)[:50]
                            )
                except Exception as e:
                    logger.warning("batch_cve_check_error", repo=repo_full_name, error=str(e))
                    if progress_tracker:
                        await progress_tracker.update(
                            repo_full_name, "error", "cve_scan",
                            error=str(e)[:50]
                        )

                return repo_full_name, findings

        tasks = [check_repo(r) for r in repos]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results_list:
            if isinstance(result, tuple):
                results[result[0]] = result[1]

        total_findings = sum(len(f) for f in results.values())
        logger.info("batch_cve_check_done", repo_count=len(repos), findings=total_findings)
        return results

    # ==================== 批量敏感信息扫描 ====================

    async def batch_secret_scan(
        self,
        repos: List[Dict],
        progress_tracker: ProgressTracker = None
    ) -> Dict[str, List[Finding]]:
        """批量敏感信息扫描（预留接口）。

        注意：SecretScanner 模块尚未实现，此方法返回空结果。

        Args:
            repos: 仓库列表 [{"owner": "xxx", "repo": "yyy"}, ...]
            progress_tracker: 进度追踪器（可选）

        Returns:
            {repo_full_name: [Finding, ...]}（当前为空）
        """
        logger.info("batch_secret_scan_start", repo_count=len(repos), note="SecretScanner模块待实现")
        results = {}

        # TODO: 实现敏感信息扫描
        # 当 SecretScanner 模块实现后，可参照 batch_cve_check 的逻辑

        for repo_info in repos:
            repo_full_name = f"{repo_info['owner']}/{repo_info['repo']}"
            results[repo_full_name] = []

            if progress_tracker:
                await progress_tracker.update(repo_full_name, "done", "secret_scan", findings=0)

        logger.info("batch_secret_scan_done", repo_count=len(repos), findings=0, note="功能待实现")
        return results

    # ==================== 批量许可证检查 ====================

    async def batch_license_check(
        self,
        repos: List[Dict],
        progress_tracker: ProgressTracker = None
    ) -> Dict[str, List[Finding]]:
        """批量许可证合规检查 - 调用 LicenseScanner 模块。

        Args:
            repos: 仓库列表 [{"owner": "xxx", "repo": "yyy"}, ...]
            progress_tracker: 进度追踪器（可选）

        Returns:
            {repo_full_name: [Finding, ...]}
        """
        logger.info("batch_license_check_start", repo_count=len(repos))
        results = {}

        scanner = self._get_license_scanner()
        semaphore = asyncio.Semaphore(self.concurrency)

        async def check_repo(repo_info):
            async with semaphore:
                owner, repo_name = repo_info["owner"], repo_info["repo"]
                repo_full_name = f"{owner}/{repo_name}"

                if progress_tracker:
                    await progress_tracker.update(repo_full_name, "running", "license_check")

                findings = []

                try:
                    repo_obj = await asyncio.to_thread(self.github.get_repo, repo_full_name)
                    findings = await scanner.scan(repo_obj)

                    if progress_tracker:
                        await progress_tracker.update(
                            repo_full_name, "done", "license_check",
                            findings=len(findings)
                        )

                except GithubException as e:
                    logger.warning("batch_license_repo_error", repo=repo_full_name, error=str(e))
                    if progress_tracker:
                        await progress_tracker.update(
                            repo_full_name, "error", "license_check",
                            error=str(e)[:50]
                        )
                except Exception as e:
                    logger.warning("batch_license_check_error", repo=repo_full_name, error=str(e))
                    if progress_tracker:
                        await progress_tracker.update(
                            repo_full_name, "error", "license_check",
                            error=str(e)[:50]
                        )

                return repo_full_name, findings

        tasks = [check_repo(r) for r in repos]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results_list:
            if isinstance(result, tuple):
                results[result[0]] = result[1]

        total_findings = sum(len(f) for f in results.values())
        logger.info("batch_license_check_done", repo_count=len(repos), findings=total_findings)
        return results

    # ==================== 批量社区健康度检查 ====================

    async def batch_community_check(
        self,
        repos: List[Dict],
        progress_tracker: ProgressTracker = None
    ) -> Dict[str, List[Finding]]:
        """批量社区健康度检查 - 调用 CommunityScanner 模块。

        注意：现在使用完整的 CommunityScanner（包含 PR/Issue 详情），
        而不是之前简化版的只检查 days_inactive。

        Args:
            repos: 仓库列表 [{"owner": "xxx", "repo": "yyy"}, ...]
            progress_tracker: 进度追踪器（可选）

        Returns:
            {repo_full_name: [Finding, ...]}
        """
        logger.info("batch_community_check_start", repo_count=len(repos))
        results = {}

        scanner = self._get_community_scanner()
        semaphore = asyncio.Semaphore(self.concurrency)

        async def check_repo(repo_info):
            async with semaphore:
                owner, repo_name = repo_info["owner"], repo_info["repo"]
                repo_full_name = f"{owner}/{repo_name}"

                if progress_tracker:
                    await progress_tracker.update(repo_full_name, "running", "community_check")

                findings = []

                try:
                    repo_obj = await asyncio.to_thread(self.github.get_repo, repo_full_name)
                    findings = await scanner.scan(repo_obj)

                    if progress_tracker:
                        await progress_tracker.update(
                            repo_full_name, "done", "community_check",
                            findings=len(findings)
                        )

                except GithubException as e:
                    logger.warning("batch_community_repo_error", repo=repo_full_name, error=str(e))
                    if progress_tracker:
                        await progress_tracker.update(
                            repo_full_name, "error", "community_check",
                            error=str(e)[:50]
                        )
                except Exception as e:
                    logger.warning("batch_community_check_error", repo=repo_full_name, error=str(e))
                    if progress_tracker:
                        await progress_tracker.update(
                            repo_full_name, "error", "community_check",
                            error=str(e)[:50]
                        )

                return repo_full_name, findings

        tasks = [check_repo(r) for r in repos]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results_list:
            if isinstance(result, tuple):
                results[result[0]] = result[1]

        total_findings = sum(len(f) for f in results.values())
        logger.info("batch_community_check_done", repo_count=len(repos), findings=total_findings)
        return results

    # ==================== 单仓库扫描方法（用于进度跟踪） ====================

    async def cve_check_single(self, owner: str, repo_name: str) -> List[Finding]:
        """单个仓库CVE检查 - 调用 CVEScanner 模块。"""
        repo_full_name = f"{owner}/{repo_name}"

        try:
            repo_obj = await asyncio.to_thread(self.github.get_repo, repo_full_name)
            scanner = self._get_cve_scanner()
            return await scanner.scan(repo_obj)
        except Exception as e:
            logger.warning("cve_single_error", repo=repo_full_name, error=str(e))
            return []

    async def secret_check_single(self, owner: str, repo_name: str) -> List[Finding]:
        """单个仓库敏感信息扫描（预留接口）。

        注意：SecretScanner 模块尚未实现，此方法返回空结果。
        """
        # TODO: 实现敏感信息扫描
        logger.info("secret_check_single", repo=f"{owner}/{repo_name}", note="功能待实现")
        return []

    async def license_check_single(self, owner: str, repo_name: str) -> List[Finding]:
        """单个仓库许可证检查 - 调用 LicenseScanner 模块。"""
        repo_full_name = f"{owner}/{repo_name}"

        try:
            repo_obj = await asyncio.to_thread(self.github.get_repo, repo_full_name)
            scanner = self._get_license_scanner()
            return await scanner.scan(repo_obj)
        except Exception as e:
            logger.warning("license_single_error", repo=repo_full_name, error=str(e))
            return []

    async def community_check_single(self, owner: str, repo_name: str) -> List[Finding]:
        """单个仓库社区健康度检查 - 调用 CommunityScanner 模块。"""
        repo_full_name = f"{owner}/{repo_name}"

        try:
            repo_obj = await asyncio.to_thread(self.github.get_repo, repo_full_name)
            scanner = self._get_community_scanner()
            return await scanner.scan(repo_obj)
        except Exception as e:
            logger.warning("community_single_error", repo=repo_full_name, error=str(e))
            return []