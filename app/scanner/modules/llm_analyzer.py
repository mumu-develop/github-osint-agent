"""LLM深度分析模块 - 趋势分析、供应链风险。

优化：
1. 减少 GitHub API 调用，使用仓库基础信息替代详细 commit 查询
2. 添加速率限制错误处理
3. 使用项目统一的 LLM 配置
"""

import os
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from github import Github, GithubException, RateLimitExceededException
from app.log_utils import get_logger
from app.models import Finding
from app.llm_config import create_chat_model, get_api_config

logger = get_logger("llm_analyzer")


class LLMAnalyzer:
    """LLM深度分析器 - 趋势分析、供应链风险。

    不包含代码质量分析（code_quality），因为已合并的代码已经过审核，
    代码质量检查应该在 PR 阶段进行。
    """

    # 速率限制标记（全局，避免重复触发）
    _rate_limit_hit = False
    _rate_limit_reset_time = None

    def __init__(self, github_token: str = None, dimensions: List[str] = None):
        """
        Args:
            github_token: GitHub API token
            dimensions: LLM分析维度列表 ["trend", "supply_chain"]
        """
        self.github_token = github_token or os.getenv("GITHUB_TOKEN")
        self.github = Github(self.github_token)
        self.dimensions = dimensions or ["trend", "supply_chain"]

        # 使用项目统一的 LLM 配置
        self.llm_enabled = self._check_llm_available()
        if self.llm_enabled:
            try:
                model_name = os.getenv("AGENT_MODEL", "openai:qwen3.6-plus")
                self.model = create_chat_model(model_name, temperature=0.3, max_tokens=1024)
                logger.info("llm_analyzer_model_created", model=model_name)
            except Exception as e:
                logger.warning("llm_analyzer_model_failed", error=str(e))
                self.llm_enabled = False

    def _check_llm_available(self) -> bool:
        """检查 LLM 是否可用。"""
        api_base, api_key = get_api_config()
        return bool(api_key)

    async def close(self):
        """关闭资源。"""
        pass

    def _check_rate_limit(self) -> bool:
        """检查是否处于速率限制状态。

        Returns:
            True 如果应该跳过请求，False 如果可以继续
        """
        if LLMAnalyzer._rate_limit_hit:
            if LLMAnalyzer._rate_limit_reset_time:
                if datetime.now() < LLMAnalyzer._rate_limit_reset_time:
                    wait_seconds = (LLMAnalyzer._rate_limit_reset_time - datetime.now()).total_seconds()
                    logger.warning("rate_limit_waiting",
                                   remaining_seconds=int(wait_seconds))
                    return True
                else:
                    # 重置时间已过，清除标记
                    LLMAnalyzer._rate_limit_hit = False
                    LLMAnalyzer._rate_limit_reset_time = None
                    logger.info("rate_limit_reset_cleared")
            return True
        return False

    def _mark_rate_limit(self, reset_time: datetime):
        """标记速率限制状态。"""
        LLMAnalyzer._rate_limit_hit = True
        LLMAnalyzer._rate_limit_reset_time = reset_time
        logger.warning("rate_limit_marked",
                       reset_time=reset_time.isoformat())

    async def scan(self, repo_obj) -> List[Finding]:
        """执行LLM深度分析。"""
        findings = []

        if not self.llm_enabled:
            logger.debug("llm_not_enabled", repo=repo_obj.full_name)
            return findings

        # 检查速率限制
        if self._check_rate_limit():
            logger.warning("scan_skipped_rate_limit", repo=repo_obj.full_name)
            return findings

        for dimension in self.dimensions:
            try:
                if dimension == "trend":
                    trend_findings = await self._analyze_trend(repo_obj)
                    findings.extend(trend_findings)
                elif dimension == "supply_chain":
                    supply_findings = await self._analyze_supply_chain(repo_obj)
                    findings.extend(supply_findings)
            except RateLimitExceededException as e:
                logger.warning("rate_limit_exceeded", repo=repo_obj.full_name)
                self._mark_rate_limit(e.reset_time if hasattr(e, 'reset_time') else datetime.now() + timedelta(minutes=15))
                break  # 停止后续分析
            except Exception as e:
                logger.warning("llm_analysis_error", dimension=dimension, repo=repo_obj.full_name, error=str(e))

        return findings

    async def _analyze_trend(self, repo_obj) -> List[Finding]:
        """分析仓库趋势和热度变化 - 使用仓库基础信息，避免详细 commit 查询。"""
        findings = []

        try:
            # 使用仓库基础信息而非详细 commit 查询（大幅减少 API 调用）
            stats = await asyncio.to_thread(lambda: {
                "stars": repo_obj.stargazers_count,
                "forks": repo_obj.forks_count,
                "watchers": repo_obj.watchers_count,
                "open_issues": repo_obj.open_issues_count,
                "created_at": repo_obj.created_at.isoformat() if repo_obj.created_at else None,
                "pushed_at": repo_obj.pushed_at.isoformat() if repo_obj.pushed_at else None,
                "updated_at": repo_obj.updated_at.isoformat() if repo_obj.updated_at else None,
            })

            # 计算热度趋势（基于 Star 增长速度，而非 commit）
            if stats["pushed_at"]:
                last_push = datetime.fromisoformat(stats["pushed_at"].replace("Z", "+00:00"))
                days_inactive = (datetime.now(last_push.tzinfo) - last_push).days

                # 长时间不活跃
                if days_inactive > 90 and stats["stars"] > 100:
                    severity = "MEDIUM" if days_inactive > 180 else "LOW"
                    findings.append(Finding(
                        repo_full_name=repo_obj.full_name,
                        finding_type="TREND",
                        severity=severity,
                        title=f"仓库活跃度下降: {days_inactive}天无更新",
                        description=f"该仓库已有 {days_inactive} 天无代码更新，Stars={stats['stars']}",
                        detail={
                            "days_inactive": days_inactive,
                            "stars": stats["stars"],
                            "last_push": stats["pushed_at"]
                        }
                    ))

            # Star 数快速增长检测（正向发现）
            if stats["stars"] > 1000 and stats["created_at"]:
                created = datetime.fromisoformat(stats["created_at"].replace("Z", "+00:00"))
                months_old = (datetime.now(created.tzinfo) - created).days / 30
                if months_old > 0:
                    stars_per_month = stats["stars"] / months_old
                    if stars_per_month > 50:
                        findings.append(Finding(
                            repo_full_name=repo_obj.full_name,
                            finding_type="TREND",
                            severity="INFO",
                            title=f"高热度仓库: Star增长 {int(stars_per_month)} 个/月",
                            description=f"该仓库平均每月获得 {int(stars_per_month)} 个 Star，热度持续上升",
                            detail={
                                "stars": stats["stars"],
                                "stars_per_month": int(stars_per_month),
                                "months_old": int(months_old)
                            }
                        ))

        except RateLimitExceededException:
            raise  # 向上传递
        except Exception as e:
            logger.warning("trend_analysis_error", repo=repo_obj.full_name, error=str(e))

        return findings

    async def _analyze_supply_chain(self, repo_obj) -> List[Finding]:
        """分析依赖供应链风险 - 使用项目统一的 LLM 配置。"""
        findings = []

        dep_files = ["requirements.txt", "package.json", "pom.xml", "go.mod", "Cargo.toml"]

        for fname in dep_files:
            try:
                content_file = await asyncio.to_thread(repo_obj.get_contents, fname)
                content = content_file.decoded_content.decode("utf-8", errors="ignore")

                # 只分析有实质内容的文件（避免空文件浪费 LLM 资源）
                if len(content.strip()) < 20:
                    continue

                prompt = f"""分析以下依赖文件的供应链安全风险：

仓库: {repo_obj.full_name}
文件: {fname}

内容:
```
{content[:2000]}  # 限制长度
```

请检查：
1. 是否有已知高危依赖（log4j, moment等）
2. 是否有版本过旧的依赖
3. 是否有可疑的私有源
4. 是否有未锁定的版本（可能导致供应链攻击）

以JSON格式返回风险评估（如果没有风险返回空对象）：
{"risks": [{"package": "...", "severity": "HIGH|MEDIUM|LOW", "reason": "..."}]}"""

                # 使用项目统一的 LLM 配置
                response = await asyncio.to_thread(
                    lambda: self.model.invoke(prompt)
                )

                result_text = response.content

                # 尝试解析 JSON
                try:
                    # 提取 JSON 部分
                    if "{" in result_text and "}" in result_text:
                        start = result_text.find("{")
                        end = result_text.rfind("}") + 1
                        json_str = result_text[start:end]
                        result = json.loads(json_str)
                        for risk in result.get("risks", []):
                            findings.append(Finding(
                                repo_full_name=repo_obj.full_name,
                                finding_type="SUPPLY_CHAIN",
                                severity=risk.get("severity", "MEDIUM"),
                                title=f"供应链风险: {risk.get('package', '未知依赖')}",
                                description=risk.get("reason", ""),
                                detail={"file": fname, "package": risk.get("package")}
                            ))
                except json.JSONDecodeError:
                    logger.debug("supply_chain_json_parse_failed", file=fname)

            except GithubException as e:
                if e.status == 404:
                    pass  # 文件不存在，正常跳过
                elif e.status == 403:
                    logger.warning("supply_chain_rate_limit", file=fname)
                    raise RateLimitExceededException(e.headers.get("X-RateLimit-Reset"))
                else:
                    logger.warning("supply_chain_github_error", file=fname, status=e.status)
            except Exception as e:
                logger.warning("supply_chain_analysis_error", file=fname, error=str(e))

        return findings