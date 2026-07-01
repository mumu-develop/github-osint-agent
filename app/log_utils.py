"""
统一日志配置模块。

所有模块都应该从这里导入 logger，确保日志配置一致。
"""

import logging
import os
import sys

# 日志级别从环境变量读取
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# 配置标准库 logging
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
    force=True,
)

# 配置 structlog
import structlog

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
        structlog.dev.ConsoleRenderer(colors=True),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

# 设置标准库 logging 输出完整堆栈
logging.getLogger().setLevel(logging.DEBUG)


def get_logger(name: str = None) -> structlog.stdlib.BoundLogger:
    """获取 logger 实例。

    Args:
        name: logger 名称，通常使用模块名（如 'agent', 'backend'）

    Returns:
        structlog logger 实例
    """
    return structlog.get_logger(name)


# 创建默认 logger（用于未指定名称的模块）
logger = get_logger("app")


def log_error(logger_instance, message: str, error: Exception, **kwargs):
    """输出完整错误信息到控制台和日志。

    Args:
        logger_instance: structlog logger 实例
        message: 错误描述
        error: 异常对象
        **kwargs: 其他上下文信息
    """
    import traceback
    full_traceback = traceback.format_exc()

    # 输出到日志
    logger_instance.error(
        message,
        error_type=type(error).__name__,
        error_message=str(error),
        traceback=full_traceback,
        **kwargs
    )

    # 输出到控制台（确保能看到）
    print(f"\n{'='*60}")
    print(f"[ERROR] {message}")
    print(f"Type: {type(error).__name__}")
    print(f"Message: {str(error)}")
    if kwargs:
        print(f"Context: {kwargs}")
    print(f"Traceback:")
    print(full_traceback)
    print(f"{'='*60}\n")


# 初始化时打印日志配置信息
logger.info("log_initialized", level=LOG_LEVEL)