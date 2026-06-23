"""文本 Embedding 统一能力。"""
from __future__ import annotations

from typing import Any

from app.core.llm.gateway import get_llm, get_provider_config
from app.core.llm.models import EmbeddingResponse, LLMUsage
from app.core.logger import logger
from app.exceptions import (
    BizException,
    LLM_ERRNO_CALL_FAILED,
    LLM_ERRNO_CAPABILITY_NOT_CONFIGURED,
    LLM_ERRNO_INVALID_INPUT,
    LLM_ERRNO_INVALID_RESPONSE,
)

MAX_EMBEDDING_BATCH_SIZE = 2048


async def embed(
    texts: list[str],
    *,
    provider: str | None = None,
    model: str | None = None,
    dimensions: int | None = None,
) -> EmbeddingResponse:
    """批量生成文本向量，并返回厂商无关的统一响应。"""
    normalized_texts = validate_texts(texts)
    if dimensions is not None and dimensions <= 0:
        raise BizException("Embedding dimensions 必须为正整数", errno=LLM_ERRNO_INVALID_INPUT)

    provider_name, cfg = get_provider_config(provider)
    if not cfg.embedding_model:
        raise BizException(
            f"LLM Provider 未配置 Embedding 能力: {provider_name}",
            errno=LLM_ERRNO_CAPABILITY_NOT_CONFIGURED,
        )
    target_model = model or cfg.embedding_model
    client = get_llm(provider_name)
    request_kwargs: dict[str, Any] = {
        "model": target_model,
        "input": normalized_texts,
        "encoding_format": "float",
    }
    if dimensions is not None:
        request_kwargs["dimensions"] = dimensions

    try:
        response = await client.embeddings.create(**request_kwargs)
    except Exception as exc:  # noqa: BLE001 —— 厂商异常统一转换
        logger.exception(
            "Embedding 调用失败 | provider={} | model={} | batch_size={}",
            provider_name,
            target_model,
            len(normalized_texts),
        )
        raise BizException("Embedding 调用失败", errno=LLM_ERRNO_CALL_FAILED) from exc

    vectors = parse_vectors(getattr(response, "data", None), len(normalized_texts))
    usage = normalize_embedding_usage(getattr(response, "usage", None))
    logger.info(
        "Embedding 调用成功 | provider={} | model={} | batch_size={} | dimensions={} | input_tokens={}",
        provider_name,
        target_model,
        len(normalized_texts),
        dimensions or "default",
        usage.input_tokens,
    )
    return EmbeddingResponse(
        provider=provider_name,
        model=target_model,
        vectors=vectors,
        usage=usage,
    )


def validate_texts(texts: list[str]) -> list[str]:
    """校验批量文本，并保留原始内容与顺序。"""
    if not texts or len(texts) > MAX_EMBEDDING_BATCH_SIZE:
        raise BizException(
            f"Embedding 批次大小必须为 1-{MAX_EMBEDDING_BATCH_SIZE}",
            errno=LLM_ERRNO_INVALID_INPUT,
        )
    if any(not isinstance(text, str) or not text.strip() for text in texts):
        raise BizException("Embedding 输入不能为空", errno=LLM_ERRNO_INVALID_INPUT)
    return texts


def parse_vectors(data: Any, expected_count: int) -> list[list[float]]:
    """校验厂商向量响应并按 index 恢复输入顺序。"""
    if not isinstance(data, (list, tuple)) or len(data) != expected_count:
        raise BizException("Embedding 响应数量无效", errno=LLM_ERRNO_INVALID_RESPONSE)

    indexed: dict[int, list[float]] = {}
    for item in data:
        index = getattr(item, "index", None)
        vector = getattr(item, "embedding", None)
        if (
            not isinstance(index, int)
            or index < 0
            or index >= expected_count
            or index in indexed
            or not isinstance(vector, (list, tuple))
            or not vector
        ):
            raise BizException("Embedding 响应结构无效", errno=LLM_ERRNO_INVALID_RESPONSE)
        try:
            indexed[index] = [float(value) for value in vector]
        except (TypeError, ValueError) as exc:
            raise BizException(
                "Embedding 响应包含非数值向量",
                errno=LLM_ERRNO_INVALID_RESPONSE,
            ) from exc

    if set(indexed) != set(range(expected_count)):
        raise BizException("Embedding 响应 index 不完整", errno=LLM_ERRNO_INVALID_RESPONSE)
    return [indexed[index] for index in range(expected_count)]


def normalize_embedding_usage(usage: Any) -> LLMUsage:
    """将厂商 Embedding usage 转换为统一字段。"""
    input_value = getattr(usage, "prompt_tokens", None)
    if input_value is None:
        input_value = getattr(usage, "input_tokens", 0)
    input_tokens = int(input_value or 0)
    total_value = getattr(usage, "total_tokens", None)
    total_tokens = int(input_tokens if total_value is None else total_value)
    return LLMUsage(
        input_tokens=input_tokens,
        output_tokens=0,
        total_tokens=total_tokens,
    )
