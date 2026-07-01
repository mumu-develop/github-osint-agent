"""
技能安全扫描脚本。

检查技能包是否包含危险代码或敏感文件。
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Any


# 危险代码模式
DANGEROUS_PATTERNS = [
    r"\bexec\s*\(",
    r"\beval\s*\(",
    r"\bcompile\s*\(",
    r"\bos\.system\s*\(",
    r"\bos\.popen\s*\(",
    r"\bsubprocess\.(call|run|Popen)\s*\([^)]*shell\s*=\s*True",
    r"\b__import__\s*\(",
    r"\bimportlib\.import_module\s*\(",
    r"\bpickle\.loads\s*\(",
    r"\byaml\.load\s*\([^)]*\)",  # 不带 Loader 的 yaml.load
    r"\bshutil\.rmtree\s*\(",
    r"\bopen\s*\([^)]*['\"]w['\"][^)]*\.\benv\b",
]

# 敏感文件模式
SENSITIVE_FILES = [
    ".env",
    ".credentials",
    ".secrets",
    ".pem",
    ".key",
    ".p12",
    "id_rsa",
    "id_ed25519",
    "credentials.json",
    "service-account.json",
    ".netrc",
    "_netrc",
]

# 允许的网络域名白名单
ALLOWED_DOMAINS = [
    "api.github.com",
    "dashscope.aliyuncs.com",
    "api.osv.dev",
    "pypi.org",
    "files.pythonhosted.org",
    "github.com",
    "raw.githubusercontent.com",
]


def scan_dangerous_code(file_path: Path) -> List[Dict[str, Any]]:
    """扫描文件中的危险代码模式。"""
    findings = []

    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.split("\n")

        for line_num, line in enumerate(lines, 1):
            for pattern in DANGEROUS_PATTERNS:
                if re.search(pattern, line):
                    findings.append({
                        "file": str(file_path),
                        "line": line_num,
                        "pattern": pattern,
                        "content": line.strip()[:100],
                        "severity": "high",
                    })
    except Exception as e:
        findings.append({
            "file": str(file_path),
            "error": str(e),
            "severity": "error",
        })

    return findings


def scan_sensitive_files(skill_path: Path) -> List[Dict[str, Any]]:
    """扫描敏感文件。"""
    findings = []

    for root, dirs, files in os.walk(skill_path):
        for file in files:
            file_lower = file.lower()
            for sensitive in SENSITIVE_FILES:
                if sensitive.lower() in file_lower:
                    findings.append({
                        "file": os.path.join(root, file),
                        "type": "sensitive_file",
                        "pattern": sensitive,
                        "severity": "critical",
                    })

    return findings


def scan_network_connections(file_path: Path) -> List[Dict[str, Any]]:
    """扫描文件中的网络连接，检查是否连接到非白名单域名。"""
    findings = []

    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")

        # 匹配 URL 模式
        url_pattern = r'https?://([^/:"\s]+)'
        matches = re.findall(url_pattern, content)

        for domain in matches:
            # 提取主域名（去除端口）
            main_domain = domain.split(":")[0]
            is_allowed = any(
                main_domain == allowed or main_domain.endswith("." + allowed)
                for allowed in ALLOWED_DOMAINS
            )

            if not is_allowed:
                findings.append({
                    "file": str(file_path),
                    "domain": main_domain,
                    "severity": "medium",
                    "message": f"Network connection to non-whitelisted domain: {main_domain}",
                })
    except Exception as e:
        findings.append({
            "file": str(file_path),
            "error": str(e),
            "severity": "error",
        })

    return findings


def scan_skill(skill_path: str) -> Dict[str, Any]:
    """
    扫描技能安全性。

    Args:
        skill_path: 技能目录路径

    Returns:
        {
            "safe": bool,
            "findings": List[Dict],
            "summary": Dict
        }
    """
    skill_path = Path(skill_path)

    if not skill_path.exists():
        return {
            "safe": False,
            "findings": [{"error": f"Skill path not found: {skill_path}", "severity": "critical"}],
            "summary": {"total": 1, "critical": 1, "high": 0, "medium": 0},
        }

    all_findings = []

    # 1. 扫描敏感文件
    sensitive_findings = scan_sensitive_files(skill_path)
    all_findings.extend(sensitive_findings)

    # 2. 扫描 Python 文件中的危险代码和网络连接
    for py_file in skill_path.rglob("*.py"):
        code_findings = scan_dangerous_code(py_file)
        all_findings.extend(code_findings)

        network_findings = scan_network_connections(py_file)
        all_findings.extend(network_findings)

    # 3. 扫描 shell 脚本
    for sh_file in skill_path.rglob("*.sh"):
        code_findings = scan_dangerous_code(sh_file)
        all_findings.extend(code_findings)

    # 统计严重程度
    summary = {
        "total": len(all_findings),
        "critical": sum(1 for f in all_findings if f.get("severity") == "critical"),
        "high": sum(1 for f in all_findings if f.get("severity") == "high"),
        "medium": sum(1 for f in all_findings if f.get("severity") == "medium"),
    }

    # 判断是否安全
    is_safe = summary["critical"] == 0 and summary["high"] == 0

    return {
        "safe": is_safe,
        "findings": all_findings,
        "summary": summary,
    }


if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python scan_skill.py <skill_path>")
        sys.exit(1)

    result = scan_skill(sys.argv[1])
    print(json.dumps(result, indent=2, ensure_ascii=False))