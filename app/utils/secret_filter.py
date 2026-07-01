"""SECRET 扫描过滤策略 - 统一的敏感信息扫描配置。

过滤策略:
1. 排除第三方依赖目录
2. 已知示例值白名单
3. 文档文件降级
4. 示例关键词检测
"""

import re
from typing import Dict, List, Optional, Tuple


class SecretFilterPolicy:
    """SECRET 扫描过滤策略。"""

    # 排除路径 - 第三方依赖目录
    EXCLUDE_PATHS = [
        "vendor/", "/vendor/",          # Go, PHP 依赖
        "node_modules/",                # Node.js 依赖
        "third_party/", "3rdparty/",    # C++ 依赖
        ".bundle/", "gems/",            # Ruby 依赖
        "Pods/",                        # iOS CocoaPods
        "packages/",                    # NuGet (C#)
        "target/dependency/",           # Maven
        "__pycache__/", ".venv/",       # Python 缓存/虚拟环境
        "dist/", "build/",              # 构建输出
    ]

    # 已知示例值白名单（官方文档示例，不是真实密钥）
    KNOWN_EXAMPLES = {
        "aws_access_key": [
            "AKIAIOSFODNN7EXAMPLE",     # AWS 官方文档示例
        ],
        "github_token": [
            "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",  # GitHub 示例格式
        ],
    }

    # 文档文件特征（降低严重程度）
    DOC_PATTERNS = [
        r"^doc\.go$",
        r"^README", r"^readme",
        r"CHANGELOG", r"changelog",
        r"\.md$", r"\.rst$",
        r"^example", r"^sample",
        r"^doc/", r"/doc/",
    ]

    # 示例关键词检测
    EXAMPLE_KEYWORDS = ["example", "sample", "demo", "placeholder", "xxx", "test", "fake"]

    # 敏感信息正则模式
    SECRET_PATTERNS = {
        "aws_access_key": r"AKIA[0-9A-Z]{16}",
        "aws_secret_key": r"(?i)aws_secret_access_key[\s]*=[\s]*['\"][0-9a-zA-Z/+]{40}['\"]",
        "github_token": r"gh[pous]_[0-9a-zA-Z]{36,}",
        "private_key": r"-----BEGIN (RSA|DSA|EC|OPENSSH) PRIVATE KEY-----",
        "jwt_secret": r"(?i)jwt[_-]?secret[\s]*=[\s]*['\"][0-9a-zA-Z]{20,}['\"]",
        "api_key": r"(?i)api[_-]?key[\s]*=[\s]*['\"][0-9a-zA-Z]{16,}['\"]",
        "generic_secret": r"(?i)secret[_-]?key[\s]*=[\s]*['\"][0-9a-zA-Z]{20,}['\"]",
    }

    @staticmethod
    def should_exclude(filename: str) -> bool:
        """检查是否应排除该文件路径。

        Args:
            filename: 文件路径

        Returns:
            True 表示应排除
        """
        for exclude in SecretFilterPolicy.EXCLUDE_PATHS:
            if exclude in filename:
                return True
        return False

    @staticmethod
    def is_known_example(pattern_name: str, match_text: str) -> bool:
        """检查是否是已知示例值。

        Args:
            pattern_name: 模式名称 (aws_access_key 等)
            match_text: 匹配文本

        Returns:
            True 表示是已知示例
        """
        examples = SecretFilterPolicy.KNOWN_EXAMPLES.get(pattern_name, [])
        for ex in examples:
            if ex in match_text or match_text.startswith(ex[:8]):
                return True
        return False

    @staticmethod
    def is_doc_file(filename: str) -> bool:
        """检查是否是文档文件。

        Args:
            filename: 文件名

        Returns:
            True 表示是文档文件
        """
        for pat in SecretFilterPolicy.DOC_PATTERNS:
            if re.search(pat, filename, re.IGNORECASE):
                return True
        return False

    @staticmethod
    def has_example_context(text: str, match_pos: int) -> bool:
        """检查匹配位置附近是否有示例关键词。

        Args:
            text: 文本内容
            match_pos: 匹配位置

        Returns:
            True 表示有示例上下文
        """
        context_start = max(0, match_pos - 100)
        context_end = min(len(text), match_pos + 100)
        context = text[context_start:context_end].lower()

        for kw in SecretFilterPolicy.EXAMPLE_KEYWORDS:
            if kw in context:
                return True
        return False

    @staticmethod
    def determine_severity(pattern_name: str, match_text: str,
                           filename: str, patch: str,
                           match_pos: int) -> Tuple[str, str]:
        """确定敏感信息的严重程度和原因。

        Args:
            pattern_name: 模式名称
            match_text: 匹配文本
            filename: 文件名
            patch: diff patch 内容
            match_pos: 匹配位置

        Returns:
            (severity, reason) 如 ("HIGH", "") 或 ("INFO", "文档文件，可能是示例")
        """
        # 1. 已知示例值 -> INFO
        if SecretFilterPolicy.is_known_example(pattern_name, match_text):
            return "INFO", "已知示例值（官方文档示例）"

        # 2. 排除路径 -> INFO (不扫描)
        if SecretFilterPolicy.should_exclude(filename):
            return "INFO", "第三方依赖目录"

        # 3. 文档文件 -> INFO
        if SecretFilterPolicy.is_doc_file(filename):
            return "INFO", "文档文件，可能是示例"

        # 4. 示例上下文 -> MEDIUM
        if SecretFilterPolicy.has_example_context(patch, match_pos):
            return "MEDIUM", "上下文包含示例关键词"

        # 5. 默认高危
        if pattern_name in ["private_key", "aws_secret_key"]:
            return "CRITICAL", ""

        return "HIGH", ""

    @staticmethod
    def get_patterns() -> Dict[str, str]:
        """获取所有敏感信息正则模式。"""
        return SecretFilterPolicy.SECRET_PATTERNS.copy()


# 便捷函数
def should_exclude_secret(filename: str) -> bool:
    """检查是否应排除（便捷函数）。"""
    return SecretFilterPolicy.should_exclude(filename)


def get_secret_severity(pattern_name: str, match_text: str,
                        filename: str, patch: str,
                        match_pos: int) -> Tuple[str, str]:
    """获取敏感信息严重程度（便捷函数）。"""
    return SecretFilterPolicy.determine_severity(
        pattern_name, match_text, filename, patch, match_pos
    )