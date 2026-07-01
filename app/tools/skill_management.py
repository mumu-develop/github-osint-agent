"""
技能管理工具。

提供技能下载、扫描、验证、分配和列表功能。
"""

import os
import shutil
import tempfile
import zipfile
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

from langchain_core.tools import tool

from app.log_utils import get_logger

logger = get_logger("skill_management")

# ============================================================
# 配置
# ============================================================

# 技能目录配置
SKILLS_BASE_DIR = Path(__file__).parent.parent.parent / "skills"

# Scope 映射（子智能体名称 -> 技能目录名）
SCOPE_MAPPING = {
    "trend-analyzer": "trend",
    "security-analyzer": "security",
    "community-analyzer": "community",
    "compliance-analyzer": "compliance",
    "main": "main",
}

# 安全扫描规则
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
    r"\byaml\.load\s*\([^)]*\)",
    r"\bshutil\.rmtree\s*\(",
]

SENSITIVE_FILES = [
    ".env", ".credentials", ".secrets",
    ".pem", ".key", ".p12",
    "id_rsa", "id_ed25519",
    "credentials.json", "service-account.json",
    ".netrc", "_netrc",
]

ALLOWED_DOMAINS = [
    "api.github.com",
    "dashscope.aliyuncs.com",
    "api.osv.dev",
    "pypi.org",
    "files.pythonhosted.org",
    "github.com",
    "raw.githubusercontent.com",
]


# ============================================================
# 工具函数
# ============================================================

@tool
async def download_skill(url: str) -> Dict[str, Any]:
    """
    从指定 URL 下载技能 ZIP 包。

    Args:
        url: 技能 ZIP 包的下载 URL

    Returns:
        {
            "success": bool,
            "skill_name": str,
            "skill_path": str,
            "message": str
        }
    """
    logger.info("download_skill_start", url=url)

    main_skills_dir = SKILLS_BASE_DIR / "main"
    main_skills_dir.mkdir(parents=True, exist_ok=True)

    # 创建临时目录
    temp_dir = tempfile.mkdtemp(prefix="skill_download_")

    try:
        # 1. 下载 ZIP
        filename = url.split("/")[-1]
        if not filename.endswith(".zip"):
            filename = "skill.zip"

        zip_path = Path(temp_dir) / filename

        request = Request(url, headers={"User-Agent": "OSINT-SkillManager/1.0"})
        response = urlopen(request, timeout=60)

        with open(zip_path, "wb") as f:
            f.write(response.read())

        logger.info("skill_zip_downloaded", zip_path=str(zip_path))

        # 2. 解压
        with zipfile.ZipFile(zip_path, "r") as zf:
            # 安全检查
            for name in zf.namelist():
                if ".." in name or name.startswith("/"):
                    return {
                        "success": False,
                        "message": f"Unsafe path in ZIP: {name}",
                    }

            files = zf.namelist()

            # 确定 skill 名称
            skill_name = zip_path.stem
            for f in files:
                if "/" in f:
                    potential_name = f.split("/")[0]
                    if potential_name and not potential_name.startswith("."):
                        skill_name = potential_name
                        break

            # 清理技能名称
            skill_name = re.sub(r"[^a-zA-Z0-9_-]", "-", skill_name).strip("-")[:50]
            if not skill_name:
                skill_name = "unnamed-skill"

            zf.extractall(temp_dir)

        # 3. 确定解压后的路径
        temp_skill_path = Path(temp_dir) / skill_name
        if not temp_skill_path.exists():
            # ZIP 可能没有根目录
            for item in Path(temp_dir).iterdir():
                if item.is_dir() and not item.name.startswith("."):
                    temp_skill_path = item
                    skill_name = item.name
                    break
            else:
                # 使用临时目录本身
                temp_skill_path = Path(temp_dir)

        # 4. 移动到最终目录
        final_path = main_skills_dir / skill_name
        if final_path.exists():
            shutil.rmtree(final_path)

        shutil.move(str(temp_skill_path), str(final_path))

        logger.info("skill_downloaded", skill_name=skill_name, path=str(final_path))

        return {
            "success": True,
            "skill_name": skill_name,
            "skill_path": str(final_path),
            "message": f"Skill '{skill_name}' downloaded successfully to {final_path}",
            "files": files,
        }

    except HTTPError as e:
        logger.error("download_http_error", code=e.code, reason=e.reason)
        return {
            "success": False,
            "message": f"HTTP error: {e.code} {e.reason}",
        }
    except URLError as e:
        logger.error("download_url_error", reason=e.reason)
        return {
            "success": False,
            "message": f"URL error: {e.reason}",
        }
    except zipfile.BadZipFile as e:
        logger.error("download_bad_zip", error=str(e))
        return {
            "success": False,
            "message": f"Invalid ZIP file: {e}",
        }
    except Exception as e:
        logger.error("download_error", error=str(e))
        return {
            "success": False,
            "message": str(e),
        }
    finally:
        # 清理临时目录
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass


