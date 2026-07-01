"""统一扫描工具 - 支持单仓库和多仓库的批处理模式。

所有工具统一使用 repos 参数，支持：
- 单仓库：repos="owner/repo"
- 多仓库：repos="owner/repo1,owner/repo2,owner/repo3"

核心原则：
- 工具名称简洁，不带 "batch" 前缀
- 参数格式统一，智能体无需区分单/多仓库
- 内部并发执行，效率最大化
"""

import os
import asyncio
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from langchain_core.tools import tool
from github import Github, GithubException
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.scanner.batch_tools import BatchScanTools
from app.progress import create_progress_tracker, get_current_session
from app.log_utils import get_logger
from app.models import Finding

logger = get_logger("unified_tools")

# 创建共享的 requests session，增大连接池
_http_session = None

def get_http_session() -> requests.Session:
    """获取共享的 HTTP session，配置连接池和重试策略。"""
    global _http_session
    if _http_session is None:
        _http_session = requests.Session()
        # 配置重试策略
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        # 配置连接池大小
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=20,
            pool_maxsize=30
        )
        _http_session.mount("https://", adapter)
        _http_session.mount("http://", adapter)
    return _http_session


# ============================================================
# 参数解析辅助函数
# ============================================================

def parse_repos(repos: str) -> List[Dict[str, str]]:
    """解析仓库字符串为列表。

    Args:
        repos: 仓库字符串，格式 "owner/repo" 或 "owner/repo1,owner/repo2,..."

    Returns:
        [{"owner": "xxx", "repo": "yyy"}, ...]
    """
    entries = [r.strip() for r in repos.split(",") if r.strip()]
    repo_list = []
    for entry in entries:
        parts = entry.split("/")
        if len(parts) == 2:
            repo_list.append({"owner": parts[0], "repo": parts[1]})
        else:
            logger.warning("invalid_repo_format", entry=entry)
    return repo_list


def format_repo_key(owner: str, repo: str) -> str:
    """生成仓库键名。"""
    return f"{owner}/{repo}"


# ============================================================
# 组织级扫描工具
# ============================================================

