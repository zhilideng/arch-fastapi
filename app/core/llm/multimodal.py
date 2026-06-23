"""图片与文本联合理解的统一能力。"""
from __future__ import annotations

import base64
import binascii
import re
from typing import Any
from urllib.parse import urlsplit

from app.core.llm.gateway import get_llm, get_provider_config
from app.core.llm.models import ImageInput, LLMUsage, MultimodalResponse
from app.core.logger import logger
from app.exceptions import (
    BizException,
    LLM_ERRNO_CALL_FAILED,
    LLM_ERRNO_CAPABILITY_NOT_CONFIGURED,
    LLM_ERRNO_INVALID_INPUT,
    LLM_ERRNO_INVALID_RESPONSE,
)

MAX_IMAGES_PER_REQUEST = 10
MAX_BASE64_IMAGE_BYTES = 10 * 1024 * 1024
DATA_URL_PATTERN = re.compile(
    r"^data:image/(?P<mime>jpeg|jpg|png|webp|gif);base64,(?P<data>.+)$",
    re.IGNORECASE | re.DOTALL,
)


async def analyze_images(
    prompt: str,
    images: list[ImageInput],
    *,
    provider: str | None = None,
    model: str | None = None,
    max_tokens: int | None = None,
) -> MultimodalResponse:
    """调用图文模型分析一张或多张图片。"""
    validate_multimodal_input(prompt, images, max_tokens)
    provider_name, cfg = get_provider_config(provider)
    if not cfg.multimodal_model:
        raise BizException(
            f"LLM Provider 未配置图文理解能力: {provider_name}",
            errno=LLM_ERRNO_CAPABILITY_NOT_CONFIGURED,
        )
    target_model = model or cfg.multimodal_model
    client = get_llm(provider_name)
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    content.extend(
        {
            "type": "image_url",
            "image_url": {"url": image.url, "detail": image.detail},
        }
        for image in images
    )
    request_kwargs: dict[str, Any] = {
        "model": target_model,
        "messages": [{"role": "user", "content": content}],
    }
    if max_tokens is not None:
        request_kwargs["max_tokens"] = max_tokens

    try:
        response = await client.chat.completions.create(**request_kwargs)
    except Exception as exc:  # noqa: BLE001 —— 厂商异常统一转换
        logger.exception(
            "图文理解调用失败 | provider={} | model={} | image_count={}",
            provider_name,
            target_model,
            len(images),
        )
        raise BizException("图文理解调用失败", errno=LLM_ERRNO_CALL_FAILED) from exc

    result_content = parse_multimodal_content(response)
    usage = normalize_multimodal_usage(getattr(response, "usage", None))
    logger.info(
        "图文理解调用成功 | provider={} | model={} | image_count={} | total_tokens={}",
        provider_name,
        target_model,
        len(images),
        usage.total_tokens,
    )
    return MultimodalResponse(
        provider=provider_name,
        model=target_model,
        content=result_content,
        usage=usage,
    )


def validate_multimodal_input(
    prompt: str,
    images: list[ImageInput],
    max_tokens: int | None,
) -> None:
    """校验提示词、图片数量、地址协议与 Base64 安全限制。"""
    if not isinstance(prompt, str) or not prompt.strip():
        raise BizException("图文理解 prompt 不能为空", errno=LLM_ERRNO_INVALID_INPUT)
    if not images or len(images) > MAX_IMAGES_PER_REQUEST:
        raise BizException(
            f"图文理解图片数量必须为 1-{MAX_IMAGES_PER_REQUEST}",
            errno=LLM_ERRNO_INVALID_INPUT,
        )
    if max_tokens is not None and max_tokens <= 0:
        raise BizException("max_tokens 必须为正整数", errno=LLM_ERRNO_INVALID_INPUT)
    for image in images:
        validate_image_url(image.url)


def validate_image_url(url: str) -> None:
    """仅允许 HTTPS 远程地址或受限图片 MIME 的 Base64 Data URL。"""
    parsed = urlsplit(url)
    if parsed.scheme.lower() == "https" and parsed.netloc:
        return
    match = DATA_URL_PATTERN.fullmatch(url)
    if match is None:
        raise BizException("图片必须为 HTTPS URL 或合法 Base64 Data URL", errno=LLM_ERRNO_INVALID_INPUT)
    try:
        image_bytes = base64.b64decode(match.group("data"), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise BizException("图片 Base64 编码无效", errno=LLM_ERRNO_INVALID_INPUT) from exc
    if not image_bytes or len(image_bytes) > MAX_BASE64_IMAGE_BYTES:
        raise BizException(
            f"Base64 图片不能为空且不得超过 {MAX_BASE64_IMAGE_BYTES} 字节",
            errno=LLM_ERRNO_INVALID_INPUT,
        )
    validate_image_bytes(match.group("mime").lower(), image_bytes)


def validate_image_bytes(mime: str, image_bytes: bytes) -> None:
    """用图片魔数校验 MIME，并拒绝动画 GIF。"""
    signatures = {
        "jpeg": image_bytes.startswith(b"\xff\xd8\xff"),
        "jpg": image_bytes.startswith(b"\xff\xd8\xff"),
        "png": image_bytes.startswith(b"\x89PNG\r\n\x1a\n"),
        "webp": (
            len(image_bytes) >= 12
            and image_bytes.startswith(b"RIFF")
            and image_bytes[8:12] == b"WEBP"
        ),
        "gif": image_bytes.startswith((b"GIF87a", b"GIF89a")),
    }
    if not signatures.get(mime, False):
        raise BizException("图片 MIME 与实际内容不匹配", errno=LLM_ERRNO_INVALID_INPUT)
    if mime == "gif" and (
        b"NETSCAPE2.0" in image_bytes
        or b"ANIMEXTS1.0" in image_bytes
        or image_bytes.count(b"\x2c") > 1
    ):
        raise BizException("暂不支持动画 GIF", errno=LLM_ERRNO_INVALID_INPUT)


def parse_multimodal_content(response: Any) -> str:
    """提取并校验图文模型的文本结果。"""
    choices = getattr(response, "choices", None)
    if not choices:
        raise BizException("图文理解响应缺少 choices", errno=LLM_ERRNO_INVALID_RESPONSE)
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None)
    if not isinstance(content, str) or not content.strip():
        raise BizException("图文理解响应缺少文本内容", errno=LLM_ERRNO_INVALID_RESPONSE)
    return content


def normalize_multimodal_usage(usage: Any) -> LLMUsage:
    """将厂商图文 usage 转换为统一字段。"""
    input_value = getattr(usage, "prompt_tokens", None)
    if input_value is None:
        input_value = getattr(usage, "input_tokens", 0)
    output_value = getattr(usage, "completion_tokens", None)
    if output_value is None:
        output_value = getattr(usage, "output_tokens", 0)
    input_tokens = int(input_value or 0)
    output_tokens = int(output_value or 0)
    total_value = getattr(usage, "total_tokens", None)
    total_tokens = int(
        input_tokens + output_tokens if total_value is None else total_value
    )
    return LLMUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )
