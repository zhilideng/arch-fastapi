"""LLM 测试 API 路由（v1）。

仅用于验证已配置 Provider 的连通性与基础响应，不承载正式业务编排。
"""
from typing import Any

import openai
from fastapi import APIRouter, Query, Request

from app.core.config import get_settings
from app.core.llm.embedding import embed
from app.core.llm.gateway import get_langchain_llm, get_llm, langchain_tracing_context
from app.core.llm.multimodal import analyze_images
from app.exceptions import BizException, LLM_ERRNO_CALL_FAILED
from app.schemas.llm import EmbeddingTestRequest, MultimodalTestRequest
from app.utils.common import ApiResponse

router = APIRouter(prefix="/llm", tags=["llm"])


@router.post("/embeddings/test")
async def test_embeddings(request_body: EmbeddingTestRequest) -> dict[str, Any]:
    """验证 Provider 的批量文本 Embedding 能力。"""
    response = await embed(
        request_body.texts,
        provider=request_body.provider,
        model=request_body.model,
        dimensions=request_body.dimensions,
    )
    return ApiResponse.ok(response.model_dump()).to_payload()


@router.post("/multimodal/test")
async def test_multimodal(request_body: MultimodalTestRequest) -> dict[str, Any]:
    """验证 Provider 的 URL/Base64 图文理解能力。"""
    response = await analyze_images(
        request_body.prompt,
        request_body.images,
        provider=request_body.provider,
        model=request_body.model,
        max_tokens=request_body.max_tokens,
    )
    return ApiResponse.ok(response.model_dump()).to_payload()


@router.get("/zhipu/test")
async def test_zhipu_llm(
    request: Request,
    prompt: str = Query("只回复两个字：成功", min_length=1, max_length=500),
    max_tokens: int = Query(32, ge=1, le=512),
) -> dict[str, Any]:
    """测试智谱 LLM Provider 是否可用。

    密钥由 ``LLM_API_KEY_ZHIPU`` 注入，接口不接收也不回显任何密钥。
    """
    settings = getattr(request.app.state, "settings", None) or get_settings()
    cfg = settings.llm.providers.get("zhipu")
    if cfg is None:
        raise BizException("智谱 LLM Provider 未配置", errno=LLM_ERRNO_CALL_FAILED)

    client = get_llm("zhipu")
    try:
        response = await client.chat.completions.create(
            model=cfg.default_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
    except openai.AuthenticationError as exc:
        raise BizException(
            "智谱 LLM 鉴权失败，请检查 LLM_API_KEY_ZHIPU 是否正确并已在服务进程中生效",
            errno=LLM_ERRNO_CALL_FAILED,
        ) from exc
    except openai.APIStatusError as exc:
        raise BizException(
            f"智谱 LLM 调用失败（HTTP {exc.status_code}）",
            errno=LLM_ERRNO_CALL_FAILED,
        ) from exc
    except Exception as exc:  # noqa: BLE001 —— 外部模型调用失败统一转业务异常
        raise BizException("智谱 LLM 调用失败", errno=LLM_ERRNO_CALL_FAILED) from exc

    message = response.choices[0].message.content if response.choices else ""
    usage = response.usage.model_dump() if response.usage is not None else None
    return ApiResponse.ok(
        {
            "provider": "zhipu",
            "model": cfg.default_model,
            "content": message,
            "usage": usage,
        }
    ).to_payload()


@router.get("/langchain/test")
async def test_langchain_llm(
    request: Request,
    provider: str | None = Query("zhipu", min_length=1, max_length=50),
    prompt: str = Query("只回复两个字：成功", min_length=1, max_length=500),
) -> dict[str, Any]:
    """测试 LangChain ChatModel 是否可用。

    不接收密钥；Provider 密钥仍由 ``LLM_API_KEY_<大写PROVIDER>`` 注入。
    """
    settings = getattr(request.app.state, "settings", None) or get_settings()
    provider_name = provider or settings.llm.default_provider
    cfg = settings.llm.providers.get(provider_name)
    if cfg is None:
        raise BizException(
            f"LLM Provider 未配置: {provider_name}",
            errno=LLM_ERRNO_CALL_FAILED,
        )

    model = get_langchain_llm(provider_name)
    try:
        with langchain_tracing_context():
            response = await model.ainvoke(prompt)
    except openai.AuthenticationError as exc:
        raise BizException(
            f"LangChain LLM 鉴权失败，请检查 LLM_API_KEY_{provider_name.upper()} 是否正确并已在服务进程中生效",
            errno=LLM_ERRNO_CALL_FAILED,
        ) from exc
    except openai.APIStatusError as exc:
        raise BizException(
            f"LangChain LLM 调用失败（HTTP {exc.status_code}）",
            errno=LLM_ERRNO_CALL_FAILED,
        ) from exc
    except Exception as exc:  # noqa: BLE001 —— 外部模型调用失败统一转业务异常
        raise BizException("LangChain LLM 调用失败", errno=LLM_ERRNO_CALL_FAILED) from exc

    return ApiResponse.ok(
        {
            "provider": provider_name,
            "model": cfg.default_model,
            "content": getattr(response, "content", response),
            "usage_metadata": getattr(response, "usage_metadata", None),
            "response_metadata": getattr(response, "response_metadata", None),
        }
    ).to_payload()