@tool
async def scan_org(
    org_name: str,
    dimensions: str = "cve,secret,license,community",
    max_repos: int = 50
) -> dict:
    """扫描整个组织的所有仓库（一键完成，并发50）。

    Args:
        org_name: GitHub组织名称（如 sofastack、alibaba）
        dimensions: 扫描维度，逗号分隔
            - cve: 依赖漏洞扫描
            - secret: 敏感信息泄露扫描
            - license: 许可证合规检查
            - community: 社区健康度检查
        max_repos: 最大扫描仓库数（默认50）

    Returns:
        扫描结果摘要，包含各维度的发现统计
    """
    logger.info("scan_org_start", org=org_name, dimensions=dimensions)

    start_time = asyncio.get_event_loop().time()

    dimension_list = [d.strip().lower() for d in dimensions.split(",")]
    valid_dimensions = {"cve", "secret", "license", "community"}
    scan_dimensions = {d: True for d in dimension_list if d in valid_dimensions}

    if not scan_dimensions:
        scan_dimensions = {"cve": True, "secret": True, "license": True, "community": True}

    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        return {"error": "GITHUB_TOKEN 未配置"}

    try:
        github_client = Github(github_token)
        github_org = await asyncio.to_thread(github_client.get_organization, org_name)
        repos = await asyncio.to_thread(lambda: list(github_org.get_repos()))
    except GithubException as e:
        logger.error("github_org_fetch_failed", org=org_name, error=str(e))
        return {"error": f"无法获取组织 {org_name}: {str(e)}"}

    repos = repos[:max_repos]
    repo_list = [{"owner": org_name, "repo": r.name} for r in repos]

    if not repo_list:
        return {"error": f"组织 {org_name} 没有仓库"}

    logger.info("scan_org_repos_found", org=org_name, count=len(repo_list))

    # 创建进度追踪器（使用当前 session）
    repo_names = [f"{r['owner']}/{r['repo']}" for r in repo_list]
    progress_tracker = create_progress_tracker("security-analyzer", repo_names)
    logger.info("progress_tracker_created", repos_count=len(repo_names))

    batch_tools = BatchScanTools(github_token, concurrency=50)

    all_findings: List[Finding] = []
    findings_by_repo: Dict[str, List[Dict]] = {}  # 改为存储具体问题列表
    findings_by_type: Dict[str, int] = {}

    try:
        if scan_dimensions.get("cve"):
            logger.info("scan_org_cve_start", org=org_name)
            cve_results = await batch_tools.batch_cve_check(repo_list, progress_tracker)
            for repo_name, findings in cve_results.items():
                all_findings.extend(findings)
                if repo_name not in findings_by_repo:
                    findings_by_repo[repo_name] = []
                for f in findings:
                    findings_by_repo[repo_name].append({
                        "type": f.finding_type,
                        "severity": f.severity,
                        "title": f.title,
                        "description": f.description,
                        "detail": f.detail
                    })
                    findings_by_type[f.finding_type] = findings_by_type.get(f.finding_type, 0) + 1

        if scan_dimensions.get("secret"):
            logger.info("scan_org_secret_start", org=org_name)
            secret_results = await batch_tools.batch_secret_scan(repo_list, progress_tracker)
            for repo_name, findings in secret_results.items():
                all_findings.extend(findings)
                if repo_name not in findings_by_repo:
                    findings_by_repo[repo_name] = []
                for f in findings:
                    findings_by_repo[repo_name].append({
                        "type": f.finding_type,
                        "severity": f.severity,
                        "title": f.title,
                        "description": f.description,
                        "detail": f.detail
                    })
                    findings_by_type[f.finding_type] = findings_by_type.get(f.finding_type, 0) + 1

        if scan_dimensions.get("license"):
            logger.info("scan_org_license_start", org=org_name)
            license_results = await batch_tools.batch_license_check(repo_list, progress_tracker)
            for repo_name, findings in license_results.items():
                all_findings.extend(findings)
                if repo_name not in findings_by_repo:
                    findings_by_repo[repo_name] = []
                for f in findings:
                    findings_by_repo[repo_name].append({
                        "type": f.finding_type,
                        "severity": f.severity,
                        "title": f.title,
                        "description": f.description,
                        "detail": f.detail
                    })
                    findings_by_type[f.finding_type] = findings_by_type.get(f.finding_type, 0) + 1

        if scan_dimensions.get("community"):
            logger.info("scan_org_community_start", org=org_name)
            community_results = await batch_tools.batch_community_check(repo_list, progress_tracker)
            for repo_name, findings in community_results.items():
                all_findings.extend(findings)
                if repo_name not in findings_by_repo:
                    findings_by_repo[repo_name] = []
                for f in findings:
                    findings_by_repo[repo_name].append({
                        "type": f.finding_type,
                        "severity": f.severity,
                        "title": f.title,
                        "description": f.description,
                        "detail": f.detail
                    })
                    findings_by_type[f.finding_type] = findings_by_type.get(f.finding_type, 0) + 1

    except Exception as e:
        logger.error("scan_org_error", error=str(e))
        return {"error": f"扫描失败: {str(e)}"}
    finally:
        await batch_tools.close()

    end_time = asyncio.get_event_loop().time()
    duration_seconds = int(end_time - start_time)

    high_critical = [f for f in all_findings if f.severity in ["CRITICAL", "HIGH"]]
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
    sorted_findings = sorted(all_findings, key=lambda f: severity_order.get(f.severity, 5))

    return {
        "org_name": org_name,
        "repos_scanned": len(repo_list),
        "dimensions_scanned": list(scan_dimensions.keys()),
        "total_findings": len(all_findings),
        "high_severity_count": len(high_critical),
        "findings_by_type": findings_by_type,
        "findings_by_repo": findings_by_repo,
        "top_findings": [
            {
                "repo": f.repo_full_name,
                "type": f.finding_type,
                "severity": f.severity,
                "title": f.title,
                "description": f.description,
                "detail": f.detail
            }
            for f in sorted_findings[:20]
        ],
        "scan_duration_seconds": duration_seconds,
    }


# ============================================================
# CVE 工具（两类）
# ============================================================

