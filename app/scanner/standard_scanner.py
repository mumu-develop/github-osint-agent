"""L2 标准扫描器 - 条件触发 LLM 分析。"""

import os
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any
from github import Github, GithubException
from app.log_utils import get_logger
from app.models import Finding, ScanTask
from app.database import FindingDAO, ScanTaskDAO, OrgConfigDAO, init_business_tables
from app.scanner.light_scanner import LightScanner, SECRET_PATTERNS, ALLOWED_LICENSES, DEPENDENCY_PATTERNS

logger = get_logger("standard_scanner")


class StandardScanner(LightScanner):
    """L2 标准扫描器 - 继承 L1，添加 LLM 深度分析。

    L2 扫描策略：
    1. 先执行 L1 扫描（API + OSV.dev）
    2. 对 L1 发现的高危问题，使用 LLM 进行深度分析
    3. 对复杂社区健康问题，使用 LLM 分析活跃度趋势
    """

    def __init__(self, github_token: str = None, llm_client=None):
        super().__init__(github_token)
        self.llm_client = llm_client
        self.llm_enabled = llm_client is not None or os.getenv("OPENAI_API_KEY")

    async def scan_repo(self, owner: str, repo: str) -> List[Finding]:
        """扫描单个仓库，L2 增加 LLM 分析。"""
        # 1. 执行 L1 扫描
        findings = await super().scan_repo(owner, repo)

        # 2. 对高危问题进行 LLM 深度分析
        high_findings = [f for f in findings if f.severity in ["CRITICAL", "HIGH"]]

        if high_findings and self.llm_enabled:
            llm_findings = await self._llm_deep_analysis(owner, repo, high_findings)
            findings.extend(llm_findings)

        # 3. LLM 分析社区趋势（可选）
        if self.llm_enabled:
            trend_finding = await self._llm_analyze_trend(owner, repo)
            if trend_finding:
                findings.append(trend_finding)

        return findings

    async def _llm_deep_analysis(self, owner: str, repo: str,
                                  findings: List[Finding]) -> List[Finding]:
        """对高危发现进行 LLM 深度分析。"""
        if not self.llm_enabled:
            return []

        import openai
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        new_findings = []

        for f in findings[:5]:  # 只分析前5个高危
            try:
                # 构建 LLM 分析 prompt
                prompt = f"""分析以下安全问题的影响和建议修复方案：

仓库: {f.repo_full_name}
问题类型: {f.finding_type}
严重程度: {f.severity}
标题: {f.title}
描述: {f.description or '无'}
详情: {f.detail}

请提供：
1. 影响范围评估
2. 修复建议
3. 紧急程度评分(1-10)

以 JSON 格式返回:
{"impact": "...", "fix_recommendation": "...", "urgency_score": N}"""

                response = await asyncio.to_thread(
                    lambda: client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.3
                    )
                )

                content = response.choices[0].message.content

                # 尝试解析 JSON
                try:
                    import json
                    analysis = json.loads(content)
                    f.detail["llm_analysis"] = analysis

                    # 根据 urgency_score 更新严重程度
                    if analysis.get("urgency_score") >= 9:
                        f.severity = "CRITICAL"
                    elif analysis.get("urgency_score") >= 7:
                        f.severity = "HIGH"

                except json.JSONDecodeError:
                    f.detail["llm_analysis"] = {"raw": content}

                logger.info("llm_analysis_done", repo=f.repo_full_name, finding=f.id)

            except Exception as e:
                logger.warning("llm_analysis_error", error=str(e))

        return new_findings

    async def _llm_analyze_trend(self, owner: str, repo: str) -> Optional[Finding]:
        """使用 LLM 分析仓库趋势。"""
        try:
            repo_obj = await asyncio.to_thread(self.github.get_repo, f"{owner}/{repo}")

            # 获取统计数据
            stars = repo_obj.stargazers_count
            forks = repo_obj.forks_count
            open_issues = repo_obj.open_issues_count
            pushed_at = repo_obj.pushed_at.isoformat() if repo_obj.pushed_at else None

            # 获取最近 commits
            commits = await asyncio.to_thread(lambda: list(repo_obj.get_commits()[:30]))

            if len(commits) < 10:
                return None

            # 构建 LLM prompt
            import openai
            client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

            prompt = f"""分析以下仓库的活跃度和趋势：

仓库: {owner}/{repo}
Stars: {stars}
Forks: {forks}
Open Issues: {open_issues}
最近更新: {pushed_at}
最近30次提交数: {len(commits)}

请评估：
1. 项目活跃度趋势（上升/稳定/下降）
2. 社区关注度变化
3. 是否有风险信号（如维护停止、安全问题频发）

以简短文字返回结论（不超过100字）。"""

            response = await asyncio.to_thread(
                lambda: client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3
                )
            )

            analysis = response.choices[0].message.content

            # 判断是否需要生成 Finding
            if any(word in analysis.lower() for word in ["下降", "停止", "风险", "警告", "建议关注"]):
                return Finding(
                    repo_full_name=f"{owner}/{repo}",
                    finding_type="TREND",
                    severity="LOW",
                    title=f"趋势分析: {owner}/{repo}",
                    description=analysis,
                    detail={
                        "stars": stars,
                        "forks": forks,
                        "commits_count": len(commits),
                        "pushed_at": pushed_at
                    }
                )

        except Exception as e:
            logger.warning("llm_trend_error", repo=f"{owner}/{repo}", error=str(e))

        return None

    async def scan_org(self, org_name: str, scan_task_id: int = None,
                       trigger_by: str = None, concurrency: int = 20) -> Dict[str, Any]:
        """扫描整个组织（L2 级别）。"""
        logger.info("l2_scan_start", org=org_name)

        await init_business_tables()

        # 获取组织仓库
        try:
            org = await asyncio.to_thread(self.github.get_organization, org_name)
            repos = await asyncio.to_thread(lambda: list(org.get_repos()))
        except GithubException as e:
            return {"error": str(e)}

        # 创建扫描任务
        run_id = f"L2SCAN_{org_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        task = ScanTask(
            run_id=run_id,
            scan_type="L2_STANDARD",
            org_name=org_name,
            trigger_by=trigger_by or "manual",
            status="running",
            total_repos=len(repos)
        )
        task_id = await ScanTaskDAO.create(task)

        # 并发扫描（L2 用更少并发，因为有 LLM 调用）
        semaphore = asyncio.Semaphore(concurrency)
        all_findings = []
        scanned = 0

        async def scan_repo_task(repo):
            async with semaphore:
                findings = await self.scan_repo(org_name, repo.name)
                nonlocal scanned
                scanned += 1

                for f in findings:
                    f.scan_task_id = task_id
                await FindingDAO.batch_create(findings)

                if scanned % 5 == 0:
                    await ScanTaskDAO.update_status(run_id, "running", scanned, len(all_findings))

                return findings

        tasks = [scan_repo_task(repo) for repo in repos]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                all_findings.extend(result)

        await ScanTaskDAO.update_status(run_id, "completed", scanned, len(all_findings))

        return {
            "run_id": run_id,
            "org_name": org_name,
            "repos_scanned": scanned,
            "total_findings": len(all_findings),
            "task_id": task_id
        }