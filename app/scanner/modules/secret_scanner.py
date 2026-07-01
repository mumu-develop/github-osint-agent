
"""敏感信息扫描模块 - 检查仓库中的敏感信息泄露。"""  

import os
import asyncio
import re
from typing import List
from github import Github, GithubException
from app.log_utils import get_logger
from app.models import Finding

logger = get_logger("secret_scanner")

SECRET_PATTERNS = [
    (r"ghp_[a-zA-Z0-9]{36}", "GitHub Personal Token"),
    (r"gho_[a-zA-Z0-9]{36}", "GitHub OAuth Token"),
    (r"aws_access_key_id", "AWS Access Key"),
    (r"aws_secret_access_key", "AWS Secret Key"),
    (r"-----BEGIN PRIVATE KEY-----", "Private Key"),
]

EXCLUDE_PATTERNS = [r"\.env\.example", r"\.git/", r"node_modules/", r"tests/"]


class SecretScanner:
    def __init__(self, github_token: str = None):
        self.github_token = github_token or os.getenv("GITHUB_TOKEN")  
        self.github = Github(self.github_token)

    async def close(self):
        pass

    async def scan(self, repo_obj) -> List[Finding]:
        findings = []
        try:
            tree = await asyncio.to_thread(lambda: repo_obj.get_git_tree(repo_obj.default_branch, recursive=True))
            for item in tree.tree:
                if item.type != "blob":
                    continue
                if any(re.search(p, item.path) for p in EXCLUDE_PATTERNS):
                    continue
                try:
                    content = await asyncio.to_thread(lambda: repo_obj.get_contents(item.path))
                    if isinstance(content, list):
                        continue
                    fc = content.decoded_content.decode("utf-8", errors="ignore")  
                    for pattern, stype in SECRET_PATTERNS:
                        if re.search(pattern, fc):
                            findings.append(Finding(
                                repo_full_name=repo_obj.full_name,
                                finding_type="SECRET",
                                severity="HIGH",
                                title=f"敏感信息泄露: {stype}",
                                description=f"在 {item.path} 中发现 {stype}",
                                detail={"file": item.path}
                            ))
                except Exception:
                    pass
        except Exception as e:
            logger.error("scan_error", error=str(e))
        return findings