@tool
async def check_cve_repos(repos: str) -> dict:
    """检查仓库的CVE漏洞（支持单仓库或多仓库）。

    Args:
        repos: 仓库，格式：
            - 单仓库："owner/repo"
            - 多仓库："owner/repo1,owner/repo2,owner/repo3"

    Returns:
        各仓库的CVE漏洞发现汇总
    """
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        return {"error": "GITHUB_TOKEN 未配置"}

    repo_list = parse_repos(repos)
    if not repo_list:
        return {"error": "仓库格式无效，请使用 owner/repo 格式"}

    logger.info("check_cve_repos_start", repos_count=len(repo_list))

    batch_tools = BatchScanTools(github_token, concurrency=50)
    try:
        results = await batch_tools.batch_cve_check(repo_list)
    except Exception as e:
        return {"error": f"CVE检查失败: {str(e)}"}
    finally:
        await batch_tools.close()

    total = sum(len(f) for f in results.values())
    high_critical = sum(1 for findings in results.values()
                       for f in findings if f.severity in ["CRITICAL", "HIGH"])

    return {
        "repos_checked": len(repo_list),
        "total_cve_findings": total,
        "high_critical_count": high_critical,
        "findings_by_repo": {
            repo: [{
                "severity": f.severity,
                "title": f.title,
                "description": f.description,
                "detail": f.detail
            } for f in findings]
            for repo, findings in results.items()
        }
    }


@tool
async def check_package_cve(ecosystem: str, package: str, version: str) -> list:
    """查询单个依赖包的CVE漏洞（深度分析）。

    用于查询特定包版本的安全问题，如 "requests 2.28.0 有什么漏洞"。

    Args:
        ecosystem: 包生态系统（PyPI, npm, Maven, Go, Cargo）
        package: 包名称
        version: 版本号

    Returns:
        CVE漏洞列表
    """
    def _check_sync():
        url = "https://api.osv.dev/v1/query"
        payload = {"package": {"name": package, "ecosystem": ecosystem}, "version": version}
        try:
            session = get_http_session()
            resp = session.post(url, json=payload, timeout=15)
            if resp.status_code == 200:
                vulns = resp.json().get("vulns", [])
                return [
                    {"id": v.get("id"), "summary": v.get("summary"),
                     "severity": v.get("severity", [{}])[0].get("type", "UNKNOWN")}
                    for v in vulns[:5]
                ]
        except Exception:
            pass
        return []

    logger.info("check_package_cve", ecosystem=ecosystem, package=package, version=version)
    return await asyncio.to_thread(_check_sync)


# ============================================================
# 敏感信息扫描
# ============================================================

@tool
async def scan_secrets(repos: str) -> dict:
    """扫描仓库的敏感信息泄露（支持单仓库或多仓库）。

    Args:
        repos: 仓库，格式：
            - 单仓库："owner/repo"
            - 多仓库："owner/repo1,owner/repo2"

    Returns:
        各仓库的敏感信息发现汇总
    """
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        return {"error": "GITHUB_TOKEN 未配置"}

    repo_list = parse_repos(repos)
    if not repo_list:
        return {"error": "仓库格式无效"}

    logger.info("scan_secrets_start", repos_count=len(repo_list))

    batch_tools = BatchScanTools(github_token, concurrency=50)
    try:
        results = await batch_tools.batch_secret_scan(repo_list)
    except Exception as e:
        return {"error": f"扫描失败: {str(e)}"}
    finally:
        await batch_tools.close()

    total = sum(len(f) for f in results.values())

    return {
        "repos_scanned": len(repo_list),
        "total_secret_findings": total,
        "findings_by_repo": {
            repo: [{
                "severity": f.severity,
                "title": f.title,
                "description": f.description,
                "detail": f.detail
            } for f in findings]
            for repo, findings in results.items() if findings
        }
    }


# ============================================================
# 许可证检查
# ============================================================

@tool
async def check_license(repos: str) -> dict:
    """检查仓库的许可证合规性（支持单仓库或多仓库）。

    Args:
        repos: 仓库，格式：
            - 单仓库："owner/repo"
            - 多仓库："owner/repo1,owner/repo2"

    Returns:
        各仓库的许可证信息汇总
    """
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        return {"error": "GITHUB_TOKEN 未配置"}

    repo_list = parse_repos(repos)
    if not repo_list:
        return {"error": "仓库格式无效"}

    logger.info("check_license_start", repos_count=len(repo_list))

    batch_tools = BatchScanTools(github_token, concurrency=50)
    try:
        results = await batch_tools.batch_license_check(repo_list)
    except Exception as e:
        return {"error": f"许可证检查失败: {str(e)}"}
    finally:
        await batch_tools.close()

    return {
        "repos_checked": len(repo_list),
        "findings_by_repo": {
            repo: [{
                "severity": f.severity,
                "title": f.title,
                "description": f.description,
                "detail": f.detail
            } for f in findings]
            for repo, findings in results.items()
        }
    }


