"""扫描器模块 - 提供多种扫描器实现。

扫描器层级:
- BaseScanner: 抽象基类，定义统一接口
- LightScanner: L1 轻量扫描器（纯API，无LLM）
- HybridScanner: 混合扫描器（批量工具 + Agent分析）
- ConfigurableScanner: 可配置扫描器（动态组合模块）

扫描类型:
- L1_LIGHT: 轻量快速扫描
- L2_STANDARD: 标准扫描
- L3_DEEP: 深度扫描（含LLM分析）
"""
from typing import Dict

from app.scanner.base_scanner import BaseScanner
from app.scanner.light_scanner import LightScanner
from app.scanner.hybrid_scanner import HybridScanner
from app.scanner.configurable_scanner import ConfigurableScanner
from app.scanner.batch_tools import BatchScanTools

__all__ = [
    "BaseScanner",
    "LightScanner",
    "HybridScanner",
    "ConfigurableScanner",
    "BatchScanTools"
]

# 扫描模式映射
SCAN_MODES = {
    "fast": {"scanner": "BatchScanTools", "llm": False},
    "balanced": {"scanner": "HybridScanner", "llm": True, "high_risk_only": True},
    "deep": {"scanner": "HybridScanner", "llm": True, "high_risk_only": False},
}

# 扫描类型映射（兼容旧接口）
SCANNER_TYPES = {
    "L1_LIGHT": LightScanner,
    "L2_STANDARD": HybridScanner,
    "L3_DEEP": HybridScanner,
    "MANUAL": LightScanner,
    "HYBRID_FAST": HybridScanner,
    "HYBRID_BALANCED": HybridScanner,
    "HYBRID_DEEP": HybridScanner,
}


def get_scanner(scan_type: str, **kwargs):
    """根据扫描类型获取扫描器实例。

    Args:
        scan_type: 扫描类型 (L1_LIGHT, L2_STANDARD, L3_DEEP, MANUAL)
        **kwargs: 扫描器参数 (github_token, dimensions, scan_mode 等)

    Returns:
        扫描器实例
    """
    scanner_cls = SCANNER_TYPES.get(scan_type, LightScanner)

    # HybridScanner 需要 scan_mode 参数
    if scanner_cls == HybridScanner:
        if scan_type == "L1_LIGHT":
            kwargs["scan_mode"] = "fast"
        elif scan_type == "L2_STANDARD":
            kwargs["scan_mode"] = "balanced"
        elif scan_type == "L3_DEEP":
            kwargs["scan_mode"] = "deep"

    return scanner_cls(**kwargs)


def create_scanner_from_config(dimensions: Dict[str, bool],
                                llm_enabled: bool = False,
                                github_token: str = None,
                                scan_mode: str = "balanced") -> BaseScanner:
    """根据配置创建合适的扫描器。

    Args:
        dimensions: 扫描维度配置
        llm_enabled: 是否启用LLM分析
        github_token: GitHub token
        scan_mode: 扫描模式 (fast/balanced/deep)

    Returns:
        扫描器实例
    """
    if scan_mode == "fast" or not llm_enabled:
        return LightScanner(github_token=github_token, dimensions=dimensions)
    else:
        return HybridScanner(
            dimensions=dimensions,
            scan_mode=scan_mode,
            github_token=github_token,
            llm_enabled=llm_enabled
        )