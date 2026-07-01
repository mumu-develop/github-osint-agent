"""混合扫描器 - 批量工具层 + Agent深度分析层。

重构说明:
- 提取内部方法为类方法，消除重复
- 统一扫描逻辑 (_scan_repo_single)
- 统一统计计算 (_build_summary)
- 使用公共工具模块
"""

import os
import asyncio
from datetime import datetime
from typing import Dict, List, Any, Optional, Set
from github import Github, GithubException
from app.log_utils import get_logger
from app.models import Finding, ScanTask, ScanSubTask
from app.database import (
    FindingDAO, ScanTaskDAO, ScanSubTaskDAO, ScanHistoryDAO,
    init_business_tables
)
from app.scanner.batch_tools import BatchScanTools
from app.scanner.scan_config import (
    subtask_timeout, max_retries, retry_delay,
    failure_threshold, max_concurrency, progress_check_interval
)
from app.utils.severity_mapper import SeverityMapper

logger = get_logger("hybrid_scanner")


class HybridScanner:
    """混合扫描器 - 批量工具 + Agent深度分析。

    扫描流程:
    1. 批量工具层：快速扫描所有仓库
    2. 高危筛选：识别需要深度分析的仓库
    3. Agent深度分析：对高危仓库调用LLM

    扫描模式:
    - fast: 仅批量工具层
    - balanced: 批量工具 + 高危仓库Agent分析（推荐）
    - deep: 批量工具 + 全量Agent分析
    """

    HIGH_RISK_SEVERITIES = ["CRITICAL", "HIGH"]
    DEFAULT_DIMENSIONS = {"cve": True, "secret": True, "license": True, "community": True}

    def __init__(self, dimensions: Dict[str, bool] = None, llm_enabled: bool = False,
                 scan_mode: str = "balanced", github_token: str = None, session_id: str = "default"):
        self.dimensions = dimensions or self.DEFAULT_DIMENSIONS.copy()
        self.scan_mode = scan_mode
        self.session_id = session_id
        self.github_token = github_token or os.getenv("GITHUB_TOKEN")
        self.github = Github(self.github_token)
        self.batch_tools = BatchScanTools(github_token, concurrency=50)

    async def close(self):
        """关闭资源。"""
        await self.batch_tools.close()

    # ==================== 核心扫描方法 ====================

    async def _scan_repo_dimensions(self, owner: str, repo_name: str) -> List[Finding]:
        """执行单个仓库的多维度扫描（核心扫描逻辑）。

        Args:
            owner: 仓库所有者
            repo_name: 仓库名称

        Returns:
            所有维度的 Finding 列表
        """
        findings = []

        if self.dimensions.get("cve"):
            findings.extend(await self.batch_tools.cve_check_single(owner, repo_name))

        if self.dimensions.get("secret"):
            findings.extend(await self.batch_tools.secret_check_single(owner, repo_name))

        if self.dimensions.get("license"):
            findings.extend(await self.batch_tools.license_check_single(owner, repo_name))

        if self.dimensions.get("community"):
            findings.extend(await self.batch_tools.community_check_single(owner, repo_name))

        return findings

    async def _scan_repo_with_retry(self, repo_full_name: str, task_id: int,
                                     run_id: str, high_risk_repos: Set[str]) -> List[Finding]:
        """扫描单个仓库（带超时、重试、状态更新）。

        Args:
            repo_full_name: 仓库全名
            task_id: 主任务ID
            run_id: 任务运行ID
            high_risk_repos: 高危仓库集合（会被更新）

        Returns:
            Finding 列表
        """
        owner, repo_name = repo_full_name.split("/")
        semaphore = asyncio.Semaphore(max_concurrency())

        async with semaphore:
            await ScanSubTaskDAO.update_status_by_repo(repo_full_name, task_id, "running")
            error_msg = ""

            for attempt in range(max_retries() + 1):
                # 检查是否暂停
                current_task = await ScanTaskDAO.get_by_run_id(run_id)
                if current_task and current_task.status == "paused":
                    await ScanSubTaskDAO.update_status_by_repo(repo_full_name, task_id, "paused")
                    return []

                try:
                    repo_findings = await asyncio.wait_for(
                        self._scan_repo_dimensions(owner, repo_name),
                        timeout=subtask_timeout()
                    )

                    high_count = len([f for f in repo_findings if f.severity in self.HIGH_RISK_SEVERITIES])
                    await ScanSubTaskDAO.update_status_by_repo(
                        repo_full_name, task_id, "completed",
                        findings_count=len(repo_findings),
                        high_severity_count=high_count
                    )

                    if high_count > 0:
                        high_risk_repos.add(repo_full_name)

                    return repo_findings

                except asyncio.TimeoutError:
                    error_msg = f"超时({subtask_timeout()}秒)"
                    logger.warning("repo_scan_timeout", repo=repo_full_name, attempt=attempt + 1)
                    if attempt < max_retries():
                        await asyncio.sleep(retry_delay())
                        continue

                except GithubException as e:
                    error_msg = f"GitHub API错误: {str(e)[:100]}"
                    logger.warning("repo_github_error", repo=repo_full_name, error=str(e))
                    break

                except Exception as e:
                    error_msg = f"异常: {str(e)[:100]}"
                    logger.warning("repo_scan_error", repo=repo_full_name, error=str(e))
                    if attempt < max_retries():
                        await asyncio.sleep(retry_delay())
                        continue

            # 最终失败
            await ScanSubTaskDAO.update_status_by_repo(repo_full_name, task_id, "failed", error_message=error_msg)
            return []

    async def _check_failure_threshold(self, task_id: int) -> bool:
        """检查失败率是否超过阈值。"""
        progress = await ScanSubTaskDAO.get_progress(task_id)
        total = progress.get("completed", 0) + progress.get("failed", 0) + progress.get("running", 0)

        if total > 10:
            rate = progress.get("failed", 0) / total
            if rate > failure_threshold():
                logger.error("high_failure_rate", rate=rate, failed=progress.get("failed", 0))
                return True
        return False

    # ==================== 统计计算 ====================

    def _build_summary(self, findings: List[Finding], high_risk_repos: Set[str]) -> Dict[str, Any]:
        """构建扫描结果摘要。

        Args:
            findings: 所有发现
            high_risk_repos: 高危仓库集合

        Returns:
            摘要统计字典
        """
        summary = {
            "by_severity": {
                "critical": len([f for f in findings if f.severity == "CRITICAL"]),
                "high": len([f for f in findings if f.severity == "HIGH"]),
                "medium": len([f for f in findings if f.severity == "MEDIUM"]),
                "low": len([f for f in findings if f.severity == "LOW"]),
                "info": len([f for f in findings if f.severity == "INFO"]),
            },
            "by_type": {},
            "high_risk_repos": list(high_risk_repos)
        }

        for f in findings:
            summary["by_type"][f.finding_type] = summary["by_type"].get(f.finding_type, 0) + 1

        return summary

    # ==================== 主扫描入口 ====================

    async def scan_org(self, org_name: str, trigger_by: str = "manual") -> Dict[str, Any]:
        """扫描整个组织（带子任务进度跟踪）。"""
        logger.info("hybrid_scan_org_start", org=org_name, mode=self.scan_mode)

        await init_business_tables()

        # 1. 获取仓库列表
        repos = await self._get_org_repos(org_name)
        if not repos:
            return {"error": "无法获取组织仓库", "repos_scanned": 0}
        total_repos = len(repos)

        # 2. 创建任务和子任务
        run_id, task_id = await self._create_scan_task(org_name, trigger_by, total_repos)
        await self._create_subtasks(task_id, repos)

        # 3. 初始化阶段进度
        phase_progress = self._init_phase_progress(total_repos)
        await ScanTaskDAO.update_phase(run_id, "scanning", phase_progress)

        # 4. 执行扫描
        all_findings, high_risk_repos, scanned_count, stop_reason = await self._execute_scan(
            repos, task_id, run_id, phase_progress
        )

        # 保存 findings
        for f in all_findings:
            f.scan_task_id = task_id
        await FindingDAO.batch_create(all_findings)

        # 5. 处理停止原因
        if stop_reason:
            return await self._handle_stop_reason(run_id, task_id, stop_reason, scanned_count, all_findings)

        # 6. Agent深度分析
        agent_findings = await self._run_agent_analysis(org_name, high_risk_repos, task_id, run_id)
        all_findings.extend(agent_findings)

        # 7. 生成报告
        await self._generate_report(org_name, task_id, run_id)

        # 8. 归档
        await self._archive_scan(run_id, task_id, all_findings, high_risk_repos)

        # 9. 完成
        await ScanTaskDAO.update_status(run_id, "completed", total_repos, len(all_findings))
        await ScanTaskDAO.update_phase(run_id, "done")

        return {
            "run_id": run_id,
            "org_name": org_name,
            "repos_scanned": total_repos,
            "total_findings": len(all_findings),
            "batch_findings": len(all_findings) - len(agent_findings),
            "agent_findings": len(agent_findings),
            "high_severity_count": len([f for f in all_findings if f.severity in self.HIGH_RISK_SEVERITIES]),
            "high_risk_repos": list(high_risk_repos),
            "scan_mode": self.scan_mode,
            "task_id": task_id
        }

    async def continue_scan(self, org_name: str, task_id: int, run_id: str) -> Dict[str, Any]:
        """继续已创建的扫描任务。"""
        logger.info("hybrid_continue_scan_start", org=org_name, task_id=task_id)

        pending_subtasks = await ScanSubTaskDAO.list_by_scan_task(task_id)
        if not pending_subtasks:
            await ScanTaskDAO.update_status(run_id, "failed", error_message="无子任务")
            return {"error": "无子任务", "repos_scanned": 0}

        total_repos = len(pending_subtasks)
        phase_progress = self._init_phase_progress(total_repos)
        await ScanTaskDAO.update_phase(run_id, "scanning", phase_progress)

        # 执行扫描
        repos = [{"full_name": st.repo_full_name} for st in pending_subtasks]
        all_findings, high_risk_repos, scanned_count, stop_reason = await self._execute_scan(
            repos, task_id, run_id, phase_progress, is_continue=True
        )

        # 保存 findings
        for f in all_findings:
            f.scan_task_id = task_id
        await FindingDAO.batch_create(all_findings)

        if stop_reason == "paused":
            return {"run_id": run_id, "status": "paused", "repos_scanned": scanned_count}

        # Agent分析
        agent_findings = await self._run_agent_analysis(org_name, high_risk_repos, task_id, run_id)
        all_findings.extend(agent_findings)

        # 生成报告 + 归档
        await self._generate_report(org_name, task_id, run_id)
        await self._archive_scan(run_id, task_id, all_findings, high_risk_repos)

        await ScanTaskDAO.update_status(run_id, "completed", total_repos, len(all_findings))
        await ScanTaskDAO.update_phase(run_id, "done")

        return {
            "run_id": run_id,
            "org_name": org_name,
            "repos_scanned": scanned_count,
            "total_findings": len(all_findings),
            "high_risk_repos": list(high_risk_repos),
            "task_id": task_id
        }

    # ==================== 辅助方法 ====================

    async def _get_org_repos(self, org_name: str) -> List:
        """获取组织仓库列表。"""
        try:
            org = await asyncio.to_thread(self.github.get_organization, org_name)
            repos = await asyncio.to_thread(lambda: list(org.get_repos()))
            logger.info("repos_fetched", org=org_name, count=len(repos))
            return repos
        except GithubException as e:
            logger.error("org_fetch_failed", org=org_name, error=str(e))
            return []

    async def _create_scan_task(self, org_name: str, trigger_by: str, total_repos: int) -> tuple:
        """创建扫描主任务。"""
        run_id = f"HYBRID_{org_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        task = ScanTask(
            run_id=run_id,
            scan_type=f"HYBRID_{self.scan_mode.upper()}",
            org_name=org_name,
            trigger_by=trigger_by,
            status="running",
            total_repos=total_repos
        )
        task_id = await ScanTaskDAO.create(task)
        return run_id, task_id

    async def _create_subtasks(self, task_id: int, repos: List) -> int:
        """创建扫描子任务。"""
        subtasks = [
            ScanSubTask(scan_task_id=task_id, repo_full_name=r.full_name, status="pending")
            for r in repos
        ]
        await ScanSubTaskDAO.batch_create(subtasks)
        return len(subtasks)

    def _init_phase_progress(self, total_repos: int) -> Dict:
        """初始化阶段进度。"""
        progress = {}
        for dim in ["cve", "secret", "license", "community"]:
            if self.dimensions.get(dim):
                progress[dim] = {"done": 0, "total": total_repos}
        return progress

    async def _execute_scan(self, repos: List, task_id: int, run_id: str,
                            phase_progress: Dict, is_continue: bool = False) -> tuple:
        """执行批量扫描。"""
        all_findings = []
        high_risk_repos = set()
        scanned_count = 0
        stop_reason = None

        repo_names = [r.full_name if hasattr(r, 'full_name') else r["full_name"] for r in repos]
        scan_tasks = {}

        for name in repo_names:
            task = asyncio.create_task(
                self._scan_repo_with_retry(name, task_id, run_id, high_risk_repos)
            )
            scan_tasks[task] = name

        pending = set(scan_tasks.keys())

        while pending:
            # 检查暂停
            current = await ScanTaskDAO.get_by_run_id(run_id)
            if current and current.status == "paused":
                stop_reason = "paused"
                for t in pending:
                    t.cancel()
                break

            # 检查失败率
            if await self._check_failure_threshold(task_id):
                stop_reason = "high_failure_rate"
                for t in pending:
                    t.cancel()
                break

            done, pending = await asyncio.wait(
                pending, return_when=asyncio.FIRST_COMPLETED,
                timeout=progress_check_interval()
            )

            for completed in done:
                repo_name = scan_tasks[completed]
                try:
                    findings = completed.result()
                    all_findings.extend(findings)
                    scanned_count += 1
                except Exception as e:
                    logger.warning("task_error", repo=repo_name, error=str(e))

            # 更新进度
            await ScanTaskDAO.update_status(run_id, "running", scanned_count, len(all_findings))
            for dim in phase_progress:
                phase_progress[dim]["done"] = scanned_count
            await ScanTaskDAO.update_phase(run_id, "scanning", phase_progress)

        return all_findings, high_risk_repos, scanned_count, stop_reason

    async def _handle_stop_reason(self, run_id: str, task_id: int, stop_reason: str,
                                   scanned_count: int, findings: List) -> Dict:
        """处理扫描停止原因。"""
        if stop_reason == "paused":
            logger.info("scan_paused", run_id=run_id)
            return {"run_id": run_id, "status": "paused", "repos_scanned": scanned_count}

        if stop_reason == "high_failure_rate":
            await ScanTaskDAO.update_status(run_id, "failed", scanned_count, len(findings))
            task_obj = await ScanTaskDAO.get_by_run_id(run_id)
            await ScanHistoryDAO.archive_from_task(task_obj, dimensions=self.dimensions,
                                                    summary={"stop_reason": stop_reason})
            return {"run_id": run_id, "error": "失败率过高", "stop_reason": stop_reason}

        return {"run_id": run_id, "repos_scanned": scanned_count}

    async def _run_agent_analysis(self, org_name: str, high_risk_repos: Set[str],
                                   task_id: int, run_id: str) -> List[Finding]:
        """运行 Agent 深度分析。"""
        if self.scan_mode == "fast" or not high_risk_repos:
            return []

        repos_to_analyze = list(high_risk_repos) if self.scan_mode == "balanced" else []
        if not repos_to_analyze:
            return []

        logger.info("agent_analysis_start", repos=len(repos_to_analyze))
        await ScanTaskDAO.update_phase(run_id, "llm_analysis", {"repos_total": len(repos_to_analyze)})

        findings = await self._agent_deep_analysis(org_name, repos_to_analyze, task_id)
        for f in findings:
            f.scan_task_id = task_id
        await FindingDAO.batch_create(findings)

        return findings

    async def _generate_report(self, org_name: str, task_id: int, run_id: str):
        """生成分析报告。

        新架构说明：
        - 报告生成由 Agent 通过 tools 控制
        - 不再依赖 OrgConfigDAO
        - 默认生成报告
        """
        await ScanTaskDAO.update_phase(run_id, "generating_report", {})
        try:
            from app.scanner.report_generator import generate_scan_report
            report = await generate_scan_report(task_id)
            if report and report.id:
                logger.info("report_generated", task_id=task_id, report_id=report.id)
            else:
                logger.warning("report_generation_failed", task_id=task_id, reason="report_not_created")
        except Exception as e:
            import traceback
            logger.error("report_generation_error", task_id=task_id, error=str(e), traceback=traceback.format_exc())

    async def _archive_scan(self, run_id: str, task_id: int,
                            findings: List[Finding], high_risk_repos: Set[str]):
        """归档扫描结果。"""
        task_obj = await ScanTaskDAO.get_by_run_id(run_id)
        summary = self._build_summary(findings, high_risk_repos)
        await ScanHistoryDAO.archive_from_task(task_obj, dimensions=self.dimensions, summary=summary)
        logger.info("scan_archived", run_id=run_id)

    async def _agent_deep_analysis(self, org_name: str, repos: List[str],
                                    task_id: int) -> List[Finding]:
        """LLM深度分析高危仓库。"""
        try:
            existing = await FindingDAO.query(scan_task_id=task_id, page_size=1000)
            high_risk = [f for f in existing if f.severity in self.HIGH_RISK_SEVERITIES]

            if not high_risk:
                return []

            from app.llm_config import get_default_model
            from langchain_openai import ChatOpenAI

            model = get_default_model()
            llm = ChatOpenAI(model=model, temperature=0.1)

            prompt = self._build_analysis_prompt(org_name, high_risk)
            response = await asyncio.to_thread(llm.invoke, prompt)

            return [Finding(
                repo_full_name=f"{org_name}/_llm_analysis_",
                finding_type="AGENT_ANALYSIS",
                severity="INFO",
                title="LLM深度分析报告",
                description=response.content[:500],
                detail={"full_report": response.content, "high_risk_count": len(high_risk)}
            )]
        except Exception as e:
            logger.warning("llm_analysis_failed", error=str(e))
            return []

    def _build_analysis_prompt(self, org_name: str, findings: List[Finding]) -> str:
        """构建LLM分析提示。"""
        by_repo = {}
        for f in findings:
            by_repo.setdefault(f.repo_full_name, []).append(f)

        prompt = f"请对 {org_name} 组织的高危发现进行分析:\n\n"
        for repo, repo_findings in list(by_repo.items())[:10]:
            prompt += f"**{repo}** ({len(repo_findings)} 个高危):\n"
            for f in repo_findings[:5]:
                prompt += f"- [{f.severity}] {f.finding_type}: {f.title}\n"
            prompt += "\n"

        prompt += "\n请提供风险评估和修复建议。"
        return prompt

    @staticmethod
    def from_scan_mode(scan_mode: str, **kwargs) -> "HybridScanner":
        """根据扫描模式创建扫描器。"""
        return HybridScanner(scan_mode=scan_mode, **kwargs)