# ============================================================
# 版权扫描
# ============================================================

@tool
async def scan_copyright(repos: str) -> dict:
    """扫描仓库的版权声明（支持单仓库或多仓库）。

    Args:
        repos: 仓库，格式：
            - 单仓库："owner/repo"
            - 多仓库："owner/repo1,owner/repo2"

    Returns:
        各仓库的版权声明发现汇总
    """
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        return {"error": "GITHUB_TOKEN 未配置"}

    repo_list = parse_repos(repos)
    if not repo_list:
        return {"error": "仓库格式无效"}

    logger.info("scan_copyright_start", repos_count=len(repo_list))

    github_client = Github(github_token)
    pattern = r"Copyright\s+©?\s*\d{4}"
    results: Dict[str, List] = {}

    async def scan_single(entry: Dict):
        owner, repo = entry["owner"], entry["repo"]
        repo_key = format_repo_key(owner, repo)
        try:
            gh_repo = await asyncio.to_thread(github_client.get_repo, repo_key)
            contents = await asyncio.to_thread(lambda: list(gh_repo.get_contents("")))

            findings = []
            for item in contents[:20]:  # 限制扫描数量
                if item.type == "file" and item.name.endswith((".py", ".java", ".js", ".go")):
                    content = item.decoded_content.decode('utf-8', errors='ignore')
                    if "Copyright" in content or "©" in content:
                        findings.append({"file": item.path, "has_copyright": True})
            return repo_key, findings
        except Exception as e:
            return repo_key, [{"error": str(e)}]

    tasks = [scan_single(entry) for entry in repo_list]
    for repo_key, findings in await asyncio.gather(*tasks):
        results[repo_key] = findings

    return {
        "repos_scanned": len(repo_list),
        "findings_by_repo": results
    }


# ============================================================
# 社区健康度检查
# ============================================================

@tool
async def check_community(repos: str, days: int = 30) -> dict:
    """检查仓库的社区健康度（支持单仓库或多仓库）。

    Args:
        repos: 仓库，格式：
            - 单仓库："owner/repo"
            - 多仓库："owner/repo1,owner/repo2"
        days: 统计最近多少天的活动（默认30天）

    Returns:
        各仓库的社区健康度汇总
    """
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        return {"error": "GITHUB_TOKEN 未配置"}

    repo_list = parse_repos(repos)
    if not repo_list:
        return {"error": "仓库格式无效"}

    logger.info("check_community_start", repos_count=len(repo_list))

    batch_tools = BatchScanTools(github_token, concurrency=50)
    try:
        results = await batch_tools.batch_community_check(repo_list)
    except Exception as e:
        return {"error": f"社区检查失败: {str(e)}"}
    finally:
        await batch_tools.close()

    return {
        "repos_checked": len(repo_list),
        "days_analyzed": days,
        "findings_by_repo": {
            repo: [{
                "severity": f.severity,
                "title": f.title,
                "description": f.description,
                "detail": f.detail
            } for f in findings]
            for repo, findings in results.items()
        }
    }


# ============================================================
# Issue/PR/贡献者 统计
# ============================================================