@tool
async def scan_skill(skill_path: str) -> Dict[str, Any]:
    """
    扫描技能安全性。

    检查危险代码模式、敏感文件和非白名单网络连接。

    Args:
        skill_path: 技能目录路径

    Returns:
        {
            "safe": bool,
            "findings": List[Dict],
            "summary": Dict
        }
    """
    logger.info("scan_skill_start", skill_path=skill_path)

    skill_path = Path(skill_path)

    if not skill_path.exists():
        return {
            "safe": False,
            "findings": [{"error": f"Skill path not found: {skill_path}", "severity": "critical"}],
            "summary": {"total": 1, "critical": 1, "high": 0, "medium": 0},
        }

    all_findings = []

    # 1. 扫描敏感文件
    for root, dirs, files in os.walk(skill_path):
        for file in files:
            file_lower = file.lower()
            for sensitive in SENSITIVE_FILES:
                if sensitive.lower() in file_lower:
                    all_findings.append({
                        "file": os.path.join(root, file),
                        "type": "sensitive_file",
                        "pattern": sensitive,
                        "severity": "critical",
                    })

    # 2. 扫描代码文件
    for py_file in skill_path.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            lines = content.split("\n")

            for line_num, line in enumerate(lines, 1):
                # 检查危险模式
                for pattern in DANGEROUS_PATTERNS:
                    if re.search(pattern, line):
                        all_findings.append({
                            "file": str(py_file),
                            "line": line_num,
                            "pattern": pattern,
                            "content": line.strip()[:100],
                            "severity": "high",
                        })

                # 检查网络连接
                url_matches = re.findall(r'https?://([^/:"\s]+)', line)
                for domain in url_matches:
                    main_domain = domain.split(":")[0]
                    is_allowed = any(
                        main_domain == allowed or main_domain.endswith("." + allowed)
                        for allowed in ALLOWED_DOMAINS
                    )
                    if not is_allowed:
                        all_findings.append({
                            "file": str(py_file),
                            "line": line_num,
                            "domain": main_domain,
                            "severity": "medium",
                            "message": f"Network connection to non-whitelisted domain: {main_domain}",
                        })

        except Exception as e:
            all_findings.append({
                "file": str(py_file),
                "error": str(e),
                "severity": "error",
            })

    # 3. 扫描 shell 脚本
    for sh_file in skill_path.rglob("*.sh"):
        try:
            content = sh_file.read_text(encoding="utf-8", errors="ignore")
            lines = content.split("\n")

            for line_num, line in enumerate(lines, 1):
                for pattern in DANGEROUS_PATTERNS:
                    if re.search(pattern, line):
                        all_findings.append({
                            "file": str(sh_file),
                            "line": line_num,
                            "pattern": pattern,
                            "content": line.strip()[:100],
                            "severity": "high",
                        })
        except Exception as e:
            all_findings.append({
                "file": str(sh_file),
                "error": str(e),
                "severity": "error",
            })

    # 统计
    summary = {
        "total": len(all_findings),
        "critical": sum(1 for f in all_findings if f.get("severity") == "critical"),
        "high": sum(1 for f in all_findings if f.get("severity") == "high"),
        "medium": sum(1 for f in all_findings if f.get("severity") == "medium"),
    }

    is_safe = summary["critical"] == 0 and summary["high"] == 0

    logger.info("scan_skill_complete", safe=is_safe, summary=summary)

    return {
        "safe": is_safe,
        "findings": all_findings,
        "summary": summary,
    }


