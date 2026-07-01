"""扫描器配置模块 - 从环境变量加载配置参数。"""

import os
from typing import Dict, Any


class ScanConfig:
    """扫描器配置类。

    所有配置参数从环境变量读取，支持 .env 文件配置。
    """

    # ==================== 超时配置 ====================

    @staticmethod
    def get_subtask_timeout() -> int:
        """单个子任务最大执行时间（秒）。"""
        return int(os.getenv("SCAN_SUBTASK_TIMEOUT", "60"))

    @staticmethod
    def get_github_api_timeout() -> int:
        """GitHub API 单次调用超时（秒）。"""
        return int(os.getenv("SCAN_GITHUB_API_TIMEOUT", "30"))

    @staticmethod
    def get_osv_api_timeout() -> int:
        """OSV.dev API 调用超时（秒）。"""
        return int(os.getenv("SCAN_OSV_API_TIMEOUT", "15"))

    # ==================== 重试配置 ====================

    @staticmethod
    def get_max_retries() -> int:
        """失败重试次数。"""
        return int(os.getenv("SCAN_MAX_RETRIES", "1"))

    @staticmethod
    def get_retry_delay() -> int:
        """重试前等待时间（秒）。"""
        return int(os.getenv("SCAN_RETRY_DELAY", "5"))

    # ==================== 失败控制 ====================

    @staticmethod
    def get_failure_threshold() -> float:
        """失败率阈值（超过此比例终止整个扫描）。"""
        return float(os.getenv("SCAN_FAILURE_THRESHOLD", "0.3"))

    # ==================== 并发控制 ====================

    @staticmethod
    def get_max_concurrency() -> int:
        """最大同时扫描仓库数。"""
        return int(os.getenv("SCAN_MAX_CONCURRENCY", "20"))

    @staticmethod
    def get_progress_check_interval() -> float:
        """扫描进度检查频率（秒）。"""
        return float(os.getenv("SCAN_PROGRESS_CHECK_INTERVAL", "1.0"))

    # ==================== 批量工具配置 ====================

    @staticmethod
    def get_batch_concurrency() -> int:
        """批量工具并发数（默认50，用于无LLM的快速扫描）。"""
        return int(os.getenv("SCAN_BATCH_CONCURRENCY", "50"))

    # ==================== GitHub Token ====================

    @staticmethod
    def get_github_token() -> str:
        """GitHub API Token。"""
        return os.getenv("GITHUB_TOKEN", "")

    # ==================== 速率限制配置 ====================

    @staticmethod
    def get_rate_limit_threshold() -> int:
        """速率限制阈值（剩余请求低于此值时暂停）。"""
        return int(os.getenv("SCAN_RATE_LIMIT_THRESHOLD", "100"))

    @staticmethod
    def get_rate_limit_wait_minutes() -> int:
        """速率限制等待时间（分钟）。"""
        return int(os.getenv("SCAN_RATE_LIMIT_WAIT_MINUTES", "15"))

    @staticmethod
    def get_enable_rate_limit_check() -> bool:
        """是否启用速率限制检查。"""
        return os.getenv("SCAN_ENABLE_RATE_LIMIT_CHECK", "true").lower() == "true"

    # ==================== 配置汇总 ====================

    @staticmethod
    def get_all_config() -> Dict[str, Any]:
        """获取所有扫描配置（用于日志记录）。"""
        return {
            "subtask_timeout": ScanConfig.get_subtask_timeout(),
            "github_api_timeout": ScanConfig.get_github_api_timeout(),
            "osv_api_timeout": ScanConfig.get_osv_api_timeout(),
            "max_retries": ScanConfig.get_max_retries(),
            "retry_delay": ScanConfig.get_retry_delay(),
            "failure_threshold": ScanConfig.get_failure_threshold(),
            "max_concurrency": ScanConfig.get_max_concurrency(),
            "progress_check_interval": ScanConfig.get_progress_check_interval(),
            "batch_concurrency": ScanConfig.get_batch_concurrency()
        }

    @staticmethod
    def validate() -> bool:
        """验证配置参数是否合理。"""
        config = ScanConfig.get_all_config()

        # 检查超时范围
        if config["subtask_timeout"] < 10 or config["subtask_timeout"] > 300:
            print(f"⚠️ SUBTASK_TIMEOUT 建议范围: 10-300秒，当前: {config['subtask_timeout']}")

        if config["github_api_timeout"] < 5 or config["github_api_timeout"] > 60:
            print(f"⚠️ GITHUB_API_TIMEOUT 建议范围: 5-60秒，当前: {config['github_api_timeout']}")

        # 检查并发数
        if config["max_concurrency"] < 1 or config["max_concurrency"] > 50:
            print(f"⚠️ MAX_CONCURRENCY 建议范围: 1-50，当前: {config['max_concurrency']}")

        # 检查失败阈值
        if config["failure_threshold"] < 0.1 or config["failure_threshold"] > 0.8:
            print(f"⚠️ FAILURE_THRESHOLD 建议范围: 0.1-0.8，当前: {config['failure_threshold']}")

        # 检查 GitHub Token
        if not ScanConfig.get_github_token():
            print("⚠️ GITHUB_TOKEN 未配置，扫描将无法执行")

        return True


# 配置实例（单例模式）
_config = None


def get_scan_config() -> ScanConfig:
    """获取扫描配置实例。"""
    global _config
    if _config is None:
        _config = ScanConfig()
    return _config


# 快捷访问函数
def subtask_timeout() -> int:
    """子任务超时时间。"""
    return ScanConfig.get_subtask_timeout()


def github_api_timeout() -> int:
    """GitHub API 超时时间。"""
    return ScanConfig.get_github_api_timeout()


def osv_api_timeout() -> int:
    """OSV API 超时时间。"""
    return ScanConfig.get_osv_api_timeout()


def max_retries() -> int:
    """最大重试次数。"""
    return ScanConfig.get_max_retries()


def retry_delay() -> int:
    """重试等待时间。"""
    return ScanConfig.get_retry_delay()


def failure_threshold() -> float:
    """失败率阈值。"""
    return ScanConfig.get_failure_threshold()


def max_concurrency() -> int:
    """最大并发数。"""
    return ScanConfig.get_max_concurrency()


def progress_check_interval() -> float:
    """进度检查频率。"""
    return ScanConfig.get_progress_check_interval()


def get_batch_concurrency() -> int:
    """批量工具并发数。"""
    return ScanConfig.get_batch_concurrency()