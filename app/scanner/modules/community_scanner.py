"""社区健康度检查模块 - 检查仓库社区活跃度、PR/Issue 响应速度。"""

import os
import asyncio
import requests
from datetime import datetime
from typing import Dict, List, Optional
from github import Github, GithubException
from app.log_utils import get_logger
from app.models import Finding

logger = get_logger("community_scanner")


class CommunityScanner:
    """社区健康度检查器 - 检查仓库社区活跃度和响应速度。

    检查指标：
    1. 仓库活跃度：最后推送时间、Star 数
    2. PR 响应速度：平均合并时间
    3. Issue 响应速度：平均关闭时间
    """

    # 响应速度阈值（小时）
    PR_MERGE_THRESHOLD = {
        "healthy": 48,      # < 48 小时 = 健康
        "warning": 168,     # 48-168 小时 = 警告（一周）
        "critical": 720     # > 720 小时 = 严重（一个月）
    }

    ISSUE_CLOSE_THRESHOLD = {
        "healthy": 24,      # < 24 小时 = 健康
        "warning": 168,     # 24-168 小时 = 警告
        "critical": 720     # > 720 小时 = 严重
    }

    def __init__(self, github_token: str = None):
        self.github_token = github_token or os.getenv("GITHUB_TOKEN")
        self.github = Github(self.github_token)

    async def close(self):
        """关闭资源。"""
        pass

    async def scan(self, repo_obj) -> List[Finding]:
        """检查社区健康度。"""
        findings = []

        try:
            # 1. 基础信息检查（活跃度）
            basic_findings = await self._check_basic_activity(repo_obj)
            findings.extend(basic_findings)

            # 2. PR 响应速度检查
            pr_findings = await self._check_pr_response(repo_obj)
            findings.extend(pr_findings)

            # 3. Issue 响应速度检查
            issue_findings = await self._check_issue_response(repo_obj)
            findings.extend(issue_findings)

        except Exception as e:
            logger.warning("community_check_error", repo=repo_obj.full_name, error=str(e))

        return findings

    async def _check_basic_activity(self, repo_obj) -> List[Finding]:
        """检查仓库基础活跃度。"""
        findings = []

        stats = await asyncio.to_thread(lambda: {
            "stars": repo_obj.stargazers_count,
            "forks": repo_obj.forks_count,
            "open_issues": repo_obj.open_issues_count,
            "updated_at": repo_obj.updated_at.isoformat() if repo_obj.updated_at else None,
            "pushed_at": repo_obj.pushed_at.isoformat() if repo_obj.pushed_at else None
        })

        if stats["pushed_at"]:
            last_push = datetime.fromisoformat(stats["pushed_at"].replace("Z", "+00:00"))
            days_inactive = (datetime.now(last_push.tzinfo) - last_push).days

            if days_inactive > 365:
                findings.append(Finding(
                    repo_full_name=repo_obj.full_name,
                    finding_type="COMMUNITY",
                    severity="MEDIUM",
                    title=f"仓库不活跃: {days_inactive}天无更新",
                    description="仓库超过一年未更新，可能已停止维护",
                    detail={"days_inactive": days_inactive, **stats}
                ))
            elif days_inactive > 180 and stats["stars"] > 1000:
                findings.append(Finding(
                    repo_full_name=repo_obj.full_name,
                    finding_type="COMMUNITY",
                    severity="LOW",
                    title=f"仓库活跃度降低: {days_inactive}天无更新",
                    description=f"高Star仓库({stats['stars']} stars)超过半年未更新",
                    detail={"days_inactive": days_inactive, **stats}
                ))

        return findings

    async def _check_pr_response(self, repo_obj) -> List[Finding]:
        """检查 PR 响应速度。"""
        findings = []

        try:
            # 使用 REST API 获取 PR 数据（比 PyGithub 更高效）
            owner, repo = repo_obj.full_name.split("/")
            headers = {
                "Authorization": f"Bearer {self.github_token}",
                "Accept": "application/vnd.github.v3+json"
            }

            url = f"https://api.github.com/repos/{owner}/{repo}/pulls?state=all&per_page=100"
            resp = await asyncio.to_thread(
                lambda: requests.get(url, headers=headers, timeout=30)
            )

            if resp.status_code != 200:
                return findings

            prs = resp.json()
            merged_prs = [p for p in prs if p.get("merged_at")]
            open_prs = [p for p in prs if p.get("state") == "open"]

            # 1. 检查长时间未合并的 PR
            stale_open_prs = []
            for p in open_prs:
                created = p.get("created_at")
                if created:
                    created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    waiting_hours = (datetime.now(created_dt.tzinfo) - created_dt).total_seconds() / 3600
                    waiting_days = waiting_hours / 24

                    # 超过 7 天未合并
                    if waiting_days > 7:
                        stale_open_prs.append({
                            "number": p.get("number"),
                            "title": p.get("title", "")[:60],
                            "author": p.get("user", {}).get("login", "未知"),
                            "created_at": created,
                            "waiting_days": round(waiting_days, 1),
                            "waiting_hours": round(waiting_hours, 1),
                            "url": p.get("html_url")
                        })

            # 报告长时间未合并的 PR
            if stale_open_prs:
                # 按等待时间排序，取最长的几个
                stale_open_prs.sort(key=lambda x: x["waiting_days"], reverse=True)

                severity = "HIGH" if any(p["waiting_days"] > 30 for p in stale_open_prs) else "MEDIUM"

                findings.append(Finding(
                    repo_full_name=repo_obj.full_name,
                    finding_type="COMMUNITY",
                    severity=severity,
                    title=f"存在 {len(stale_open_prs)} 个 PR 长时间未合并",
                    description=f"最长等待 {stale_open_prs[0]['waiting_days']} 天的 PR 未被处理",
                    detail={
                        "stale_prs_count": len(stale_open_prs),
                        "stale_prs": stale_open_prs[:10],  # 只列出前 10 个
                        "max_waiting_days": stale_open_prs[0]["waiting_days"] if stale_open_prs else 0,
                        "total_open_prs": len(open_prs)
                    }
                ))

            # 2. 计算已合并 PR 的平均合并时间
            if merged_prs and len(merged_prs) >= 5:
                total_hours = 0
                for p in merged_prs:
                    created = p.get("created_at")
                    merged = p.get("merged_at")
                    if created and merged:
                        created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                        merged_dt = datetime.fromisoformat(merged.replace("Z", "+00:00"))
                        total_hours += (merged_dt - created_dt).total_seconds() / 3600

                avg_merge_hours = total_hours / len(merged_prs)

                # 根据阈值判断（只在没有 stale PR 问题时报告）
                if avg_merge_hours > self.PR_MERGE_THRESHOLD["critical"] and not stale_open_prs:
                    findings.append(Finding(
                        repo_full_name=repo_obj.full_name,
                        finding_type="COMMUNITY",
                        severity="HIGH",
                        title=f"PR 响应缓慢: 平均 {round(avg_merge_hours/24, 1)} 天才合并",
                        description="PR 合并时间过长，社区响应速度严重不足",
                        detail={
                            "avg_merge_hours": round(avg_merge_hours, 1),
                            "avg_merge_days": round(avg_merge_hours / 24, 1),
                            "total_prs": len(prs),
                            "merged_prs": len(merged_prs),
                            "threshold": "30天"
                        }
                    ))
                elif avg_merge_hours > self.PR_MERGE_THRESHOLD["warning"] and not stale_open_prs:
                    findings.append(Finding(
                        repo_full_name=repo_obj.full_name,
                        finding_type="COMMUNITY",
                        severity="MEDIUM",
                        title=f"PR 响应较慢: 平均 {round(avg_merge_hours/24, 1)} 天合并",
                        description="PR 合并时间较长，建议关注社区活跃度",
                        detail={
                            "avg_merge_hours": round(avg_merge_hours, 1),
                            "avg_merge_days": round(avg_merge_hours / 24, 1),
                            "threshold": "7天"
                        }
                    ))

        except Exception as e:
            logger.warning("pr_check_error", repo=repo_obj.full_name, error=str(e))

        return findings

    async def _check_issue_response(self, repo_obj) -> List[Finding]:
        """检查 Issue 响应速度。"""
        findings = []

        try:
            owner, repo = repo_obj.full_name.split("/")
            headers = {
                "Authorization": f"Bearer {self.github_token}",
                "Accept": "application/vnd.github.v3+json"
            }

            # 1. 获取开放的 Issue（排除 PR）
            open_url = f"https://api.github.com/repos/{owner}/{repo}/issues?state=open&per_page=100"
            open_resp = await asyncio.to_thread(
                lambda: requests.get(open_url, headers=headers, timeout=30)
            )

            open_issues = []
            if open_resp.status_code == 200:
                open_data = open_resp.json()
                # 过滤掉 PR
                open_issues = [i for i in open_data if "pull_request" not in i]

            # 检查长时间未关闭的 Issue
            stale_open_issues = []
            for i in open_issues:
                created = i.get("created_at")
                if created:
                    created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    waiting_hours = (datetime.now(created_dt.tzinfo) - created_dt).total_seconds() / 3600
                    waiting_days = waiting_hours / 24

                    # 超过 14 天未处理
                    if waiting_days > 14:
                        stale_open_issues.append({
                            "number": i.get("number"),
                            "title": i.get("title", "")[:60],
                            "author": i.get("user", {}).get("login", "未知"),
                            "created_at": created,
                            "waiting_days": round(waiting_days, 1),
                            "labels": [l.get("name") for l in i.get("labels", [])],
                            "url": i.get("html_url")
                        })

            # 报告长时间未处理的 Issue
            if stale_open_issues:
                stale_open_issues.sort(key=lambda x: x["waiting_days"], reverse=True)

                severity = "HIGH" if any(i["waiting_days"] > 60 for i in stale_open_issues) else "MEDIUM"

                findings.append(Finding(
                    repo_full_name=repo_obj.full_name,
                    finding_type="COMMUNITY",
                    severity=severity,
                    title=f"存在 {len(stale_open_issues)} 个 Issue 长时间未处理",
                    description=f"最长等待 {stale_open_issues[0]['waiting_days']} 天的 Issue 未被响应",
                    detail={
                        "stale_issues_count": len(stale_open_issues),
                        "stale_issues": stale_open_issues[:10],  # 只列出前 10 个
                        "max_waiting_days": stale_open_issues[0]["waiting_days"] if stale_open_issues else 0,
                        "total_open_issues": len(open_issues)
                    }
                ))

            # 2. 获取已关闭的 Issue，计算平均关闭时间
            closed_url = f"https://api.github.com/repos/{owner}/{repo}/issues?state=closed&per_page=100"
            closed_resp = await asyncio.to_thread(
                lambda: requests.get(closed_url, headers=headers, timeout=30)
            )

            if closed_resp.status_code != 200:
                return findings

            closed_issues = closed_resp.json()
            # 过滤掉 PR
            real_closed_issues = [i for i in closed_issues if "pull_request" not in i]

            if real_closed_issues and len(real_closed_issues) >= 5:
                # 计算平均关闭时间
                total_hours = 0
                for i in real_closed_issues:
                    created = i.get("created_at")
                    closed = i.get("closed_at")
                    if created and closed:
                        created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                        closed_dt = datetime.fromisoformat(closed.replace("Z", "+00:00"))
                        total_hours += (closed_dt - created_dt).total_seconds() / 3600

                avg_close_hours = total_hours / len(real_closed_issues)

                # 根据阈值判断（只在没有 stale Issue 问题时报告）
                if avg_close_hours > self.ISSUE_CLOSE_THRESHOLD["critical"] and not stale_open_issues:
                    findings.append(Finding(
                        repo_full_name=repo_obj.full_name,
                        finding_type="COMMUNITY",
                        severity="HIGH",
                        title=f"Issue 响应缓慢: 平均 {round(avg_close_hours/24, 1)} 天才关闭",
                        description="Issue 处理时间过长，社区支持严重不足",
                        detail={
                            "avg_close_hours": round(avg_close_hours, 1),
                            "avg_close_days": round(avg_close_hours / 24, 1),
                            "closed_issues": len(real_closed_issues),
                            "threshold": "30天"
                        }
                    ))
                elif avg_close_hours > self.ISSUE_CLOSE_THRESHOLD["warning"] and not stale_open_issues:
                    findings.append(Finding(
                        repo_full_name=repo_obj.full_name,
                        finding_type="COMMUNITY",
                        severity="MEDIUM",
                        title=f"Issue 响应较慢: 平均 {round(avg_close_hours/24, 1)} 天关闭",
                        description="Issue 处理时间较长，建议关注社区响应",
                        detail={
                            "avg_close_hours": round(avg_close_hours, 1),
                            "avg_close_days": round(avg_close_hours / 24, 1),
                            "threshold": "7天"
                        }
                    ))

        except Exception as e:
            logger.warning("issue_check_error", repo=repo_obj.full_name, error=str(e))

        return findings