"""依赖文件解析模块 - 统一的依赖解析工具。

支持多种依赖文件格式:
- requirements.txt (Python/PyPI)
- package.json (Node.js/npm)
- pom.xml (Java/Maven)
- go.mod (Go)
- Cargo.toml (Rust) - 待实现
"""

import re
import json
from typing import Dict, List, Optional, Tuple


class DependencyParser:
    """依赖文件解析器 - 支持多种格式。"""

    # 依赖文件类型映射
    FILE_TYPES = {
        "requirements.txt": {"ecosystem": "PyPI", "language": "Python"},
        "package.json": {"ecosystem": "npm", "language": "Node.js"},
        "pom.xml": {"ecosystem": "Maven", "language": "Java"},
        "go.mod": {"ecosystem": "Go", "language": "Go"},
        "Cargo.toml": {"ecosystem": "crates.io", "language": "Rust"},
    }

    @staticmethod
    def parse(filename: str, content: str) -> List[Dict]:
        """解析依赖文件内容。

        Args:
            filename: 文件名 (requirements.txt, package.json 等)
            content: 文件内容

        Returns:
            依赖列表 [{"name": "xxx", "version": "yyy"}, ...]
        """
        if filename == "requirements.txt":
            return DependencyParser.parse_requirements(content)
        elif filename == "package.json":
            return DependencyParser.parse_package_json(content)
        elif filename == "pom.xml":
            return DependencyParser.parse_pom_xml(content)
        elif filename == "go.mod":
            return DependencyParser.parse_go_mod(content)
        elif filename == "Cargo.toml":
            return DependencyParser.parse_cargo_toml(content)
        else:
            return []

    @staticmethod
    def parse_requirements(content: str) -> List[Dict]:
        """解析 requirements.txt 文件。

        支持格式:
        - package==1.0.0
        - package>=1.0.0
        - package~=1.0.0
        - package (无版本)
        """
        deps = []
        for line in content.strip().split("\n"):
            line = line.strip()
            # 跳过空行和注释
            if not line or line.startswith("#"):
                continue
            # 跳过环境变量引用和特殊指令
            if line.startswith("-") or line.startswith("--") or "${" in line:
                continue

            # 匹配版本约束
            match = re.match(r"^([a-zA-Z0-9_.-]+)[=<>~!]+([0-9.]+)", line)
            if match:
                deps.append({"name": match.group(1), "version": match.group(2)})
            elif re.match(r"^([a-zA-Z0-9_.-]+)$", line):
                # 无版本约束
                deps.append({"name": line, "version": None})

        return deps

    @staticmethod
    def parse_package_json(content: str) -> List[Dict]:
        """解析 package.json 文件。

        支持 dependencies 和 devDependencies。
        """
        deps = []
        try:
            data = json.loads(content)
            for section in ["dependencies", "devDependencies", "peerDependencies", "optionalDependencies"]:
                if section in data:
                    for name, version in data[section].items():
                        # 清理版本号前缀 (^, ~, >=, @ 等)
                        clean_version = None
                        if version:
                            clean_version = re.sub(r"^[^0-9]+", "", version)
                            if not clean_version or clean_version == version:
                                clean_version = version.lstrip("^~>=<")
                        deps.append({"name": name, "version": clean_version})
        except json.JSONDecodeError:
            pass
        return deps

    @staticmethod
    def parse_pom_xml(content: str) -> List[Dict]:
        """解析 pom.xml 文件。

        支持 Maven 属性变量替换 (${variable.name})。
        """
        deps = []

        # 1. 先解析 properties 获取变量定义
        properties = {}
        props_pattern = r"<properties>.*?</properties>"
        props_match = re.search(props_pattern, content, re.DOTALL)
        if props_match:
            props_content = props_match.group(0)
            # 解析每个 property
            prop_pattern = r"<([a-zA-Z0-9_.-]+)>([^<]+)</([a-zA-Z0-9_.-]+)>"
            for match in re.finditer(prop_pattern, props_content):
                prop_name = match.group(1)
                prop_value = match.group(2)
                properties[prop_name] = prop_value

        # 2. 解析 dependency 节点
        pattern = r"<dependency>.*?<groupId>([^<]+)</groupId>.*?<artifactId>([^<]+)</artifactId>.*?(?:<version>([^<]+)</version>)?.*?</dependency>"
        for match in re.finditer(pattern, content, re.DOTALL):
            group_id = match.group(1)
            artifact_id = match.group(2)
            version = match.group(3) if match.group(3) else None

            # 3. 替换版本号中的变量 ${xxx}
            if version and "${" in version:
                # 提取变量名
                var_match = re.findall(r"\$\{([^}]+)\}", version)
                for var_name in var_match:
                    if var_name in properties:
                        version = version.replace(f"${{{var_name}}}", properties[var_name])
                    else:
                        # 变量未定义，标记为未知
                        version = version.replace(f"${{{var_name}}}", "unknown")

            # 跳过空版本或占位符版本
            if version and version != "unknown" and not version.startswith("${"):
                deps.append({
                    "name": f"{group_id}:{artifact_id}",
                    "version": version,
                    "group_id": group_id,
                    "artifact_id": artifact_id
                })
            elif version == "unknown" or (version and "${" in version):
                # 记录无法解析的依赖，标记版本为 unknown
                deps.append({
                    "name": f"{group_id}:{artifact_id}",
                    "version": "unknown",
                    "group_id": group_id,
                    "artifact_id": artifact_id,
                    "raw_version": match.group(3) if match.group(3) else None
                })

        return deps

    @staticmethod
    def parse_go_mod(content: str) -> List[Dict]:
        """解析 go.mod 文件。

        支持 require 语句和间接依赖。
        """
        deps = []

        # 匹配 require 块或单行 require
        # require (
        #   github.com/foo/bar v1.0.0
        # )
        # 或 require github.com/foo/bar v1.0.0

        in_require_block = False
        for line in content.strip().split("\n"):
            line = line.strip()

            if line == "require (":
                in_require_block = True
                continue
            elif line == ")" and in_require_block:
                in_require_block = False
                continue

            if in_require_block or line.startswith("require "):
                # 移除 require 关键字
                if line.startswith("require "):
                    line = line[8:].strip()

                # 匹配 package version
                match = re.match(r"^([a-zA-Z0-9./_-]+)\s+v?([0-9.]+)", line)
                if match:
                    name = match.group(1)
                    # 跳过 module 和 go 关键字
                    if name not in ["module", "go"]:
                        deps.append({"name": name, "version": match.group(2)})

        return deps

    @staticmethod
    def parse_cargo_toml(content: str) -> List[Dict]:
        """解析 Cargo.toml 文件 (Rust)。

        待实现 - 需要解析 TOML 格式。
        """
        deps = []
        try:
            import tomllib  # Python 3.11+
            data = tomllib.loads(content)
            for section in ["dependencies", "dev-dependencies"]:
                if section in data:
                    for name, version in data[section].items():
                        if isinstance(version, str):
                            deps.append({"name": name, "version": version})
                        elif isinstance(version, dict) and "version" in version:
                            deps.append({"name": name, "version": version["version"]})
        except ImportError:
            # Python 3.10 及以下，使用正则
            pattern = r'^([a-zA-Z0-9_-]+)\s*=\s*["\']?([0-9.]+)["\']?'
            for match in re.finditer(pattern, content, re.MULTILINE):
                deps.append({"name": match.group(1), "version": match.group(2)})
        return deps

    @staticmethod
    def get_ecosystem(filename: str) -> Optional[str]:
        """获取依赖文件对应的生态系统。"""
        return DependencyParser.FILE_TYPES.get(filename, {}).get("ecosystem")

    @staticmethod
    def get_language(filename: str) -> Optional[str]:
        """获取依赖文件对应的语言。"""
        return DependencyParser.FILE_TYPES.get(filename, {}).get("language")


# 便捷函数
def parse_dependencies(filename: str, content: str) -> List[Dict]:
    """解析依赖文件（便捷函数）。"""
    return DependencyParser.parse(filename, content)


def get_dep_ecosystem(filename: str) -> Optional[str]:
    """获取生态系统（便捷函数）。"""
    return DependencyParser.get_ecosystem(filename)