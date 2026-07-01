"""CVE漏洞扫描模块 - 依赖文件分析 + OSV.dev API查询。

重构说明:
- 依赖解析使用 app.utils.dep_parser.DependencyParser
- 严重程度映射使用 app.utils.severity_mapper
"""

import os
import asyncio
import aiohttp
from typing import Dict, List, Optional
from github import Github, GithubException
from app.log_utils import get_logger
from app.models import Finding
from app.utils.dep_parser import DependencyParser
from app.utils.severity_mapper import map_osv_severity

logger = get_logger("cve_scanner")


def extract_fixed_version(osv_vuln: Dict) -> Optional[str]:
    """从 OSV 漏洞数据中提取修复版本。

    OSV 数据结构:
    affected[].ranges[].events[].fixed = "修复版本号"

    Returns:
        修复版本号，如果有多个取第一个
    """
    affected = osv_vuln.get("affected", [])
    for aff in affected:
        ranges = aff.get("ranges", [])
        for r in ranges:
            events = r.get("events", [])
            for e in events:
                if "fixed" in e:
                    return e["fixed"]
    return None


def extract_summary_info(osv_vuln: Dict) -> Dict:
    """从 OSV 漏洞数据中提取关键摘要信息。"""
    return {
        "summary": osv_vuln.get("summary", ""),
        "details": osv_vuln.get("details", ""),
        "aliases": osv_vuln.get("aliases", []),
        "cvss": osv_vuln.get("severity", []),
        "references": [r.get("url") for r in osv_vuln.get("references", []) if r.get("url")]
    }


class CVEScanner:
    """CVE漏洞扫描器 - 依赖文件分析 + OSV.dev API。"""

    def __init__(self, github_token: str = None):
        self.github_token = github_token or os.getenv("GITHUB_TOKEN")
        self.github = Github(self.github_token)
        self.osv_api_url = "https://api.osv.dev/v1/query"
        self._session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取 aiohttp session（延迟初始化）。"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
        return self._session

    async def close(self):
        """关闭资源。"""
        if self._session and not self._session.closed:
            await self._session.close()

    async def scan(self, repo_obj) -> List[Finding]:
        """扫描单个仓库的CVE漏洞 - 使用公共 DependencyParser。"""
        findings = []

        # 依赖文件列表
        dep_files = ["requirements.txt", "package.json", "pom.xml", "go.mod"]

        for filename in dep_files:
            try:
                content_file = await asyncio.to_thread(repo_obj.get_contents, filename)
                content = content_file.decoded_content.decode("utf-8", errors="ignore")

                ecosystem = DependencyParser.get_ecosystem(filename)
                deps = DependencyParser.parse(filename, content)

                if not deps or not ecosystem:
                    continue

                logger.debug("cve_dep_file_parsed", file=filename, deps=len(deps))

                session = await self._get_session()
                for dep in deps:
                    version = dep.get("version")

                    # 跳过无效版本：None、空、"unknown"、包含变量占位符
                    if not version:
                        continue
                    if version == "unknown" or "${" in version:
                        logger.debug("skip_invalid_version", package=dep.get("name"), version=version)
                        continue

                    cves = await self._query_osv(session, ecosystem, dep["name"], version)

                    for cve in cves:
                        severity = map_osv_severity(cve)
                        fixed_version = extract_fixed_version(cve)
                        summary_info = extract_summary_info(cve)

                        # 构建更详细的标题
                        cve_id = cve.get("id", "UNKNOWN")
                        title = f"{cve_id}: {dep['name']}@{version}"

                        # 构建详细描述
                        description_parts = []
                        if summary_info.get("summary"):
                            description_parts.append(summary_info["summary"])
                        if fixed_version:
                            description_parts.append(f"建议升级至 {fixed_version}")
                        if summary_info.get("aliases"):
                            aliases_str = ", ".join(summary_info["aliases"][:3])
                            description_parts.append(f"相关: {aliases_str}")
                        description = " | ".join(description_parts) if description_parts else ""

                        findings.append(Finding(
                            repo_full_name=repo_obj.full_name,
                            finding_type="CVE",
                            severity=severity,
                            title=title,
                            description=description,
                            detail={
                                "package": dep["name"],
                                "version": version,
                                "cve_id": cve_id,
                                "fixed_version": fixed_version,
                                "aliases": summary_info.get("aliases", []),
                                "cvss": summary_info.get("cvss", []),
                                "summary": summary_info.get("summary", ""),
                                "references": summary_info.get("references", []),
                                "file": filename,
                                "ecosystem": ecosystem
                            }
                        ))

            except GithubException:
                pass
            except Exception as e:
                logger.warning("cve_scan_error", file=filename, error=str(e))

        return findings

    async def _query_osv(self, session: aiohttp.ClientSession, ecosystem: str,
                          package: str, version: str) -> List[Dict]:
        """查询 OSV.dev API。"""
        payload = {
            "package": {"name": package, "ecosystem": ecosystem},
            "version": version
        }

        try:
            async with session.post(self.osv_api_url, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("vulns", [])
        except aiohttp.ClientError as e:
            logger.warning("osv_query_error", package=package, error=str(e))

        return []