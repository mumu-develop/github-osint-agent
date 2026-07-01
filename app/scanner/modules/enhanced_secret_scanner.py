"""增强版密钥扫描模块 - 集成 detect-secrets 库。

方案三（混合方案）：
- 优先使用 detect-secrets（专业规则库）
- 备用使用正则匹配（覆盖 detect-secrets 未检测的类型）
- 白名单过滤减少误报
"""

import os
import re
import tempfile
import asyncio
from typing import Dict, List, Optional, Tuple
from github import Github, GithubException
from app.log_utils import get_logger
from app.models import Finding

logger = get_logger("enhanced_secret_scanner")

# 尝试导入 detect-secrets
try:
    from detect_secrets import SecretsCollection
    from detect_secrets.settings import default_settings
    HAS_DETECT_SECRETS = True
    logger.info("detect_secrets_available")
except ImportError:
    HAS_DETECT_SECRETS = False
    logger.warning("detect_secrets_not_available", message="使用备用正则匹配")


class EnhancedSecretScanner:
    """增强版密钥扫描器 - 集成 detect-secrets。"""

    # 正则模式（备用，覆盖 detect-secrets 未检测的类型）
    BACKUP_PATTERNS = {
        # GitHub Token
        "github_token": r"(ghp_[a-zA-Z0-9]{36}|gho_[a-zA-Z0-9]{36}|ghu_[a-zA-Z0-9]{36}|ghs_[a-zA-Z0-9]{36}|ghr_[a-zA-Z0-9]{36})",
        # GitHub OAuth
        "github_oauth": r"[a-f0-9]{40}",
        # AWS Access Key
        "aws_access_key": r"(A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}",
        # AWS Secret Key
        "aws_secret_key": r"(?i)aws(.{0,20})?['\"][0-9a-zA-Z\/+]{40}['\"]",
        # Google API Key
        "google_api_key": r"AIza[0-9A-Za-z\\-_]{35}",
        # Slack Token
        "slack_token": r"xox[baprs]-[0-9]{10}-[0-9]{10}-[0-9a-zA-Z]{24}",
        # JWT Secret
        "jwt_secret": r"(?i)(jwt|secret)['\"]?\s*[:=]\s*['\"]?[a-zA-Z0-9]{20,}",
        # Private Key
        "private_key": r"-----BEGIN (RSA |DSA |EC |OPENSSH )?PRIVATE KEY-----",
        # Generic Secret (高风险关键词)
        "generic_secret": r"(?i)(password|passwd|pwd|secret|api_key|apikey|access_key|auth_token)['\"]?\s*[:=]\s*['\"]?[^'\"\\s]{8,}",
        # Database URL
        "database_url": r"(mysql|postgres|mongodb|redis)://[^\\s]+:[^\\s]+@[^\\s]+",
        # Generic API Key Pattern
        "api_key": r"[a-zA-Z0-9]{32,45}",
    }

    # 白名单关键词（排除示例代码和文档）
    WHITELIST_KEYWORDS = [
        "example", "sample", "test", "demo", "placeholder",
        "your_key_here", "replace_with", "xxx", "yyy",
        "dummy", "fake", "mock", "stub", "fixture",
        "<your", "insert_your", "change_this",
    ]

    # 白名单文件（排除示例和文档）
    WHITELIST_FILES = [
        "example", "sample", "test", "demo", "doc", "docs",
        "readme", "changelog", "license", "contributing",
        ".md", ".rst", ".txt",  # 文档文件扩展名
    ]

    # 白名单路径
    WHITELIST_PATHS = [
        "test/", "tests/", "examples/", "docs/", "documentation/",
        "spec/", "specs/", "mock/", "mocks/", "fixture/",
    ]

    # 高严重程度密钥类型
    HIGH_SEVERITY_TYPES = [
        "private_key", "aws_secret_key", "aws_access_key",
        "github_token", "google_api_key", "jwt_secret"
    ]

    def __init__(self, github_token: str = None):
        self.github_token = github_token or os.getenv("GITHUB_TOKEN")
        self.github = Github(self.github_token)

    async def scan(self, repo_full_name: str) -> List[Finding]:
        """扫描仓库的敏感信息泄露。"""
        findings = []

        try:
            repo_obj = await asyncio.to_thread(self.github.get_repo, repo_full_name)

            # 获取最近提交的文件变更
            commits = await asyncio.to_thread(lambda: list(repo_obj.get_commits()[:10]))

            for commit in commits:
                files = await asyncio.to_thread(lambda: list(commit.files))

                for file in files:
                    if self._should_exclude(file.filename, file.patch):
                        continue

                    # 方法一：使用 detect-secrets（如果可用）
                    if HAS_DETECT_SECRETS and file.patch:
                        detect_findings = self._scan_with_detect_secrets(
                            file.patch, file.filename, commit.sha, repo_full_name
                        )
                        findings.extend(detect_findings)

                    # 方法二：备用正则匹配（覆盖更多类型）
                    regex_findings = self._scan_with_regex(
                        file.patch, file.filename, commit.sha, repo_full_name
                    )
                    findings.extend(regex_findings)

        except GithubException as e:
            logger.warning("github_error", repo=repo_full_name, error=str(e))
        except Exception as e:
            logger.warning("scan_error", repo=repo_full_name, error=str(e))

        # 去重（同一文件同一位置可能被两种方法检测）
        findings = self._deduplicate(findings)

        return findings

    def _should_exclude(self, filename: str, content: str) -> bool:
        """判断是否应该排除此文件。"""
        filename_lower = filename.lower()

        # 1. 白名单文件名
        for whitelist in self.WHITELIST_FILES:
            if whitelist in filename_lower:
                return True

        # 2. 白名单路径
        for path in self.WHITELIST_PATHS:
            if path in filename_lower:
                return True

        # 3. 白名单关键词（内容中包含）
        if content:
            content_lower = content.lower()
            for keyword in self.WHITELIST_KEYWORDS:
                if keyword in content_lower:
                    # 检查是否在密钥附近出现（+-50字符内）
                    # 如果是，则认为是示例代码
                    return True

        # 4. 文件类型过滤（二进制文件等）
        excluded_extensions = ['.png', '.jpg', '.gif', '.svg', '.pdf', '.zip', '.jar', '.war']
        for ext in excluded_extensions:
            if filename_lower.endswith(ext):
                return True

        return False

    def _scan_with_detect_secrets(self, content: str, filename: str,
                                    commit_sha: str, repo_full_name: str) -> List[Finding]:
        """使用 detect-secrets 库扫描。"""
        findings = []

        try:
            # 创建临时文件供 detect-secrets 扫描
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(content)
                temp_path = f.name

            # 使用 detect-secrets 扫描
            secrets = SecretsCollection()
            secrets.scan_file(temp_path)

            # 清理临时文件
            os.unlink(temp_path)

            # 处理检测结果
            for secret in secrets:
                # 获取密钥类型
                secret_type = secret.secret_type or "unknown"
                secret_value = secret.secret_value or ""

                # 过滤白名单
                if self._is_whitelist_value(secret_value):
                    continue

                severity = self._get_severity(secret_type)

                findings.append(Finding(
                    repo_full_name=repo_full_name,
                    finding_type="SECRET",
                    severity=severity,
                    title=f"敏感信息泄露: {secret_type}",
                    description=f"在文件 {filename} 中发现 {secret_type}（由 detect-secrets 检测）",
                    detail={
                        "file": filename,
                        "pattern_type": secret_type,
                        "match_value": secret_value[:20] + "..." if len(secret_value) > 20 else secret_value,
                        "line_number": secret.line_number,
                        "commit_sha": commit_sha,
                        "scanner": "detect-secrets"
                    }
                ))

        except Exception as e:
            logger.warning("detect_secrets_error", file=filename, error=str(e))

        return findings

    def _scan_with_regex(self, content: str, filename: str,
                          commit_sha: str, repo_full_name: str) -> List[Finding]:
        """使用正则匹配扫描（备用方法）。"""
        findings = []

        if not content:
            return findings

        for pattern_name, pattern in self.BACKUP_PATTERNS.items():
            try:
                matches = re.findall(pattern, content)
                for match in matches:
                    match_text = match if isinstance(match, str) else match[0]

                    # 过滤白名单
                    if self._is_whitelist_value(match_text):
                        continue

                    severity = self._get_severity(pattern_name)

                    findings.append(Finding(
                        repo_full_name=repo_full_name,
                        finding_type="SECRET",
                        severity=severity,
                        title=f"敏感信息泄露: {pattern_name}",
                        description=f"在文件 {filename} 中发现可能的 {pattern_name}",
                        detail={
                            "file": filename,
                            "pattern_type": pattern_name,
                            "match_value": match_text[:20] + "..." if len(match_text) > 20 else match_text,
                            "commit_sha": commit_sha,
                            "scanner": "regex"
                        }
                    ))
            except Exception as e:
                logger.warning("regex_error", pattern=pattern_name, error=str(e))

        return findings

    def _is_whitelist_value(self, value: str) -> bool:
        """检查密钥值是否在白名单中。"""
        value_lower = value.lower()

        for keyword in self.WHITELIST_KEYWORDS:
            if keyword in value_lower:
                return True

        # 检查是否是明显的示例格式
        example_patterns = [
            r"^xxx+$",  # xxx, xxxxxx
            r"^yyy+$",  # yyy, yyyyyy
            r"^your_.*_here$",  # your_key_here
            r"^insert_.*$",  # insert_your_key
            r"^replace_.*$",  # replace_with_your_key
            r"^placeholder",  # placeholder_*
        ]

        for pattern in example_patterns:
            if re.match(pattern, value_lower):
                return True

        return False

    def _get_severity(self, secret_type: str) -> str:
        """获取密钥的严重程度。"""
        secret_type_lower = secret_type.lower()

        for high_type in self.HIGH_SEVERITY_TYPES:
            if high_type in secret_type_lower:
                return "HIGH"

        # JWT 和认证相关
        if "jwt" in secret_type_lower or "auth" in secret_type_lower:
            return "HIGH"

        # API 密钥
        if "api" in secret_type_lower or "key" in secret_type_lower:
            return "MEDIUM"

        # 其他
        return "LOW"

    def _deduplicate(self, findings: List[Finding]) -> List[Finding]:
        """去重（同一文件同一类型只保留一个）。"""
        seen = set()
        unique_findings = []

        for f in findings:
            # 使用 文件+类型+值前缀 作为唯一标识
            key = (
                f.detail.get("file", ""),
                f.detail.get("pattern_type", ""),
                f.detail.get("match_value", "")[:15]
            )

            if key not in seen:
                seen.add(key)
                unique_findings.append(f)

        return unique_findings

    async def close(self):
        """关闭资源。"""
        pass