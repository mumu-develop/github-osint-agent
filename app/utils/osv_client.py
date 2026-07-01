"""OSV.dev API 客户端 - 统一的漏洞查询接口。

OSV.dev 是一个开源漏洞数据库，支持多种生态系统:
- PyPI (Python)
- npm (Node.js)
- Maven (Java)
- Go
- crates.io (Rust)
- 等

API 文档: https://osv.dev/docs/
"""

import asyncio
import aiohttp
from typing import Dict, List, Optional, Any
from app.log_utils import get_logger
from app.scanner.scan_config import osv_api_timeout, get_batch_concurrency

logger = get_logger("osv_client")


class OSVClient:
    """OSV.dev API 客户端 - 支持批量查询和并发处理。"""

    API_URL = "https://api.osv.dev/v1/query"

    def __init__(self, concurrency: int = None, timeout: int = None):
        """初始化 OSV 客户端。

        Args:
            concurrency: 最大并发请求数
            timeout: 单次请求超时时间（秒）
        """
        self.concurrency = concurrency or get_batch_concurrency()
        self.timeout = timeout or osv_api_timeout()
        self._session: Optional[aiohttp.ClientSession] = None
        self._semaphore: Optional[asyncio.Semaphore] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取 aiohttp session（延迟初始化）。"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                connector=aiohttp.TCPConnector(limit=self.concurrency)
            )
        return self._session

    async def close(self):
        """关闭资源。"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def query(self, ecosystem: str, package: str, version: str) -> List[Dict]:
        """查询单个依赖的漏洞。

        Args:
            ecosystem: 生态系统 (PyPI, npm, Maven, Go 等)
            package: 包名
            version: 版本号

        Returns:
            漏洞列表 [{"id": "CVE-xxx", ...}]
        """
        session = await self._get_session()
        payload = {
            "package": {"name": package, "ecosystem": ecosystem},
            "version": version
        }

        try:
            async with session.post(self.API_URL, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    vulns = data.get("vulns", [])
                    logger.debug("osv_query_success",
                                 package=package, version=version,
                                 vulns=len(vulns))
                    return vulns
                else:
                    logger.warning("osv_query_failed",
                                   package=package, version=version,
                                   status=resp.status)
        except aiohttp.ClientError as e:
            logger.warning("osv_query_error",
                           package=package, version=version,
                           error=str(e))
        except asyncio.TimeoutError:
            logger.warning("osv_query_timeout",
                           package=package, version=version)

        return []

    async def batch_query(self, dependencies: List[Dict],
                          ecosystem: str) -> Dict[str, List[Dict]]:
        """批量查询多个依赖的漏洞。

        Args:
            dependencies: 依赖列表 [{"name": "xxx", "version": "yyy"}, ...]
            ecosystem: 生态系统

        Returns:
            {package@version: [vulns]}
        """
        if not dependencies:
            return {}

        session = await self._get_session()
        semaphore = asyncio.Semaphore(self.concurrency)

        results = {}

        async def query_single(dep: Dict) -> Tuple[str, List[Dict]]:
            """查询单个依赖。"""
            async with semaphore:
                package = dep["name"]
                version = dep.get("version")
                if not version:
                    return f"{package}@unknown", []

                vulns = await self.query(ecosystem, package, version)
                key = f"{package}@{version}"
                return key, vulns

        tasks = [query_single(dep) for dep in dependencies]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results_list:
            if isinstance(result, tuple):
                results[result[0]] = result[1]
            elif isinstance(result, Exception):
                logger.warning("osv_batch_query_error", error=str(result))

        return results

    async def query_for_repo(self, dep_files: Dict[str, str]) -> List[Dict]:
        """查询仓库所有依赖文件的漏洞。

        Args:
            dep_files: {filename: content} 如 {"requirements.txt": "flask==1.0"}

        Returns:
            漏洞列表
        """
        from app.utils.dep_parser import DependencyParser

        all_vulns = []
        session = await self._get_session()

        for filename, content in dep_files.items():
            ecosystem = DependencyParser.get_ecosystem(filename)
            if not ecosystem:
                continue

            deps = DependencyParser.parse(filename, content)
            if not deps:
                continue

            for dep in deps:
                if not dep.get("version"):
                    continue

                vulns = await self.query(ecosystem, dep["name"], dep["version"])
                for vuln in vulns:
                    vuln["source_file"] = filename
                    vuln["package"] = dep["name"]
                    vuln["version"] = dep["version"]
                    vuln["ecosystem"] = ecosystem
                all_vulns.extend(vulns)

        return all_vulns


# 全局实例（单例模式）
_client: Optional[OSVClient] = None


async def get_osv_client() -> OSVClient:
    """获取 OSV 客户端实例。"""
    global _client
    if _client is None:
        _client = OSVClient()
    return _client


async def query_osv(ecosystem: str, package: str, version: str) -> List[Dict]:
    """查询 OSV（便捷函数）。"""
    client = await get_osv_client()
    return await client.query(ecosystem, package, version)


async def close_osv_client():
    """关闭 OSV 客户端。"""
    global _client
    if _client is not None:
        await _client.close()
        _client = None