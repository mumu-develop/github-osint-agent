"""扫描器基类 - 统一的扫描器接口和通用功能。

所有扫描器应继承此基类，确保:
- 统一的资源管理 (close 方法)
- 统一的 GitHub 客户端初始化
- 统一的扫描维度配置
"""

import os
import asyncio
import aiohttp
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from github import Github, GithubException
from app.log_utils import get_logger

logger = get_logger("base_scanner")


class BaseScanner(ABC):
    """扫描器抽象基类。

    提供通用功能:
    - GitHub 客户端管理
    - aiohttp session 管理
    - 扫描维度配置

    子类需实现:
    - scan_repo(): 单仓库扫描逻辑
    - scan_org(): 组织扫描逻辑 (可选，有默认实现)
    """

    # 默认扫描维度
    DEFAULT_DIMENSIONS = {
        "cve": True,
        "secret": True,
        "license": True,
        "community": False
    }

    def __init__(self, github_token: str = None, dimensions: Dict[str, bool] = None):
        """初始化扫描器。

        Args:
            github_token: GitHub API token
            dimensions: 扫描维度配置
        """
        self.github_token = github_token or os.getenv("GITHUB_TOKEN")
        self.dimensions = dimensions or self.DEFAULT_DIMENSIONS.copy()
        self.github = Github(self.github_token)
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取 aiohttp session（延迟初始化）。"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15),
                connector=aiohttp.TCPConnector(limit=50)
            )
        return self._session

    async def close(self):
        """关闭资源 - 子类应调用此方法。"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    @abstractmethod
    async def scan_repo(self, owner: str, repo: str) -> List[Any]:
        """扫描单个仓库 - 子类必须实现。

        Args:
            owner: 仓库所有者
            repo: 仓库名称

        Returns:
            发现列表 (Finding 对象)
        """
        pass

    async def get_repo_list(self, org_name: str) -> List[Any]:
        """获取组织的仓库列表。

        Args:
            org_name: 组织名称

        Returns:
            仓库对象列表
        """
        try:
            org = await asyncio.to_thread(self.github.get_organization, org_name)
            repos = await asyncio.to_thread(lambda: list(org.get_repos()))
            logger.info("repo_list_fetched", org=org_name, count=len(repos))
            return repos
        except GithubException as e:
            logger.error("repo_list_failed", org=org_name, error=str(e))
            return []

    async def scan_org_batch(self, org_name: str, concurrency: int = 30,
                             task_creator: callable = None) -> Dict[str, Any]:
        """批量扫描组织仓库 - 默认实现。

        Args:
            org_name: 组织名称
            concurrency: 并发数
            task_creator: 任务创建函数 (可选)

        Returns:
            扫描结果统计
        """
        repos = await self.get_repo_list(org_name)
        if not repos:
            return {"error": "无法获取仓库列表", "repos_scanned": 0}

        semaphore = asyncio.Semaphore(concurrency)
        all_findings = []
        scanned_count = 0

        async def scan_with_semaphore(repo):
            async with semaphore:
                findings = await self.scan_repo(org_name, repo.name)
                nonlocal scanned_count
                scanned_count += 1
                return findings

        tasks = [scan_with_semaphore(repo) for repo in repos]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                all_findings.extend(result)

        return {
            "org_name": org_name,
            "repos_scanned": scanned_count,
            "total_findings": len(all_findings),
            "findings": all_findings
        }

    def _default_dimensions(self) -> Dict[str, bool]:
        """获取默认扫描维度。"""
        return self.DEFAULT_DIMENSIONS.copy()