@tool
async def get_issue_metrics(repos: str) -> dict:
    """获取仓库的Issue统计（支持单仓库或多仓库）。

    使用 GitHub REST API 批量获取，避免逐个 Issue 请求。

    Args:
        repos: 仓库，格式："owner/repo" 或 "owner/repo1,owner/repo2"

    Returns:
        各仓库的Issue总数、打开数、平均关闭时间
    """
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        return {"error": "GITHUB_TOKEN 未配置"}

    repo_list = parse_repos(repos)
    if not repo_list:
        return {"error": "仓库格式无效"}

    results: Dict[str, Dict] = {}
    session = get_http_session()
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github.v3+json"
    }

    async def get_single(entry: Dict):
        owner, repo = entry["owner"], entry["repo"]
        repo_key = format_repo_key(owner, repo)

        try:
            # 直接用 REST API 批量获取 Issue 列表（含完整信息）
            url = f"https://api.github.com/repos/{owner}/{repo}/issues?state=all&per_page=100"

            resp = await asyncio.to_thread(
                session.get, url, headers=headers, timeout=30
            )

            if resp.status_code != 200:
                return repo_key, {"error": f"API返回 {resp.status_code}"}

            issues = resp.json()

            # 过滤掉 PR（GitHub API 返回的 issues 包含 PR）
            real_issues = [i for i in issues if "pull_request" not in i]

            open_issues = [i for i in real_issues if i.get("state") == "open"]
            closed_issues = [i for i in real_issues if i.get("state") == "closed"]

            avg_close_hours = 0
            if closed_issues:
                total_seconds = 0
                for i in closed_issues:
                    created = i.get("created_at")
                    closed = i.get("closed_at")
                    if created and closed:
                        from datetime import datetime
                        created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                        closed_dt = datetime.fromisoformat(closed.replace("Z", "+00:00"))
                        total_seconds += (closed_dt - created_dt).total_seconds()

                avg_close_hours = total_seconds / len(closed_issues) / 3600

            return repo_key, {
                "total": len(real_issues),
                "open": len(open_issues),
                "closed": len(closed_issues),
                "avg_close_hours": round(avg_close_hours, 1)
            }

        except Exception as e:
            return repo_key, {"error": str(e)}

    tasks = [get_single(entry) for entry in repo_list]
    for repo_key, data in await asyncio.gather(*tasks):
        results[repo_key] = data

    return {
        "repos_checked": len(repo_list),
        "metrics_by_repo": results
    }


@tool
async def get_pr_metrics(repos: str) -> dict:
    """获取仓库的PR统计（支持单仓库或多仓库）。

    使用 GitHub REST API 批量获取，避免逐个 PR 请求。

    Args:
        repos: 仓库，格式："owner/repo" 或 "owner/repo1,owner/repo2"

    Returns:
        各仓库的PR总数、合并数、平均合并时间
    """
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        return {"error": "GITHUB_TOKEN 未配置"}

    repo_list = parse_repos(repos)
    if not repo_list:
        return {"error": "仓库格式无效"}

    results: Dict[str, Dict] = {}
    session = get_http_session()
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github.v3+json"
    }

    async def get_single(entry: Dict):
        owner, repo = entry["owner"], entry["repo"]
        repo_key = format_repo_key(owner, repo)

        try:
            # 直接用 REST API 批量获取 PR 列表（含完整信息）
            url = f"https://api.github.com/repos/{owner}/{repo}/pulls?state=all&per_page=100"

            resp = await asyncio.to_thread(
                session.get, url, headers=headers, timeout=30
            )

            if resp.status_code != 200:
                return repo_key, {"error": f"API返回 {resp.status_code}"}

            prs = resp.json()

            # 从 API 返回中直接提取信息，无需额外请求
            total = len(prs)
            merged_prs = [p for p in prs if p.get("merged_at")]

            avg_merge_hours = 0
            if merged_prs:
                total_seconds = 0
                for p in merged_prs:
                    created = p.get("created_at")
                    merged = p.get("merged_at")
                    if created and merged:
                        # 解析 ISO 时间格式
                        from datetime import datetime
                        created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                        merged_dt = datetime.fromisoformat(merged.replace("Z", "+00:00"))
                        total_seconds += (merged_dt - created_dt).total_seconds()

                avg_merge_hours = total_seconds / len(merged_prs) / 3600

            return repo_key, {
                "total": total,
                "merged": len(merged_prs),
                "open": len([p for p in prs if p.get("state") == "open"]),
                "avg_merge_hours": round(avg_merge_hours, 1)
            }

        except Exception as e:
            return repo_key, {"error": str(e)}

    tasks = [get_single(entry) for entry in repo_list]
    for repo_key, data in await asyncio.gather(*tasks):
        results[repo_key] = data

    return {
        "repos_checked": len(repo_list),
        "metrics_by_repo": results
    }


