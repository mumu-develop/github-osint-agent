"""扫描协调器 - 统一扫描入口，协调批量工具和Agent分析。

提供三种扫描模式：
- fast: 仅批量工具层（快速扫描，无LLM）
- balanced: 批量工具 + 高危仓库Agent分析（推荐）
- deep: 批量工具 + 全量Agent分析（深度审计）
"""

import os
import asyncio
from datetime import datetime
from typing import Dict, List, Any, Optional
from github import Github, GithubException
from app.log_utils import get_logger
from app.models import Finding, ScanTask, SCAN_TEMPLATES
from app.database import FindingDAO, ScanTaskDAO, OrgConfigDAO, ScanSubTaskDAO, init_business_tables
from app.scanner.batch_tools import BatchScanTools
from app.scanner.hybrid_scanner import HybridScanner
from app.services.scan_lock import ScanLockService

logger = get_logger("scan_orchestrator")


class ScanOrchestrator:
    """扫描协调器 - 统一管理扫描任务。

    功能：
    1. 扫描模式选择（fast/balanced/deep）
    2. 高危仓库智能筛选
    3. 扫描任务状态管理
    4. 结果汇总和报告生成
    """

    # 扫描模式配置
    SCAN_MODES = {
        "fast": {
            "description": "快速扫描 - 仅批量工具，无LLM调用",
            "batch_layer": True,
            "agent_layer": False,
            "estimated_time_per_repo": 2,  # 秒
            "max_concurrency": 50
        },
        "balanced": {
            "description": "平衡扫描 - 批量工具 + 高危仓库Agent分析",
            "batch_layer": True,
            "agent_layer": True,
            "agent_scope": "high_risk_only",
            "estimated_time_per_repo": 5,
            "max_concurrency": 50
        },
        "deep": {
            "description": "深度扫描 - 批量工具 + 全量Agent分析",
            "batch_layer": True,
            "agent_layer": True,
            "agent_scope": "all",
            "estimated_time_per_repo": 15,
            "max_concurrency": 30
        }
    }

    def __init__(self, github_token: str = None):
        self.github_token = github_token or os.getenv("GITHUB_TOKEN")
        self.github = Github(self.github_token)

    async def scan_org(self, org_name: str, scan_mode: str = "balanced",
                       dimensions: Dict[str, bool] = None,
                       trigger_by: str = "manual") -> Dict[str, Any]:
        """扫描组织。

        Args:
            org_name: 组织名称
            scan_mode: 扫描模式 fast|balanced|deep
            dimensions: 扫描维度配置
            trigger_by: 触发方式

        Returns:
            扫描结果
        """
        if scan_mode not in self.SCAN_MODES:
            raise ValueError(f"未知扫描模式: {scan_mode}")

        mode_config = self.SCAN_MODES[scan_mode]
        logger.info("orchestrator_scan_start",
                    org=org_name,
                    mode=scan_mode,
                    description=mode_config["description"])

        await init_business_tables()

        # 生成 run_id 用于锁标识
        run_id = f"{scan_mode.upper()}_{org_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # 1. Redis 分布式锁（快速互斥层）
        lock_service = ScanLockService()
        acquired = await lock_service.acquire_lock(org_name, run_id, trigger_by)

        if not acquired:
            # 获取锁信息用于返回
            lock_info = await lock_service.get_lock_info(org_name)
            logger.warning("scan_locked_by_other", org=org_name, run_id=run_id, lock_info=lock_info)
            return {
                "code": 1,
                "message": f"组织 {org_name} 已有运行中的扫描任务（Redis 锁）",
                "lock_info": lock_info
            }

        try:
            # 2. 数据库幂等性检查（兜底层）
            running_task = await ScanTaskDAO.get_running_task_by_org(org_name)
            if running_task:
                logger.warning("scan_already_running", org=org_name, run_id=running_task.run_id)
                # 释放 Redis 锁（因为数据库检查发现已有任务）
                await lock_service.release_lock(org_name, run_id)
                return {
                    "code": 1,
                    "message": f"组织 {org_name} 已有运行中的扫描任务",
                    "existing_task": {
                        "run_id": running_task.run_id,
                        "status": running_task.status,
                        "progress": f"{running_task.scanned_repos}/{running_task.total_repos}"
                    }
                }

            # 3. 获取仓库数量（用于预估时间）
            try:
                org = await asyncio.to_thread(self.github.get_organization, org_name)
                repos = await asyncio.to_thread(lambda: list(org.get_repos()))
                total_repos = len(repos)
            except GithubException as e:
                logger.error("orchestrator_get_org_failed", org=org_name, error=str(e))
                return {"error": str(e)}

            # 4. 计算预估时间
            estimated_seconds = total_repos * mode_config["estimated_time_per_repo"]
            estimated_minutes = max(1, int(estimated_seconds / 60))

            logger.info("orchestrator_scan_estimated",
                        org=org_name,
                        repos=total_repos,
                        estimated_minutes=estimated_minutes)

            # 5. 执行扫描
            if scan_mode == "fast":
                # 快速模式：仅批量工具
                scanner = BatchScanTools(self.github_token, concurrency=50)
                result = await self._run_fast_scan(org_name, repos, scanner, dimensions, trigger_by)
                await scanner.close()
            else:
                # balanced/deep模式：混合扫描
                scanner = HybridScanner(
                    dimensions=dimensions,
                    scan_mode=scan_mode,
                    github_token=self.github_token
                )
                result = await scanner.scan_org(org_name, trigger_by)
                await scanner.close()

            # 6. 添加预估信息到结果
            result["scan_mode"] = scan_mode
            result["estimated_time_minutes"] = estimated_minutes
            result["mode_description"] = mode_config["description"]

            return result

        finally:
            # 7. 释放 Redis 锁
            await lock_service.release_lock(org_name, run_id)
            logger.info("scan_lock_released", org=org_name, run_id=run_id)

    async def _run_fast_scan(self, org_name: str, repos: List,
                              batch_tools: BatchScanTools,
                              dimensions: Dict[str, bool],
                              trigger_by: str) -> Dict[str, Any]:
        """执行快速扫描（仅批量工具层）。"""
        logger.info("fast_scan_start", org=org_name, repos=len(repos))

        # 创建任务
        run_id = f"FAST_{org_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        task = ScanTask(
            run_id=run_id,
            scan_type="FAST",
            org_name=org_name,
            trigger_by=trigger_by,
            status="running",
            total_repos=len(repos)
        )
        task_id = await ScanTaskDAO.create(task)

        repo_list = [{"owner": org_name, "repo": r.name} for r in repos]

        # 并发执行批量扫描
        all_findings = []

        if dimensions.get("cve"):
            cve_results = await batch_tools.batch_cve_check(repo_list)
            for repo, findings in cve_results.items():
                all_findings.extend(findings)

        if dimensions.get("secret"):
            secret_results = await batch_tools.batch_secret_scan(repo_list)
            for repo, findings in secret_results.items():
                all_findings.extend(findings)

        if dimensions.get("license"):
            license_results = await batch_tools.batch_license_check(repo_list)
            for repo, findings in license_results.items():
                all_findings.extend(findings)

        if dimensions.get("community"):
            community_results = await batch_tools.batch_community_check(repo_list)
            for repo, findings in community_results.items():
                all_findings.extend(findings)

        # 保存结果
        for f in all_findings:
            f.scan_task_id = task_id
        saved_count = await FindingDAO.batch_create(all_findings)
        logger.info("findings_saved_to_db", task_id=task_id, total=len(all_findings), saved=saved_count)

        # 完成任务
        high_severity = len([f for f in all_findings if f.severity in ["CRITICAL", "HIGH"]])
        await ScanTaskDAO.update_status(run_id, "completed", len(repos), len(all_findings))

        # 生成报告（根据组织配置决定）
        task_obj = await ScanTaskDAO.get_by_run_id(run_id)
        if task_obj and task_obj.org_name:
            org_config = await OrgConfigDAO.get_by_name(task_obj.org_name)
            if org_config and org_config.generate_report:
                try:
                    from app.scanner.report_generator import generate_scan_report
                    report = await generate_scan_report(task_id, report_type="summary")
                    logger.info("fast_report_generated", task_id=task_id, report_id=report.id)
                except Exception as e:
                    logger.warning("fast_report_generation_failed", task_id=task_id, error=str(e))
            else:
                logger.info("report_generation_skipped", task_id=task_id, reason="org_config disabled")

        logger.info("fast_scan_done", org=org_name, findings=len(all_findings))

        return {
            "run_id": run_id,
            "org_name": org_name,
            "repos_scanned": len(repos),
            "total_findings": len(all_findings),
            "high_severity_count": high_severity,
            "task_id": task_id
        }

    async def _run_fast_scan_with_task(self, org_name: str, repos: List,
                                        batch_tools: BatchScanTools,
                                        dimensions: Dict[str, bool],
                                        task_id: int, run_id: str) -> Dict[str, Any]:
        """执行快速扫描（任务和子任务已由外部创建）。

        用于从 routes/orgs.py 调用，任务和子任务已预先创建。

        Args:
            org_name: 组织名称
            repos: 仓库列表
            batch_tools: 批量扫描工具
            dimensions: 扫描维度
            task_id: 已创建的任务ID
            run_id: 任务运行ID

        Returns:
            扫描结果
        """
        from app.database import ScanSubTaskDAO
        from app.log_utils import get_logger

        logger = get_logger("scan_orchestrator")
        logger.info("fast_scan_with_task_start", org=org_name, repos=len(repos),
                    task_id=task_id, run_id=run_id)

        # 初始化阶段进度
        phase_progress = {}
        for dim in ["cve", "secret", "license", "community"]:
            if dimensions.get(dim):
                phase_progress[dim] = {"done": 0, "total": len(repos)}
        await ScanTaskDAO.update_phase(run_id, "scanning", phase_progress)

        repo_list = [{"owner": org_name, "repo": r.name} for r in repos]
        repo_full_names = [f"{org_name}/{r.name}" for r in repos]

        # 并发执行批量扫描，汇总每个仓库的发现
        all_findings = []
        repo_findings_map: Dict[str, List[Finding]] = {name: [] for name in repo_full_names}

        try:
            if dimensions.get("cve"):
                logger.info("fast_scan_cve_start", org=org_name)
                cve_results = await batch_tools.batch_cve_check(repo_list)
                for repo_full_name, findings in cve_results.items():
                    if repo_full_name in repo_findings_map:
                        repo_findings_map[repo_full_name].extend(findings)
                        all_findings.extend(findings)
                # 更新 CVE 维度进度
                if "cve" in phase_progress:
                    phase_progress["cve"]["done"] = len(cve_results)
                    await ScanTaskDAO.update_phase(run_id, "scanning", phase_progress)

            if dimensions.get("secret"):
                logger.info("fast_scan_secret_start", org=org_name)
                secret_results = await batch_tools.batch_secret_scan(repo_list)
                for repo_full_name, findings in secret_results.items():
                    if repo_full_name in repo_findings_map:
                        repo_findings_map[repo_full_name].extend(findings)
                        all_findings.extend(findings)
                # 更新 SECRET 维度进度
                if "secret" in phase_progress:
                    phase_progress["secret"]["done"] = len(secret_results)
                    await ScanTaskDAO.update_phase(run_id, "scanning", phase_progress)

            if dimensions.get("license"):
                logger.info("fast_scan_license_start", org=org_name)
                license_results = await batch_tools.batch_license_check(repo_list)
                for repo_full_name, findings in license_results.items():
                    if repo_full_name in repo_findings_map:
                        repo_findings_map[repo_full_name].extend(findings)
                        all_findings.extend(findings)
                # 更新 LICENSE 维度进度
                if "license" in phase_progress:
                    phase_progress["license"]["done"] = len(license_results)
                    await ScanTaskDAO.update_phase(run_id, "scanning", phase_progress)

            if dimensions.get("community"):
                logger.info("fast_scan_community_start", org=org_name)
                community_results = await batch_tools.batch_community_check(repo_list)
                for repo_full_name, findings in community_results.items():
                    if repo_full_name in repo_findings_map:
                        repo_findings_map[repo_full_name].extend(findings)
                        all_findings.extend(findings)
                # 更新 COMMUNITY 维度进度
                if "community" in phase_progress:
                    phase_progress["community"]["done"] = len(community_results)
                    await ScanTaskDAO.update_phase(run_id, "scanning", phase_progress)

        except Exception as e:
            logger.error("fast_scan_batch_error", org=org_name, error=str(e))
            # 标记所有子任务为失败
            await ScanSubTaskDAO.finalize_remaining_subtasks(task_id, "failed", error_message=str(e))
            raise

        # 统一更新每个仓库的子任务状态
        for repo_full_name, findings in repo_findings_map.items():
            high_count = len([f for f in findings if f.severity in ["CRITICAL", "HIGH"]])
            await ScanSubTaskDAO.update_status_by_repo(
                repo_full_name, task_id, "completed",
                findings_count=len(findings),
                high_severity_count=high_count
            )

        # 对于没有返回结果的仓库（可能在批量扫描中被跳过），标记为完成但0发现
        for repo_full_name in repo_full_names:
            if repo_full_name not in repo_findings_map or not repo_findings_map[repo_full_name]:
                await ScanSubTaskDAO.update_status_by_repo(
                    repo_full_name, task_id, "completed",
                    findings_count=0,
                    high_severity_count=0
                )

        # 保存结果
        for f in all_findings:
            f.scan_task_id = task_id
        saved_count = await FindingDAO.batch_create(all_findings)
        logger.info("findings_saved_to_db", task_id=task_id, total=len(all_findings), saved=saved_count)

        # 完成任务
        high_severity = len([f for f in all_findings if f.severity in ["CRITICAL", "HIGH"]])
        await ScanTaskDAO.update_status(run_id, "completed", len(repos), len(all_findings))

        # 生成报告（根据组织配置决定）
        task_obj = await ScanTaskDAO.get_by_run_id(run_id)
        if task_obj and task_obj.org_name:
            org_config = await OrgConfigDAO.get_by_name(task_obj.org_name)
            if org_config and org_config.generate_report:
                # 更新阶段为 "generating_report"
                await ScanTaskDAO.update_phase(run_id, "generating_report", {"report_type": "summary"})
                try:
                    from app.scanner.report_generator import generate_scan_report
                    report = await generate_scan_report(task_id, report_type="summary")
                    logger.info("fast_report_generated", task_id=task_id, report_id=report.id)
                except Exception as e:
                    logger.warning("fast_report_generation_failed", task_id=task_id, error=str(e))
            else:
                logger.info("report_generation_skipped", task_id=task_id, reason="org_config disabled")

        # 归档到历史记录
        from app.database import ScanHistoryDAO
        task_obj = await ScanTaskDAO.get_by_run_id(run_id)
        if task_obj:
            summary = {
                "by_severity": {
                    "critical": len([f for f in all_findings if f.severity == "CRITICAL"]),
                    "high": len([f for f in all_findings if f.severity == "HIGH"]),
                    "medium": len([f for f in all_findings if f.severity == "MEDIUM"]),
                    "low": len([f for f in all_findings if f.severity == "LOW"])
                },
                "by_type": {}
            }
            for f in all_findings:
                summary["by_type"][f.finding_type] = summary["by_type"].get(f.finding_type, 0) + 1
            await ScanHistoryDAO.archive_from_task(task_obj, dimensions=dimensions, summary=summary)
            logger.info("fast_scan_archived_to_history", run_id=run_id, org=org_name)

        # 更新阶段为 "done"
        await ScanTaskDAO.update_phase(run_id, "done")

        logger.info("fast_scan_with_task_done", org=org_name, findings=len(all_findings))

        return {
            "run_id": run_id,
            "org_name": org_name,
            "repos_scanned": len(repos),
            "total_findings": len(all_findings),
            "high_severity_count": high_severity,
            "task_id": task_id
        }

    async def resume_fast_scan(self, run_id: str, org_name: str = None) -> Dict[str, Any]:
        """恢复暂停的 fast 模式扫描。

        Args:
            run_id: 任务运行ID
            org_name: 组织名称（可选，会从任务中获取）

        Returns:
            扫描结果
        """
        await init_business_tables()

        # 1. 获取主任务
        task = await ScanTaskDAO.get_by_run_id(run_id)
        if not task:
            return {"error": f"任务 {run_id} 不存在"}

        if task.status != "paused":
            return {"error": f"任务状态为 {task.status}，无法恢复"}

        task_id = task.id
        org_name = org_name or task.org_name

        # 2. 恢复主任务状态
        await ScanTaskDAO.resume(run_id)

        # 3. 获取待执行的子任务
        pending_subtasks = await ScanSubTaskDAO.get_pending_subtasks(task_id, limit=100)

        if not pending_subtasks:
            # 所有子任务已完成
            logger.info("fast_resume_all_done", run_id=run_id)
            await ScanTaskDAO.update_status(run_id, "completed", task.scanned_repos, task.findings_count)
            return {"run_id": run_id, "message": "任务已完成"}

        # 4. 将 paused 状态的子任务恢复为 pending
        await ScanSubTaskDAO.resume_all_by_task(task_id)

        # 5. 重新获取待执行的子任务
        pending_subtasks = await ScanSubTaskDAO.get_pending_subtasks(task_id, limit=100)
        repo_names = [st.repo_full_name.split("/")[-1] for st in pending_subtasks]
        repo_full_names = [st.repo_full_name for st in pending_subtasks]

        logger.info("fast_resume_start", run_id=run_id, pending_count=len(pending_subtasks))

        # 6. 获取组织配置的扫描维度
        org_config = await OrgConfigDAO.get_by_name(org_name)
        dimensions = org_config.scan_dimensions if org_config else {
            "cve": True, "secret": True, "license": True, "community": False
        }

        # 7. 执行剩余仓库的扫描
        repo_list = [{"owner": org_name, "repo": name} for name in repo_names]
        batch_tools = BatchScanTools(os.getenv("GITHUB_TOKEN"), concurrency=50)

        all_findings = []
        repo_findings_map: Dict[str, List[Finding]] = {name: [] for name in repo_full_names}

        try:
            if dimensions.get("cve"):
                cve_results = await batch_tools.batch_cve_check(repo_list)
                for repo_full_name, findings in cve_results.items():
                    if repo_full_name in repo_findings_map:
                        repo_findings_map[repo_full_name].extend(findings)
                        all_findings.extend(findings)

            if dimensions.get("secret"):
                secret_results = await batch_tools.batch_secret_scan(repo_list)
                for repo_full_name, findings in secret_results.items():
                    if repo_full_name in repo_findings_map:
                        repo_findings_map[repo_full_name].extend(findings)
                        all_findings.extend(findings)

            if dimensions.get("license"):
                license_results = await batch_tools.batch_license_check(repo_list)
                for repo_full_name, findings in license_results.items():
                    if repo_full_name in repo_findings_map:
                        repo_findings_map[repo_full_name].extend(findings)
                        all_findings.extend(findings)

            if dimensions.get("community"):
                community_results = await batch_tools.batch_community_check(repo_list)
                for repo_full_name, findings in community_results.items():
                    if repo_full_name in repo_findings_map:
                        repo_findings_map[repo_full_name].extend(findings)
                        all_findings.extend(findings)

        except Exception as e:
            logger.error("fast_resume_batch_error", run_id=run_id, error=str(e))
            await ScanSubTaskDAO.finalize_remaining_subtasks(task_id, "failed", error_message=str(e))
            await batch_tools.close()
            raise

        # 8. 更新子任务状态
        for repo_full_name, findings in repo_findings_map.items():
            high_count = len([f for f in findings if f.severity in ["CRITICAL", "HIGH"]])
            await ScanSubTaskDAO.update_status_by_repo(
                repo_full_name, task_id, "completed",
                findings_count=len(findings),
                high_severity_count=high_count
            )

        # 9. 保存 findings
        for f in all_findings:
            f.scan_task_id = task_id
        await FindingDAO.batch_create(all_findings)

        await batch_tools.close()

        # 10. 更新主任务状态
        total_findings = task.findings_count + len(all_findings)
        total_scanned = task.scanned_repos + len(repo_names)
        high_severity = len([f for f in all_findings if f.severity in ["CRITICAL", "HIGH"]])
        await ScanTaskDAO.update_status(run_id, "completed", total_scanned, total_findings)

        logger.info("fast_resume_done", run_id=run_id, repos_scanned=len(repo_names), findings=len(all_findings))

        return {
            "run_id": run_id,
            "org_name": org_name,
            "repos_scanned": len(repo_names),
            "total_findings": len(all_findings),
            "high_severity_count": high_severity
        }

    async def get_scan_estimate(self, org_name: str, scan_mode: str,
                                 dimensions: Dict[str, bool] = None) -> Dict[str, Any]:
        """获取扫描预估信息（不执行扫描）。

        Args:
            org_name: 组织名称
            scan_mode: 扫描模式
            dimensions: 扫描维度

        Returns:
            预估信息
        """
        try:
            org = await asyncio.to_thread(self.github.get_organization, org_name)
            repos = await asyncio.to_thread(lambda: list(org.get_repos()))
            total_repos = len(repos)
        except GithubException as e:
            return {"error": str(e)}

        mode_config = self.SCAN_MODES.get(scan_mode, self.SCAN_MODES["balanced"])
        estimated_seconds = total_repos * mode_config["estimated_time_per_repo"]

        active_dims = sum(1 for d in ["cve", "secret", "license", "community"]
                          if dimensions and dimensions.get(d))

        return {
            "org_name": org_name,
            "total_repos": total_repos,
            "scan_mode": scan_mode,
            "mode_description": mode_config["description"],
            "estimated_time_minutes": max(1, int(estimated_seconds / 60)),
            "active_dimensions": active_dims,
            "agent_layer": mode_config["agent_layer"]
        }

    @staticmethod
    async def from_org_config(org_config, scan_mode: str = None) -> "ScanOrchestrator":
        """从组织配置创建扫描协调器。

        Args:
            org_config: OrgConfig对象
            scan_mode: 可选覆盖扫描模式
        """
        orchestrator = ScanOrchestrator()
        # scan_mode 由调用方传入或使用默认 balanced
        return orchestrator


# ==================== 快捷函数 ====================

async def quick_scan(org_name: str, dimensions: Dict[str, bool] = None) -> Dict[str, Any]:
    """快速扫描 - 仅批量工具层，极速。

    适合大规模扫描场景，无LLM调用。
    """
    orchestrator = ScanOrchestrator()
    return await orchestrator.scan_org(org_name, "fast", dimensions)


async def balanced_scan(org_name: str, dimensions: Dict[str, bool] = None) -> Dict[str, Any]:
    """平衡扫描 - 批量工具 + 高危仓库Agent分析。

    推荐：速度和深度兼顾。
    """
    orchestrator = ScanOrchestrator()
    return await orchestrator.scan_org(org_name, "balanced", dimensions)


async def deep_scan(org_name: str, dimensions: Dict[str, bool] = None) -> Dict[str, Any]:
    """深度扫描 - 批量工具 + 全量Agent分析。

    适合审计场景，全面深度分析。
    """
    orchestrator = ScanOrchestrator()
    return await orchestrator.scan_org(org_name, "deep", dimensions)