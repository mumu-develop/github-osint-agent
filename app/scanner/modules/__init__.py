"""扫描模块目录 - 可配置化的独立扫描模块。

所有模块统一接口：scan(repo_obj) -> List[Finding]
"""

from app.scanner.modules.cve_scanner import CVEScanner
from app.scanner.modules.license_scanner import LicenseScanner
from app.scanner.modules.community_scanner import CommunityScanner
from app.scanner.modules.llm_analyzer import LLMAnalyzer

__all__ = [
    "CVEScanner",
    "LicenseScanner",
    "CommunityScanner",
    "LLMAnalyzer"
]