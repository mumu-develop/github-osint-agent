"""许可证合规检查模块 - 检查仓库许可证合规性。"""

import os
import asyncio
from typing import Dict, List, Optional
from github import Github, GithubException
from app.log_utils import get_logger
from app.models import Finding

logger = get_logger("license_scanner")

# 许可证白名单
ALLOWED_LICENSES = ["MIT", "Apache-2.0", "BSD-3-Clause", "BSD-2-Clause", "ISC", "GPL-2.0", "GPL-3.0"]


class LicenseScanner:
    """许可证合规检查器 - 检查仓库许可证合规性。"""

    def __init__(self, github_token: str = None):
        self.github_token = github_token or os.getenv("GITHUB_TOKEN")
        self.github = Github(self.github_token)

    async def close(self):
        """关闭资源。"""
        pass

    async def scan(self, repo_obj) -> List[Finding]:
        """检查许可证合规性。"""
        findings = []

        try:
            license_info = await asyncio.to_thread(lambda: repo_obj.license)

            if not license_info:
                findings.append(Finding(
                    repo_full_name=repo_obj.full_name,
                    finding_type="LICENSE",
                    severity="MEDIUM",
                    title="许可证缺失",
                    description="仓库未声明许可证，可能存在合规风险"
                ))
            else:
                license_name = license_info.spdx_id or license_info.name
                if license_name not in ALLOWED_LICENSES:
                    findings.append(Finding(
                        repo_full_name=repo_obj.full_name,
                        finding_type="LICENSE",
                        severity="LOW",
                        title=f"非标准许可证: {license_name}",
                        description=f"仓库使用 {license_name} 许可证，不在标准白名单中",
                        detail={"license": license_name, "allowed": ALLOWED_LICENSES}
                    ))

        except Exception as e:
            logger.warning("license_check_error", repo=repo_obj.full_name, error=str(e))

        return findings