"""L3 深度扫描器 - 全量 LLM 分析。"""

import os
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from github import Github, GithubException
from app.log_utils import get_logger
from app.models import Finding, ScanTask
from app.database import FindingDAO, ScanTaskDAO, OrgConfigDAO, RepoMonitorDAO, init_business_tables

logger = get_logger("deep_scanner")


class DeepScanner:
    """L3 深度扫描器 - 全量使用 LLM 进行深度分析。

    L3 扫描策略：
    1. 获取仓库完整代码结构和历史
    2. 使用 LLM 分析代码质量、安全模式、架构风险
    3. 深度分析依赖安全和供应链风险
    4. 分析贡献者行为和社区健康趋势
    """

    def __init__(self, github_token: str = None):
        self.github_token = github_token or os.getenv("GITHUB_TOKEN")
        self.github = Github(self.github_token)
        self.llm_enabled = os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")

    async def close(self):
        """关闭资源。"""
        pass

    async def scan_repo(self, owner: str, repo: str) -> List[Finding]:
        """深度扫描单个仓库。"""
        findings = []
        repo_full_name = f"{owner}/{repo}"

        logger.info("l3_scan_repo_start", repo=repo_full_name)

        if not self.llm_enabled:
            logger.warning("l3_llm_not_enabled", repo=repo_full_name)
            return findings

        try:
            repo_obj = await asyncio.to_thread(self.github.get_repo, repo_full_name)

            # 1. LLM 分析代码结构
            structure_findings = await self._analyze_code_structure(repo_obj)
            findings.extend(structure_findings)

            # 2. LLM 分析安全问题模式
            security_findings = await self._analyze_security_patterns(repo_obj)
            findings.extend(security_findings)

            # 3. LLM 分析依赖供应链
            supply_chain_findings = await self._analyze_supply_chain(repo_obj)
            findings.extend(supply_chain_findings)

            # 4. LLM 分析社区健康和贡献者行为
            community_findings = await self._analyze_community_deep(repo_obj)
            findings.extend(community_findings)

            logger.info("l3_scan_repo_done", repo=repo_full_name, findings=len(findings))

        except GithubException as e:
            logger.warning("l3_scan_repo_error", repo=repo_full_name, error=str(e))

        return findings

    async def _analyze_code_structure(self, repo_obj) -> List[Finding]:
        """使用 LLM 分析代码结构和质量。"""
        findings = []

        try:
            # 获取主要文件内容
            contents = await asyncio.to_thread(lambda: list(repo_obj.get_contents("")))

            code_files = []
            for item in contents[:20]:  # 只分析前20个文件
                if item.type == "file" and item.name.endswith((".py", ".js", ".java", ".go", ".ts")):
                    try:
                        content = await asyncio.to_thread(lambda: item.decoded_content.decode("utf-8", errors="ignore"))
                        code_files.append({"name": item.name, "content": content[:5000]})  # 截取前5000字符
                    except Exception:
                        pass

            if not code_files:
                return findings

            # 构建 LLM prompt
            prompt = f"""分析以下仓库的代码结构和质量：

仓库: {repo_obj.full_name}
语言: {repo_obj.language}

代码文件列表:
{json.dumps([f["name"] for f in code_files])}

主要代码内容（前几个文件）:
"""

            for f in code_files[:5]:
                prompt += f"\n### {f['name']}\n```\n{f['content'][:2000]}\n```\n"

            prompt += """
请评估：
1. 代码组织结构是否清晰
2. 是否存在明显的安全风险模式（硬编码密码、SQL拼接等）
3. 是否有过度复杂的逻辑
4. 文档和注释质量

以JSON格式返回问题列表：
{"issues": [{"type": "...", "severity": "HIGH|MEDIUM|LOW", "description": "...", "file": "..."}]}"""

            import openai
            client = openai.OpenAI()

            response = await asyncio.to_thread(
                lambda: client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3
                )
            )

            result_text = response.choices[0].message.content

            try:
                result = json.loads(result_text)
                for issue in result.get("issues", []):
                    findings.append(Finding(
                        repo_full_name=repo_obj.full_name,
                        finding_type="COMMUNITY" if issue["type"] == "documentation" else "SECRET",
                        severity=issue.get("severity", "MEDIUM"),
                        title=f"代码质量: {issue.get('type', '未知问题')}",
                        description=issue.get("description", ""),
                        detail={"file": issue.get("file"), "type": issue.get("type")}
                    ))
            except json.JSONDecodeError:
                # 无法解析，直接作为描述
                if "风险" in result_text or "问题" in result_text:
                    findings.append(Finding(
                        repo_full_name=repo_obj.full_name,
                        finding_type="COMMUNITY",
                        severity="LOW",
                        title="LLM 代码分析结果",
                        description=result_text[:500]
                    ))

        except Exception as e:
            logger.warning("l3_structure_analysis_error", repo=repo_obj.full_name, error=str(e))

        return findings

    async def _analyze_security_patterns(self, repo_obj) -> List[Finding]:
        """使用 LLM 深度分析安全模式。"""
        findings = []

        # 获取最近提交的代码变更
        try:
            commits = await asyncio.to_thread(lambda: list(repo_obj.get_commits()[:20]))

            code_changes = []
            for commit in commits:
                for file in commit.files[:10]:
                    if file.patch and file.filename.endswith((".py", ".js", ".java", ".go")):
                        code_changes.append({
                            "file": file.filename,
                            "patch": file.patch[:2000],
                            "sha": commit.sha[:8]
                        })

            if not code_changes:
                return findings

            prompt = f"""分析以下代码变更中的安全风险：

仓库: {repo_obj.full_name}

最近的代码变更:
"""

            for change in code_changes[:10]:
                prompt += f"\n### {change['file']} (commit {change['sha']})\n```diff\n{change['patch']}\n```\n"

            prompt += """
请检查：
1. 是否引入了新的敏感信息（密钥、密码）
2. 是否有不安全的编码模式（SQL拼接、命令注入）
3. 是否有权限控制变更
4. 是否有可疑的外部依赖引入

以JSON格式返回发现：
{"findings": [{"type": "...", "severity": "HIGH|MEDIUM|LOW", "file": "...", "description": "..."}]}"""

            import openai
            client = openai.OpenAI()

            response = await asyncio.to_thread(
                lambda: client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3
                )
            )

            result_text = response.choices[0].message.content

            try:
                result = json.loads(result_text)
                for f in result.get("findings", []):
                    findings.append(Finding(
                        repo_full_name=repo_obj.full_name,
                        finding_type="SECRET",
                        severity=f.get("severity", "MEDIUM"),
                        title=f"安全模式: {f.get('type', '未知')}",
                        description=f.get("description", ""),
                        detail={"file": f.get("file")}
                    ))
            except json.JSONDecodeError:
                pass

        except Exception as e:
            logger.warning("l3_security_analysis_error", repo=repo_obj.full_name, error=str(e))

        return findings

    async def _analyze_supply_chain(self, repo_obj) -> List[Finding]:
        """分析依赖供应链风险。"""
        findings = []

        # 获取依赖文件
        dep_files = ["requirements.txt", "package.json", "pom.xml", "go.mod", "Cargo.toml"]

        for fname in dep_files:
            try:
                content_file = await asyncio.to_thread(repo_obj.get_contents, fname)
                content = content_file.decoded_content.decode("utf-8", errors="ignore")

                # 使用 LLM 分析依赖风险
                prompt = f"""分析以下依赖文件的供应链安全风险：

仓库: {repo_obj.full_name}
文件: {fname}

内容:
```
{content}
```

请检查：
1. 是否有已知高危依赖（log4j, moment等）
2. 是否有版本过旧的依赖
3. 是否有可疑的私有源
4. 是否有未锁定的版本（可能导致供应链攻击）

以JSON格式返回风险评估：
{"risks": [{"package": "...", "severity": "HIGH|MEDIUM|LOW", "reason": "..."}]}"""

                import openai
                client = openai.OpenAI()

                response = await asyncio.to_thread(
                    lambda: client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.3
                    )
                )

                result_text = response.choices[0].message.content

                try:
                    result = json.loads(result_text)
                    for risk in result.get("risks", []):
                        findings.append(Finding(
                            repo_full_name=repo_obj.full_name,
                            finding_type="CVE",
                            severity=risk.get("severity", "MEDIUM"),
                            title=f"供应链风险: {risk.get('package', '未知依赖')}",
                            description=risk.get("reason", ""),
                            detail={"file": fname, "package": risk.get("package")}
                        ))
                except json.JSONDecodeError:
                    pass

            except GithubException:
                # 文件不存在
                pass
            except Exception as e:
                logger.warning("l3_supply_chain_error", file=fname, error=str(e))

        return findings

    async def _analyze_community_deep(self, repo_obj) -> List[Finding]:
        """深度分析社区健康。"""
        findings = []

        try:
            # 获取贡献者统计
            contributors = await asyncio.to_thread(lambda: list(repo_obj.get_contributors()[:50]))

            # 获取 Issue 和 PR 统计
            issues = await asyncio.to_thread(lambda: list(repo_obj.get_issues(state="all")[:100]))
            prs = await asyncio.to_thread(lambda: list(repo_obj.get_pulls(state="all")[:100]))

            # 构建 LLM prompt
            prompt = f"""分析以下仓库的社区健康度：

仓库: {repo_obj.full_name}
Stars: {repo_obj.stargazers_count}
Forks: {repo_obj.forks_count}

贡献者数量: {len(contributors)}
最近Issue数: {len(issues)}
最近PR数: {len(prs)}

主要贡献者贡献分布:
"""

            contributor_stats = {}
            for c in contributors[:20]:
                try:
                    contributor_stats[c.login] = c.contributions
                except Exception:
                    pass

            prompt += json.dumps(contributor_stats) + "\n"

            prompt += """
请分析：
1. 贡献者活跃度是否健康（是否有核心维护者）
2. Issue处理效率如何
3. 是否有社区治理风险（单点依赖、维护停滞）
4. 是否需要关注的风险信号

以简短文字返回分析结果（不超过200字）。"""

            import openai
            client = openai.OpenAI()

            response = await asyncio.to_thread(
                lambda: client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3
                )
            )

            analysis = response.choices[0].message.content

            # 根据分析结果决定是否生成 Finding
            if any(word in analysis.lower() for word in ["风险", "警告", "停滞", "单点依赖", "维护者缺失"]):
                findings.append(Finding(
                    repo_full_name=repo_obj.full_name,
                    finding_type="COMMUNITY",
                    severity="MEDIUM",
                    title="社区健康风险",
                    description=analysis,
                    detail={
                        "contributors": len(contributors),
                        "issues": len(issues),
                        "prs": len(prs)
                    }
                ))

        except Exception as e:
            logger.warning("l3_community_analysis_error", repo=repo_obj.full_name, error=str(e))

        return findings

    async def scan_org(self, org_name: str, scan_task_id: int = None,
                       trigger_by: str = None, concurrency: int = 10) -> Dict[str, Any]:
        """扫描整个组织（L3 级别）。"""
        logger.info("l3_scan_org_start", org=org_name)

        await init_business_tables()

        # 获取组织仓库
        try:
            org = await asyncio.to_thread(self.github.get_organization, org_name)
            repos = await asyncio.to_thread(lambda: list(org.get_repos()))
        except GithubException as e:
            return {"error": str(e)}

        # 创建扫描任务
        run_id = f"L3SCAN_{org_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        task = ScanTask(
            run_id=run_id,
            scan_type="L3_DEEP",
            org_name=org_name,
            trigger_by=trigger_by or "manual",
            status="running",
            total_repos=len(repos)
        )
        task_id = await ScanTaskDAO.create(task)

        # L3 扫描使用较低并发（因为 LLM 调用较多）
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

        logger.info("l3_scan_org_done", org=org_name, repos_scanned=scanned, findings=len(all_findings))

        return {
            "run_id": run_id,
            "org_name": org_name,
            "repos_scanned": scanned,
            "total_findings": len(all_findings),
            "task_id": task_id
        }