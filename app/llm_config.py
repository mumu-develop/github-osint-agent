"""
统一 LLM 模型配置模块。

使用 langchain.chat_models.init_chat_model 创建模型，支持 Rate Limiter 和超时配置。

支持环境变量配置：
- LLM_REQUEST_TIMEOUT: 请求超时（秒），默认 120
- LLM_MAX_CONCURRENCY: 最大并发请求数，默认 100
- RATE_LIMIT_REQUESTS_PER_SECOND: 每秒请求数限制（可选）
- RATE_LIMIT_CHECK_EVERY_SECONDS: 限速检查间隔（可选）
- RATE_LIMIT_MAX_BUCKET_SIZE: 令牌桶大小（可选）
"""

import os
import asyncio
from typing import Optional
from langchain.chat_models import init_chat_model
from langchain.rate_limiters import InMemoryRateLimiter
from langchain_core.language_models.chat_models import BaseChatModel
from app.log_utils import get_logger

logger = get_logger("llm")

# 全局并发信号量（控制 LLM API 并发）
_llm_semaphore: Optional[asyncio.Semaphore] = None


def get_llm_semaphore() -> asyncio.Semaphore:
    """获取 LLM 并发信号量。

    Returns:
        asyncio.Semaphore 实例
    """
    global _llm_semaphore
    if _llm_semaphore is None:
        max_concurrency = int(os.getenv("LLM_MAX_CONCURRENCY", "100"))
        _llm_semaphore = asyncio.Semaphore(max_concurrency)
        logger.info("llm_semaphore_created", max_concurrency=max_concurrency)
    return _llm_semaphore


async def with_llm_concurrency_control(coro):
    """带并发控制的 LLM 调用包装器。

    Args:
        coro: 异步协程

    Returns:
        协程执行结果
    """
    semaphore = get_llm_semaphore()
    async with semaphore:
        logger.debug("llm_concurrency_slot_acquired", current=semaphore._value)
        result = await coro
        logger.debug("llm_concurrency_slot_released")
        return result


def get_api_config() -> tuple[str, str]:
    """获取 API 配置。

    Returns:
        (api_base, api_key) 元组
    """
    api_base = os.getenv("OPENAI_API_BASE", "https://coding.dashscope.aliyuncs.com/v1")
    api_key = os.getenv("OPENAI_API_KEY", "")

    logger.debug("api_config", api_base=api_base, has_key=bool(api_key))
    return api_base, api_key


def get_request_timeout() -> int:
    """获取请求超时时间（秒）。

    Returns:
        超时秒数，默认 120 秒
    """
    return int(os.getenv("LLM_REQUEST_TIMEOUT", "120"))


def get_rate_limiter() -> Optional[InMemoryRateLimiter]:
    """从环境变量创建 Rate Limiter。

    默认配置支持 100 并发对话，每秒约 1.1 个请求。
    如果未显式配置，使用默认值以保证高并发场景稳定。

    Returns:
        InMemoryRateLimiter 实例
    """
    # 默认配置：支持 100 并发对话，平均每对话 90s
    # QPS = 100/90 ≈ 1.1，配置 2 QPS 作为安全余量
    requests_per_second = os.getenv("RATE_LIMIT_REQUESTS_PER_SECOND", "2.0")
    check_every = float(os.getenv("RATE_LIMIT_CHECK_EVERY_SECONDS", "0.1"))
    max_bucket = float(os.getenv("RATE_LIMIT_MAX_BUCKET_SIZE", "10.0"))  # 允许突发

    try:
        rps = float(requests_per_second)

        logger.info("creating_rate_limiter",
                    requests_per_second=rps,
                    check_every_n_seconds=check_every,
                    max_bucket_size=max_bucket)

        return InMemoryRateLimiter(
            requests_per_second=rps,
            check_every_n_seconds=check_every,
            max_bucket_size=max_bucket,
        )
    except ValueError as e:
        logger.warning("rate_limiter_config_invalid", error=str(e))
        # 返回默认配置而不是 None，确保高并发稳定
        return InMemoryRateLimiter(
            requests_per_second=2.0,
            check_every_n_seconds=0.1,
            max_bucket_size=10.0,
        )


def create_chat_model(
    model_name: str,
    temperature: float = 0.1,
    max_tokens: int = 4096,
    api_base: Optional[str] = None,
    api_key: Optional[str] = None,
    rate_limiter: Optional[InMemoryRateLimiter] = None,
    request_timeout: Optional[int] = None,
) -> BaseChatModel:
    """创建 Chat 模型实例。

    使用 init_chat_model 统一接口创建模型，自动禁用 Responses API。

    Args:
        model_name: 模型名称（支持 provider:前缀，如 "openai:qwen3.6-plus"）
        temperature: 温度参数
        max_tokens: 最大 token 数
        api_base: API 基地址（默认从环境变量读取）
        api_key: API 密钥（默认从环境变量读取）
        rate_limiter: Rate Limiter 实例（默认从环境变量创建）
        request_timeout: 请求超时（默认从环境变量读取）

    Returns:
        BaseChatModel 实例
    """
    # 获取配置
    if api_base is None or api_key is None:
        default_base, default_key = get_api_config()
        api_base = api_base or default_base
        api_key = api_key or default_key

    # 获取 Rate Limiter
    if rate_limiter is None:
        rate_limiter = get_rate_limiter()

    # 获取请求超时
    if request_timeout is None:
        request_timeout = get_request_timeout()

    logger.info("creating_model",
                model=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
                api_base=api_base,
                has_rate_limiter=rate_limiter is not None,
                request_timeout=request_timeout)

    # 使用 init_chat_model 创建模型
    # 显式禁用 Responses API，避免 langchain-openai 1.3.2 的 bug
    # 必须直接传递 use_responses_api=False，不能通过 model_kwargs
    model = init_chat_model(
        model=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        base_url=api_base,
        api_key=api_key,
        rate_limiter=rate_limiter,
        use_responses_api=False,  # 显式禁用 Responses API
        request_timeout=request_timeout,  # 添加请求超时
    )

    logger.info("model_created", model=model_name, use_responses_api=model.use_responses_api)

    return model


def get_default_model() -> BaseChatModel:
    """获取默认主 Agent 模型。

    从 AGENT_MODEL 环境变量读取模型名称。
    """
    model_name = os.getenv("AGENT_MODEL", "openai:qwen3.6-plus")
    logger.info("getting_default_model", env_model=model_name)
    return create_chat_model(model_name)