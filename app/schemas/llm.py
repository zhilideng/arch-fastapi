"""LLM 验证接口请求模型。"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.llm.models import ImageInput


class EmbeddingTestRequest(BaseModel):
    """Embedding 能力验证请求。"""

    texts: list[str] = Field(min_length=1, max_length=2048)
    provider: str | None = Field(default=None, min_length=1, max_length=50)
    model: str | None = Field(default=None, min_length=1, max_length=100)
    dimensions: int | None = Field(default=None, gt=0)


class MultimodalTestRequest(BaseModel):
    """图文理解能力验证请求。"""

    prompt: str = Field(min_length=1, max_length=10_000)
    images: list[ImageInput] = Field(min_length=1, max_length=10)
    provider: str | None = Field(default=None, min_length=1, max_length=50)
    model: str | None = Field(default=None, min_length=1, max_length=100)
    max_tokens: int | None = Field(default=None, gt=0, le=16_384)