@tool
async def validate_skill(skill_path: str) -> Dict[str, Any]:
    """
    验证技能可用性。

    检查 SKILL.md 格式、依赖和脚本语法。

    Args:
        skill_path: 技能目录路径

    Returns:
        {
            "valid": bool,
            "findings": List[Dict],
            "summary": Dict,
            "frontmatter": Dict (if parsed)
        }
    """
    logger.info("validate_skill_start", skill_path=skill_path)

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
    skill_md_path = skill_path / "SKILL.md"
    if not skill_md_path.exists():
        all_findings.append({
            "error": "SKILL.md not found",
            "severity": "critical",
        })
    else:
        try:
            content = skill_md_path.read_text(encoding="utf-8")

            # 解析 frontmatter
            pattern = r"^---\s*\n(.*?)\n---\s*\n(.*)$"
            match = re.match(pattern, content, re.DOTALL)

            if not match:
                all_findings.append({
                    "error": "Invalid frontmatter format",
                    "severity": "critical",
                    "file": str(skill_md_path),
                })
            else:
                frontmatter_str = match.group(1)

                # 简单解析 YAML
                frontmatter = {}
                current_list = None

                for line in frontmatter_str.split("\n"):
                    stripped = line.strip()
                    if not stripped:
                        continue

                    if stripped.startswith("- ") and current_list is not None:
                        current_list.append(stripped[2:].strip("\"'"))
                        continue

                    if ":" in line and not line.startswith(" "):
                        key, _, value = line.partition(":")
                        key = key.strip()
                        value = value.strip().strip("\"'")

                        if value == "":
                            if key == "dependencies":
                                current_list = []
                                frontmatter[key] = current_list
                            else:
                                frontmatter[key] = {}
                                current_list = None
                        else:
                            frontmatter[key] = value
                            current_list = None

                # 检查必需字段
                required_fields = ["name", "description"]
                for field in required_fields:
                    if field not in frontmatter:
                        all_findings.append({
                            "error": f"Missing required field: {field}",
                            "severity": "high",
                            "file": str(skill_md_path),
                        })

                # 检查版本格式
                version = frontmatter.get("version", "")
                if version and not re.match(r"^\d+\.\d+\.\d+$", str(version)):
                    all_findings.append({
                        "warning": f"Invalid version format: {version}",
                        "severity": "low",
                        "file": str(skill_md_path),
                    })

        except Exception as e:
            all_findings.append({
                "error": f"Failed to parse SKILL.md: {e}",
                "severity": "high",
                "file": str(skill_md_path),
            })

    # 2. 验证脚本目录（可选）
    scripts_path = skill_path / "scripts"
    if scripts_path.exists():
        for script in scripts_path.glob("*.py"):
            # 基本语法检查（尝试编译）
            try:
                code = script.read_text(encoding="utf-8")
                compile(code, str(script), "exec")
            except SyntaxError as e:
                all_findings.append({
                    "error": f"Syntax error in {script.name}: line {e.lineno}",
                    "severity": "high",
                    "file": str(script),
                })

    # 统计
    summary = {
        "total": len(all_findings),
        "critical": sum(1 for f in all_findings if f.get("severity") == "critical"),
        "high": sum(1 for f in all_findings if f.get("severity") == "high"),
        "medium": sum(1 for f in all_findings if f.get("severity") == "medium"),
        "low": sum(1 for f in all_findings if f.get("severity") == "low"),
    }

    is_valid = summary["critical"] == 0 and summary["high"] == 0

    logger.info("validate_skill_complete", valid=is_valid, summary=summary)

    return {
        "valid": is_valid,
        "findings": all_findings,
        "summary": summary,
        "frontmatter": frontmatter,
    }


@tool
async def assign_skill(skill_name: str, subagent_name: str) -> Dict[str, Any]:
    """
    将技能分配给子智能体。

    从 skills/main/ 复制技能到对应的子智能体技能目录。

    Args:
        skill_name: 技能名称
        subagent_name: 子智能体名称（如 trend-analyzer, security-analyzer）

    Returns:
        {
            "success": bool,
            "message": str,
            "source_path": str,
            "target_path": str
        }
    """
    logger.info("assign_skill_start", skill_name=skill_name, subagent_name=subagent_name)

    # 确定 scope 目录
    scope_dir = SCOPE_MAPPING.get(subagent_name)
    if not scope_dir:
        return {
            "success": False,
            "message": f"Unknown subagent: {subagent_name}. Valid options: {list(SCOPE_MAPPING.keys())}",
        }

    # 源路径
    source_path = SKILLS_BASE_DIR / "main" / skill_name
    if not source_path.exists():
        return {
            "success": False,
            "message": f"Skill not found in main directory: {skill_name}",
        }

    # 目标路径
    target_dir = SKILLS_BASE_DIR / scope_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / skill_name

    # 复制
    try:
        if target_path.exists():
            shutil.rmtree(target_path)

        shutil.copytree(source_path, target_path)

        logger.info("skill_assigned", skill_name=skill_name, subagent=subagent_name, target=str(target_path))

        return {
            "success": True,
            "message": f"Skill '{skill_name}' assigned to {subagent_name}",
            "source_path": str(source_path),
            "target_path": str(target_path),
        }

    except Exception as e:
        logger.error("assign_skill_error", error=str(e))
        return {
            "success": False,
            "message": str(e),
        }


