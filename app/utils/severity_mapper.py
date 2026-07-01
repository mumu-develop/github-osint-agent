"""严重程度映射工具 - 统一的漏洞严重程度评估。

支持多种来源的严重程度评估:
- OSV.dev CVSS 分数
- CVSS 向量字符串
- 自定义评分规则
"""

import re
from typing import Dict, List, Optional, Any
from app.log_utils import get_logger

logger = get_logger("severity_mapper")


class SeverityMapper:
    """严重程度映射器 - 将各种评分系统映射到统一等级。"""

    # 系统内部使用的严重程度等级
    LEVELS = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]

    # CVSS 分数阈值
    CVSS_THRESHOLDS = {
        "CRITICAL": 9.0,
        "HIGH": 7.0,
        "MEDIUM": 4.0,
        "LOW": 1.0,
    }

    # 漏洞类型风险等级（用于无 CVSS 时的评估）
    RISK_TYPE_LEVELS = {
        "远程代码执行": "CRITICAL",
        "注入漏洞": "HIGH",
        "权限提升": "HIGH",
        "认证绕过": "HIGH",
        "拒绝服务": "MEDIUM",
        "信息泄露": "MEDIUM",
        "加密漏洞": "MEDIUM",
        "路径遍历": "MEDIUM",
        "反序列化": "HIGH",
        "供应链攻击": "HIGH",
        "高危漏洞": "HIGH",
        "安全漏洞": "MEDIUM",
    }

    @staticmethod
    def from_cvss_score(score: float) -> str:
        """根据 CVSS 分数确定严重程度。

        Args:
            score: CVSS 分数 (0-10)

        Returns:
            严重程度等级 (CRITICAL|HIGH|MEDIUM|LOW|INFO)
        """
        if score >= SeverityMapper.CVSS_THRESHOLDS["CRITICAL"]:
            return "CRITICAL"
        elif score >= SeverityMapper.CVSS_THRESHOLDS["HIGH"]:
            return "HIGH"
        elif score >= SeverityMapper.CVSS_THRESHOLDS["MEDIUM"]:
            return "MEDIUM"
        elif score >= SeverityMapper.CVSS_THRESHOLDS["LOW"]:
            return "LOW"
        else:
            return "INFO"

    @staticmethod
    def from_cvss_vector(vector: str) -> float:
        """解析 CVSS 向量字符串，提取分数。

        CVSS 向量格式: CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H

        Args:
            vector: CVSS 向量字符串

        Returns:
            CVSS 分数，无法解析时返回 0.0
        """
        if not vector:
            return 0.0

        # 尝试从向量中提取分数
        # 有些向量包含分数: CVSS:3.1/AV:N/.../C:H/I:H/A:H (score: 9.8)
        match = re.search(r"score:\s*([0-9.]+)", vector)
        if match:
            return float(match.group(1))

        # 射击简化估算 - 根据影响指标
        # C:H/I:H/A:H 通常对应高分
        impact_match = re.findall(r"/(C|I|A):(H|L|N)", vector)
        if impact_match:
            high_count = sum(1 for _, level in impact_match if level == "H")
            if high_count == 3:
                return 9.0  # 全高危
            elif high_count >= 2:
                return 7.5  # 两高危
            elif high_count == 1:
                return 5.0  # 一高危

        return 0.0

    @staticmethod
    def from_osv(vuln: Dict) -> str:
        """从 OSV 漏洞数据提取严重程度。

        Args:
            vuln: OSV 漏洞数据

        Returns:
            严重程度等级
        """
        severity_list = vuln.get("severity", [])

        for s in severity_list:
            if s.get("type") == "CVSS":
                score = s.get("score", 0)

                # 数字分数
                if isinstance(score, (int, float)):
                    return SeverityMapper.from_cvss_score(float(score))

                # CVSS 向量字符串
                if isinstance(score, str):
                    parsed_score = SeverityMapper.from_cvss_vector(score)
                    if parsed_score > 0:
                        return SeverityMapper.from_cvss_score(parsed_score)

        # 无 CVSS 时，根据影响范围推断
        affected = vuln.get("affected", [])
        if len(affected) > 10:
            return "HIGH"  # 影响多个包
        elif len(affected) > 5:
            return "MEDIUM"

        # 根据漏洞类型推断
        summary = vuln.get("summary", "").lower()
        details = vuln.get("details", "").lower()
        aliases = vuln.get("aliases", [])
        text = f"{summary} {details}"

        for risk_type, level in SeverityMapper.RISK_TYPE_LEVELS.items():
            if risk_type.lower() in text:
                return level

        # 检查是否是知名高危漏洞
        known_critical = ["log4j", "heartbleed", "shellshock", "struts2", "spring4shell"]
        for kc in known_critical:
            if kc in text or any(kc in a.lower() for a in aliases):
                return "CRITICAL"

        return "MEDIUM"

    @staticmethod
    def from_secret_type(secret_type: str, context: Dict = None) -> str:
        """根据敏感信息类型确定严重程度。

        Args:
            secret_type: 敏感信息类型 (aws_access_key, github_token 等)
            context: 上下文信息 (file, has_example_keyword 等)

        Returns:
            严重程度等级
        """
        # 高危类型
        critical_types = ["private_key", "aws_secret_key"]
        high_types = ["aws_access_key", "github_token", "jwt_secret", "api_key"]

        if secret_type in critical_types:
            # 检查上下文是否是示例
            if context:
                if context.get("is_example") or context.get("is_doc_file"):
                    return "INFO"
                if context.get("has_example_keyword"):
                    return "MEDIUM"
            return "CRITICAL"

        if secret_type in high_types:
            if context:
                if context.get("is_example") or context.get("is_doc_file"):
                    return "INFO"
                if context.get("has_example_keyword"):
                    return "MEDIUM"
            return "HIGH"

        return "MEDIUM"

    @staticmethod
    def get_cvss_score(vuln: Dict) -> float:
        """从漏洞数据提取 CVSS 分数。

        Args:
            vuln: 漏洞数据 (OSV 格式)

        Returns:
            CVSS 分数，无数据时返回 0.0
        """
        severity_list = vuln.get("severity", [])

        for s in severity_list:
            if s.get("type") == "CVSS":
                score = s.get("score", 0)
                if isinstance(score, (int, float)):
                    return float(score)
                if isinstance(score, str):
                    return SeverityMapper.from_cvss_vector(score)

        return 0.0

    @staticmethod
    def get_risk_type(vuln: Dict) -> str:
        """根据漏洞特征判断风险类型。

        Args:
            vuln: 漏洞数据

        Returns:
            风险类型描述
        """
        summary = vuln.get("summary", "").lower()
        details = vuln.get("details", "").lower()
        aliases = vuln.get("aliases", [])
        id_lower = vuln.get("id", "").lower()

        text = f"{summary} {details} {id_lower}"

        # 检查风险类型关键词
        for risk_type, keywords in {
            "远程代码执行": ["rce", "remote code execution", "code execution", "arbitrary code"],
            "注入漏洞": ["injection", "sql injection", "command injection", "xss", "ssrf"],
            "拒绝服务": ["dos", "denial of service", "memory exhaustion"],
            "信息泄露": ["information disclosure", "data leak", "sensitive data"],
            "权限提升": ["privilege escalation", "elevation"],
            "加密漏洞": ["crypto", "encryption", "tls", "ssl"],
            "路径遍历": ["path traversal", "directory traversal"],
            "反序列化": ["deserialization", "deserialize"],
            "认证绕过": ["authentication", "auth bypass", "bypass authentication"],
            "供应链攻击": ["supply chain", "dependency confusion"],
        }.items():
            for kw in keywords:
                if kw in text:
                    return risk_type

        # 检查知名漏洞
        known_critical = ["log4j", "heartbleed", "shellshock", "struts2", "spring4shell"]
        for kc in known_critical:
            if kc in text or any(kc in a.lower() for a in aliases):
                return "高危漏洞"

        return "安全漏洞"


# 便捷函数
def map_osv_severity(vuln: Dict) -> str:
    """映射 OSV 严重程度（便捷函数）。"""
    return SeverityMapper.from_osv(vuln)


def get_cvss_score(vuln: Dict) -> float:
    """获取 CVSS 分数（便捷函数）。"""
    return SeverityMapper.get_cvss_score(vuln)


def get_risk_type(vuln: Dict) -> str:
    """获取风险类型（便捷函数）。"""
    return SeverityMapper.get_risk_type(vuln)