@tool
async def get_contributor_activity(repos: str, days: int = 30) -> dict:
    """获取仓库的贡献者活跃度（支持单仓库或多仓库）。

    Args:
        repos: 仓库，格式："owner/repo" 或 "owner/repo1,owner/repo2"
        days: 统计最近多少天（默认30天）

    Returns:
        各仓库的活跃贡献者数、提交数
    """
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        return {"error": "GITHUB_TOKEN 未配置"}

    repo_list = parse_repos(repos)
    if not repo_list:
        return {"error": "仓库格式无效"}

    github_client = Github(github_token)
    since = datetime.now() - timedelta(days=days)
    results: Dict[str, Dict] = {}

    async def get_single(entry: Dict):
        owner, repo = entry["owner"], entry["repo"]
        repo_key = format_repo_key(owner, repo)
        try:
            gh_repo = await asyncio.to_thread(github_client.get_repo, repo_key)
            commits = await asyncio.to_thread(lambda: list(gh_repo.get_commits(since=since)))

            contributors = {}
            for commit in commits:
                author = commit.author.login if commit.author else "unknown"
                contributors[author] = contributors.get(author, 0) + 1

            return repo_key, {
                "active_contributors": len(contributors),
                "commits": len(commits),
                "top_contributors": sorted(contributors.items(), key=lambda x: x[1], reverse=True)[:5]
            }
        except Exception as e:
            return repo_key, {"error": str(e)}

    tasks = [get_single(entry) for entry in repo_list]
    for repo_key, data in await asyncio.gather(*tasks):
        results[repo_key] = data

    return {
        "repos_checked": len(repo_list),
        "days_analyzed": days,
        "metrics_by_repo": results
    }


# ============================================================
# 依赖文件获取
# ============================================================

@tool
async def get_dependency_files(repos: str) -> dict:
    """获取仓库的依赖文件内容（支持单仓库或多仓库）。

    Args:
        repos: 仓库，格式："owner/repo" 或 "owner/repo1,owner/repo2"

    Returns:
        各仓库的依赖文件内容（requirements.txt, package.json 等）
    """
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        return {"error": "GITHUB_TOKEN 未配置"}

    repo_list = parse_repos(repos)
    if not repo_list:
        return {"error": "仓库格式无效"}

    logger.info("get_dependency_files_start", repos_count=len(repo_list))

    github_client = Github(github_token)

    dep_files_list = [
        "requirements.txt", "package.json", "pom.xml",
        "build.gradle", "go.mod", "Cargo.toml", "composer.json"
    ]

    async def get_single(entry: Dict):
        owner, repo = entry["owner"], entry["repo"]
        repo_key = format_repo_key(owner, repo)
        try:
            gh_repo = await asyncio.to_thread(github_client.get_repo, repo_key)

            contents: Dict[str, str] = {}
            for file_name in dep_files_list:
                try:
                    content_file = await asyncio.to_thread(gh_repo.get_contents, file_name)
                    if content_file:
                        contents[file_name] = content_file.decoded_content.decode("utf-8")[:500]
                except Exception:
                    pass

            return repo_key, {"files": contents, "found": len(contents)}
        except Exception as e:
            return repo_key, {"error": str(e)}

    tasks = [get_single(entry) for entry in repo_list]
    results = {}
    for repo_key, data in await asyncio.gather(*tasks):
        results[repo_key] = data

    total_found = sum(d.get("found", 0) for d in results.values() if "found" in d)

    return {
        "repos_checked": len(repo_list),
        "total_dependency_files_found": total_found,
        "results_by_repo": results
    }


# ============================================================
# Star历史和仓库统计
# ============================================================