@tool
async def list_skills(location: str = "all") -> Dict[str, Any]:
    """
    列出可用技能。

    Args:
        location: 技能位置（"all", "main", "trend", "security", "community", "compliance"）

    Returns:
        {
            "skills": Dict[str, List[Dict]],
            "total": int
        }
    """
    logger.info("list_skills_start", location=location)

    result = {"skills": {}, "total": 0}

    def scan_skill_dir(skill_dir: Path) -> List[Dict]:
        """扫描技能目录，返回技能列表。"""
        skills = []
        if not skill_dir.exists():
            return skills

        for skill_path in skill_dir.iterdir():
            if not skill_path.is_dir():
                continue
            if skill_path.name.startswith("."):
                continue

            skill_info = {"name": skill_path.name, "path": str(skill_path)}

            # 读取 SKILL.md 获取元数据
            skill_md = skill_path / "SKILL.md"
            if skill_md.exists():
                try:
                    content = skill_md.read_text(encoding="utf-8")
                    # 解析 frontmatter
                    pattern = r"^---\s*\n(.*?)\n---\s*\n(.*)$"
                    match = re.match(pattern, content, re.DOTALL)
                    if match:
                        frontmatter_str = match.group(1)
                        for line in frontmatter_str.split("\n"):
                            if ":" in line and not line.startswith(" "):
                                key, _, value = line.partition(":")
                                key = key.strip()
                                value = value.strip().strip("\"'")
                                if key in ["name", "description", "version", "author"]:
                                    skill_info[key] = value
                except Exception:
                    pass

            # 检查是否有脚本
            scripts_dir = skill_path / "scripts"
            if scripts_dir.exists():
                skill_info["scripts"] = [s.name for s in scripts_dir.glob("*.py")]

            skills.append(skill_info)

        return skills

    if location == "all":
        for scope_name, scope_dir in SCOPE_MAPPING.items():
            skill_dir = SKILLS_BASE_DIR / scope_dir
            skills = scan_skill_dir(skill_dir)
            result["skills"][scope_name] = skills
            result["total"] += len(skills)
    else:
        scope_dir = SCOPE_MAPPING.get(location, location)
        skill_dir = SKILLS_BASE_DIR / scope_dir
        skills = scan_skill_dir(skill_dir)
        result["skills"][location] = skills
        result["total"] = len(skills)

    logger.info("list_skills_complete", total=result["total"])

    return result


@tool
async def remove_skill(skill_name: str, location: str = "all") -> Dict[str, Any]:
    """
    移除技能。

    Args:
        skill_name: 技能名称
        location: 技能位置（"all", "main", "trend", "security", "community", "compliance"）

    Returns:
        {
            "success": bool,
            "message": str,
            "removed_paths": List[str]
        }
    """
    logger.info("remove_skill_start", skill_name=skill_name, location=location)

    removed_paths = []

    def remove_from_scope(scope_name: str) -> bool:
        """从指定 scope 移除技能。"""
        scope_dir = SCOPE_MAPPING.get(scope_name, scope_name)
        skill_path = SKILLS_BASE_DIR / scope_dir / skill_name

        if skill_path.exists():
            try:
                shutil.rmtree(skill_path)
                removed_paths.append(str(skill_path))
                return True
            except Exception as e:
                logger.error("remove_skill_error", path=str(skill_path), error=str(e))
                return False
        return True

    if location == "all":
        for scope_name in SCOPE_MAPPING.keys():
            remove_from_scope(scope_name)
    else:
        remove_from_scope(location)

    if removed_paths:
        logger.info("skill_removed", skill_name=skill_name, paths=removed_paths)
        return {
            "success": True,
            "message": f"Skill '{skill_name}' removed from {len(removed_paths)} location(s)",
            "removed_paths": removed_paths,
        }
    else:
        return {
            "success": False,
            "message": f"Skill '{skill_name}' not found in any location",
            "removed_paths": [],
        }


# 导出分组
skill_tools = [
    download_skill,
    scan_skill,
    validate_skill,
    assign_skill,
    list_skills,
    remove_skill,
]