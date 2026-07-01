"""
技能验证脚本。

验证技能格式和依赖是否满足要求。
"""

import os
import re
import sys
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional


def parse_frontmatter(content: str) -> Optional[Dict[str, Any]]:
    """解析 SKILL.md 的 YAML frontmatter。"""
    pattern = r"^---\s*\n(.*?)\n---\s*\n(.*)$"
    match = re.match(pattern, content, re.DOTALL)

    if not match:
        return None

    frontmatter_str = match.group(1)
    body = match.group(2)

    # 简单解析 YAML frontmatter（不使用 yaml 库）
    frontmatter = {}
    current_key = None
    current_list = None

    for line in frontmatter_str.split("\n"):
        stripped = line.strip()

        if not stripped:
            continue

        # 列表项
        if stripped.startswith("- ") and current_list is not None:
            current_list.append(stripped[2:].strip("\"'"))
            continue

        # 键值对
        if ":" in line and not line.startswith(" "):
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip("\"'")

            if value == "":
                # 可能是嵌套对象或列表
                current_key = key
                if key == "dependencies":
                    current_list = []
                    frontmatter[key] = current_list
                elif key == "metadata":
                    frontmatter[key] = {}
                    current_list = None
                else:
                    frontmatter[key] = {}
                    current_list = None
            else:
                frontmatter[key] = value
                current_key = None
                current_list = None
        elif line.startswith("  ") and current_key:
            # 嵌套值
            key, _, value = line.strip().partition(":")
            if value:
                frontmatter[current_key][key] = value.strip().strip("\"'")

    return {
        "frontmatter": frontmatter,
        "body": body,
    }


def validate_skill_md(skill_path: Path) -> Dict[str, Any]:
    """验证 SKILL.md 文件格式。"""
    skill_md_path = skill_path / "SKILL.md"

    findings = []

    if not skill_md_path.exists():
        return {
            "valid": False,
            "findings": [{"error": "SKILL.md not found", "severity": "critical"}],
        }

    try:
        content = skill_md_path.read_text(encoding="utf-8")
        parsed = parse_frontmatter(content)

        if not parsed:
            findings.append({
                "error": "Invalid frontmatter format",
                "severity": "critical",
                "file": str(skill_md_path),
            })
            return {"valid": False, "findings": findings}

        frontmatter = parsed["frontmatter"]

        # 检查必需字段
        required_fields = ["name", "description", "version"]
        for field in required_fields:
            if field not in frontmatter:
                findings.append({
                    "error": f"Missing required field: {field}",
                    "severity": "high",
                    "file": str(skill_md_path),
                })

        # 检查版本格式
        version = frontmatter.get("version", "")
        if version and not re.match(r"^\d+\.\d+\.\d+$", str(version)):
            findings.append({
                "warning": f"Invalid version format: {version}",
                "severity": "low",
                "file": str(skill_md_path),
            })

        return {
            "valid": len([f for f in findings if f.get("severity") in ["critical", "high"]]) == 0,
            "findings": findings,
            "frontmatter": frontmatter,
            "body": parsed["body"],
        }

    except Exception as e:
        return {
            "valid": False,
            "findings": [{"error": f"Failed to parse SKILL.md: {e}", "severity": "critical"}],
        }


def validate_dependencies(skill_path: Path, frontmatter: Dict) -> Dict[str, Any]:
    """验证依赖是否可安装。"""
    dependencies = frontmatter.get("dependencies", [])
    findings = []

    if not dependencies:
        return {"valid": True, "findings": [], "installed": []}

    # 检查 pip 是否可用
    try:
        result = subprocess.run(
            ["pip", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return {
                "valid": True,
                "findings": [{"warning": "pip not available for dependency check", "severity": "low"}],
                "installed": [],
            }
    except Exception:
        return {
            "valid": True,
            "findings": [{"warning": "pip check failed", "severity": "low"}],
            "installed": [],
        }

    # 检查每个依赖
    installed = []
    for dep in dependencies:
        if not isinstance(dep, str):
            continue

        try:
            # 尝试导入
            module_name = dep.split("[")[0].split(">")[0].split("<")[0].split("=")[0].strip()
            result = subprocess.run(
                ["python", "-c", f"import {module_name.replace('-', '_')}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                installed.append(dep)
            else:
                findings.append({
                    "warning": f"Dependency not installed: {dep}",
                    "severity": "medium",
                })
        except Exception as e:
            findings.append({
                "warning": f"Dependency check failed for {dep}: {e}",
                "severity": "medium",
            })

    return {
        "valid": len([f for f in findings if f.get("severity") in ["critical", "high"]]) == 0,
        "findings": findings,
        "installed": installed,
    }


def validate_scripts(skill_path: Path) -> Dict[str, Any]:
    """验证脚本文件是否存在且可执行。"""
    scripts_path = skill_path / "scripts"
    findings = []

    if not scripts_path.exists():
        # 脚本目录是可选的
        return {"valid": True, "findings": [], "scripts": []}

    scripts = []
    for script in scripts_path.glob("*.py"):
        scripts.append(str(script))

        # 检查 Python 语法
        try:
            result = subprocess.run(
                ["python", "-m", "py_compile", str(script)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                findings.append({
                    "error": f"Syntax error in {script.name}: {result.stderr[:200]}",
                    "severity": "high",
                    "file": str(script),
                })
        except Exception as e:
            findings.append({
                "warning": f"Failed to validate {script.name}: {e}",
                "severity": "low",
            })

    return {
        "valid": len([f for f in findings if f.get("severity") in ["critical", "high"]]) == 0,
        "findings": findings,
        "scripts": scripts,
    }


def validate_skill(skill_path: str) -> Dict[str, Any]:
    """
    验证技能可用性。

    Args:
        skill_path: 技能目录路径

    Returns:
        {
            "valid": bool,
            "findings": List[Dict],
            "summary": Dict,
            "frontmatter": Dict (如果解析成功)
        }
    """
    skill_path = Path(skill_path)

    if not skill_path.exists():
        return {
            "valid": False,
            "findings": [{"error": f"Skill path not found: {skill_path}", "severity": "critical"}],
            "summary": {"total": 1, "critical": 1, "high": 0, "medium": 0},
        }

    all_findings = []
    frontmatter = None

    # 1. 验证 SKILL.md
    md_result = validate_skill_md(skill_path)
    all_findings.extend(md_result.get("findings", []))
    frontmatter = md_result.get("frontmatter")

    # 2. 验证依赖
    if frontmatter:
        dep_result = validate_dependencies(skill_path, frontmatter)
        all_findings.extend(dep_result.get("findings", []))

    # 3. 验证脚本
    script_result = validate_scripts(skill_path)
    all_findings.extend(script_result.get("findings", []))

    # 统计
    summary = {
        "total": len(all_findings),
        "critical": sum(1 for f in all_findings if f.get("severity") == "critical"),
        "high": sum(1 for f in all_findings if f.get("severity") == "high"),
        "medium": sum(1 for f in all_findings if f.get("severity") == "medium"),
        "low": sum(1 for f in all_findings if f.get("severity") == "low"),
    }

    is_valid = summary["critical"] == 0 and summary["high"] == 0

    return {
        "valid": is_valid,
        "findings": all_findings,
        "summary": summary,
        "frontmatter": frontmatter,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python validate_skill.py <skill_path>")
        sys.exit(1)

    result = validate_skill(sys.argv[1])
    print(json.dumps(result, indent=2, ensure_ascii=False))