@tool
async def get_star_history(repos: str, limit: int = 100) -> dict:
    """获取仓库的Star历史（支持单仓库或多仓库）。

    Args:
        repos: 仓库，格式："owner/repo" 或 "owner/repo1,owner/repo2"
        limit: 每个仓库获取的star数量（默认100）

    Returns:
        各仓库的Star历史数据
    """
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        return {"error": "GITHUB_TOKEN 未配置"}

    repo_list = parse_repos(repos)
    if not repo_list:
        return {"error": "仓库格式无效"}

    results: Dict[str, List] = {}

    async def get_single(entry: Dict):
        owner, repo = entry["owner"], entry["repo"]
        repo_key = format_repo_key(owner, repo)

        headers = {
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github.v3.star+json"
        }
        url = f"https://api.github.com/repos/{owner}/{repo}/stargazers?per_page={limit}"

        try:
            session = get_http_session()
            resp = await asyncio.to_thread(session.get, url, headers=headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                star_by_date = {}
                for item in data:
                    if "starred_at" in item:
                        date = item["starred_at"][:10]
                        star_by_date[date] = star_by_date.get(date, 0) + 1
                history = [{"date": d, "stars": s} for d, s in sorted(star_by_date.items())]
                return repo_key, {"history": history, "total_stars": len(data)}
        except Exception:
            pass

        # 备用方案
        try:
            g = Github(github_token)
            gh_repo = await asyncio.to_thread(g.get_repo, repo_key)
            return repo_key, {"total_stars": gh_repo.stargazers_count, "history": []}
        except:
            return repo_key, {"error": "获取失败"}

    tasks = [get_single(entry) for entry in repo_list]
    for repo_key, data in await asyncio.gather(*tasks):
        results[repo_key] = data

    return {
        "repos_checked": len(repo_list),
        "history_by_repo": results
    }


@tool
async def get_repo_stats(repos: str) -> dict:
    """获取仓库的基本统计信息（支持单仓库或多仓库）。

    Args:
        repos: 仓库，格式："owner/repo" 或 "owner/repo1,owner/repo2"

    Returns:
        各仓库的Star数、Fork数、Issue数、贡献者数等
    """
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        return {"error": "GITHUB_TOKEN 未配置"}

    repo_list = parse_repos(repos)
    if not repo_list:
        return {"error": "仓库格式无效"}

    github_client = Github(github_token)
    results: Dict[str, Dict] = {}

    async def get_single(entry: Dict):
        owner, repo = entry["owner"], entry["repo"]
        repo_key = format_repo_key(owner, repo)
        try:
            gh_repo = await asyncio.to_thread(github_client.get_repo, repo_key)
            contributors = await asyncio.to_thread(lambda: list(gh_repo.get_contributors()[:50]))

            return repo_key, {
                "name": gh_repo.name,
                "stars": gh_repo.stargazers_count,
                "forks": gh_repo.forks_count,
                "open_issues": gh_repo.open_issues_count,
                "contributors_count": len(contributors),
                "language": gh_repo.language,
                "topics": gh_repo.get_topics(),
            }
        except Exception as e:
            return repo_key, {"error": str(e)}

    tasks = [get_single(entry) for entry in repo_list]
    for repo_key, data in await asyncio.gather(*tasks):
        results[repo_key] = data

    return {
        "repos_checked": len(repo_list),
        "stats_by_repo": results
    }


@tool
async def get_org_repos(org_name: str) -> dict:
    """获取组织下的所有仓库列表。

    Args:
        org_name: GitHub组织名称

    Returns:
        仓库列表，包含名称、Star数、Fork数、语言、Topics等
    """
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        return {"error": "GITHUB_TOKEN 未配置"}

    try:
        github_client = Github(github_token)
        org = await asyncio.to_thread(github_client.get_organization, org_name)
        repos = await asyncio.to_thread(lambda: list(org.get_repos()))

        return {
            "org_name": org_name,
            "repos_count": len(repos),
            "repos": [
                {
                    "name": r.name,
                    "stars": r.stargazers_count,
                    "forks": r.forks_count,
                    "language": r.language,
                    "topics": r.get_topics(),
                }
                for r in repos[:50]
            ]
        }
    except Exception as e:
        return {"error": f"获取组织仓库失败: {str(e)}"}


@tool
async def calculate_growth_rate(history: list, days: int = 7) -> float:
    """计算增长率（纯计算逻辑，不需要数据获取）。

    Args:
        history: Star历史数据，格式 [{"date": "YYYY-MM-DD", "stars": N}, ...]
        days: 计算增长的天数

    Returns:
        增长率（百分比）
    """
    if not history or len(history) < 2:
        return 0.0

    sorted_history = sorted(history, key=lambda x: x.get("date", ""))
    recent = sorted_history[-days:] if len(sorted_history) >= days else sorted_history
    first_stars = recent[0].get("stars", 0)
    last_stars = recent[-1].get("stars", 0)

    if first_stars == 0:
        return 0.0

    return round((last_stars - first_stars) / first_stars * 100, 2)


# ============================================================
# 导出工具列表
# ============================================================

# 核心扫描工具
scan_tools = [
    scan_org,
    check_cve_repos,
    check_package_cve,
    scan_secrets,
    check_license,
    scan_copyright,
    check_community,
]

# 统计工具
metrics_tools = [
    get_issue_metrics,
    get_pr_metrics,
    get_contributor_activity,
    get_dependency_files,
    get_star_history,
    get_repo_stats,
    get_org_repos,
]

# 计算工具
calc_tools = [
    calculate_growth_rate,
]

# 全部工具
all_tools = scan_tools + metrics_tools + calc_tools