"""LLM 能力的厂商无关数据模型。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class LLMUsage(BaseModel):
    """统一后的模型 Token 用量。"""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class ImageInput(BaseModel):
    """图文理解的一张图片输入。"""

    url: str
    detail: Literal["auto", "low", "high"] = "auto"


class EmbeddingResponse(BaseModel):
    """批量文本向量化的统一响应。"""

    provider: str
    model: str
    vectors: list[list[float]]
    usage: LLMUsage


class MultimodalResponse(BaseModel):
    """图文理解的统一响应。"""

    provider: str
    model: str
    content: str
    usage: LLMUsage
