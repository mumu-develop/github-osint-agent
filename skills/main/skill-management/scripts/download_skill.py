"""
技能下载脚本。

从指定 URL 下载技能 ZIP 包并解压。
"""

import os
import re
import sys
import json
import tempfile
import zipfile
import shutil
from pathlib import Path
from typing import Dict, Any
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError


def download_skill_zip(url: str, dest_dir: str = None) -> Dict[str, Any]:
    """
    从 URL 下载技能 ZIP 包。

    Args:
        url: 技能 ZIP 包的下载 URL
        dest_dir: 目标目录，默认为临时目录

    Returns:
        {
            "success": bool,
            "zip_path": str,
            "error": str (if failed)
        }
    """
    if dest_dir is None:
        dest_dir = tempfile.mkdtemp(prefix="skill_download_")

    dest_path = Path(dest_dir)
    dest_path.mkdir(parents=True, exist_ok=True)

    # 从 URL 提取文件名
    filename = url.split("/")[-1]
    if not filename.endswith(".zip"):
        filename = "skill.zip"

    zip_path = dest_path / filename

    try:
        request = Request(url, headers={"User-Agent": "OSINT-SkillManager/1.0"})
        response = urlopen(request, timeout=60)

        with open(zip_path, "wb") as f:
            f.write(response.read())

        return {
            "success": True,
            "zip_path": str(zip_path),
            "dest_dir": str(dest_path),
        }

    except HTTPError as e:
        return {
            "success": False,
            "error": f"HTTP error: {e.code} {e.reason}",
        }
    except URLError as e:
        return {
            "success": False,
            "error": f"URL error: {e.reason}",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def extract_skill_zip(zip_path: str, dest_dir: str = None) -> Dict[str, Any]:
    """
    解压技能 ZIP 包。

    Args:
        zip_path: ZIP 文件路径
        dest_dir: 解压目标目录

    Returns:
        {
            "success": bool,
            "skill_path": str,
            "skill_name": str,
            "files": List[str],
            "error": str (if failed)
        }
    """
    zip_path = Path(zip_path)

    if not zip_path.exists():
        return {
            "success": False,
            "error": f"ZIP file not found: {zip_path}",
        }

    if dest_dir is None:
        dest_dir = zip_path.parent

    dest_path = Path(dest_dir)

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            # 检查 ZIP 文件安全性
            for name in zf.namelist():
                # 防止路径遍历攻击
                if ".." in name or name.startswith("/"):
                    return {
                        "success": False,
                        "error": f"Unsafe path in ZIP: {name}",
                    }

            # 获取文件列表
            files = zf.namelist()

            # 确定 skill 名称（从第一个目录或 ZIP 文件名）
            skill_name = zip_path.stem
            for f in files:
                if "/" in f:
                    potential_name = f.split("/")[0]
                    if potential_name and not potential_name.startswith("."):
                        skill_name = potential_name
                        break

            # 解压
            zf.extractall(dest_path)

            # 确定 skill 路径
            skill_path = dest_path / skill_name
            if not skill_path.exists():
                # 可能 ZIP 没有根目录
                skill_path = dest_path

            return {
                "success": True,
                "skill_path": str(skill_path),
                "skill_name": skill_name,
                "files": files,
            }

    except zipfile.BadZipFile as e:
        return {
            "success": False,
            "error": f"Invalid ZIP file: {e}",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def sanitize_skill_name(name: str) -> str:
    """清理技能名称，确保安全。"""
    # 只保留字母、数字、下划线和连字符
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "-", name)
    # 移除首尾的连字符
    sanitized = sanitized.strip("-")
    # 限制长度
    return sanitized[:50] if sanitized else "unnamed-skill"


def download_skill(url: str, skills_dir: str = None) -> Dict[str, Any]:
    """
    下载技能的完整流程。

    Args:
        url: 技能 ZIP 包的下载 URL
        skills_dir: 技能目录，默认为 ./skills/main/

    Returns:
        {
            "success": bool,
            "skill_name": str,
            "skill_path": str,
            "error": str (if failed)
        }
    """
    if skills_dir is None:
        skills_dir = Path(__file__).parent.parent.parent.parent / "main"
    else:
        skills_dir = Path(skills_dir)

    # 1. 下载 ZIP
    download_result = download_skill_zip(url)
    if not download_result["success"]:
        return download_result

    zip_path = download_result["zip_path"]
    temp_dir = download_result["dest_dir"]

    try:
        # 2. 解压到临时目录
        extract_result = extract_skill_zip(zip_path)
        if not extract_result["success"]:
            return extract_result

        temp_skill_path = Path(extract_result["skill_path"])
        skill_name = sanitize_skill_name(extract_result["skill_name"])

        # 3. 移动到技能目录
        final_path = skills_dir / skill_name

        if final_path.exists():
            shutil.rmtree(final_path)

        shutil.move(str(temp_skill_path), str(final_path))

        return {
            "success": True,
            "skill_name": skill_name,
            "skill_path": str(final_path),
            "files": extract_result["files"],
        }

    finally:
        # 清理临时目录
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python download_skill.py <url> [skills_dir]")
        sys.exit(1)

    url = sys.argv[1]
    skills_dir = sys.argv[2] if len(sys.argv) > 2 else None

    result = download_skill(url, skills_dir)
    print(json.dumps(result, indent=2, ensure_ascii=False))