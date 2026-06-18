"""LLM 网关层统一抽象与中性数据结构。

设计要点：
- 本模块定义「与厂商无关」的统一接口与数据结构。上层（agents / rag / services）
  只依赖本模块，**不接触 openai SDK 任何类型**——这是「屏蔽厂商差异」的边界，
  也是「统一模型调用接口」的落点；
- ``BaseLLM`` 为抽象基类，定义 ``chat``（非流式）与 ``stream``（流式）两入口；
- 数据结构 ``ChatMessage`` / ``ToolCall`` / ``Usage`` / ``ChatResponse`` /
  ``ChatChunk`` 为中性 Pydantic 模型，由各 Provider 实现把厂商响应归一为它们。

能力范围（本期）：chat 文本补全 + 流式 streaming + tool calling + usage 统计。
多模态（vision）/ embedding 不在本期范围（接口预留扩展位但未实现，YAGNI）。
"""
from __future__ import annotations

import abc
from collections.abc import AsyncIterator
from typing import Any, Optional

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """模型发起的一次工具调用（function calling）。

    ``arguments`` 已由 Provider 实现从厂商返回的 JSON 字符串反序列化为 ``dict``，
    上层无需再 ``json.loads``，直接按字段取值即可。
    """

    id: str  # 工具调用标识（用于关联后续 tool 角色回传的执行结果）
    name: str  # 要调用的工具 / 函数名
    arguments: dict[str, Any]  # 工具入参（已 parse 的 JSON 对象，非原始字符串）


class Usage(BaseModel):
    """单次调用的 token 用量统计（计费 / 限流 / 观测的基础）。"""

    prompt_tokens: int = 0  # 输入 token 数
    completion_tokens: int = 0  # 输出 token 数
    total_tokens: int = 0  # 合计 token 数


class ChatMessage(BaseModel):
    """统一消息结构（对话 / messages 列表的单条元素）。

    ``role`` 取 OpenAI 语义的 system / user / assistant / tool：
    - system：系统指令；
    - user：用户输入；
    - assistant：模型回复（可带 ``tool_calls`` 表示模型要调工具）；
    - tool：工具执行结果回传（须带 ``tool_call_id`` 关联对应的调用请求）。
    """

    role: str  # system / user / assistant / tool
    content: str = ""  # 消息文本内容（多模态图片输入本期不支持）
    tool_calls: Optional[list[ToolCall]] = None  # role=assistant 且模型发起工具调用时填充
    tool_call_id: Optional[str] = None  # role=tool 时关联的 tool_calls[].id


class ChatResponse(BaseModel):
    """非流式调用的统一返回（``chat()`` 产物）。

    抹平厂商差异：无论 OpenAI / DeepSeek / Qwen / Claude，均归一为本结构。
    """

    content: str = ""  # 模型回复文本
    tool_calls: list[ToolCall] = Field(default_factory=list)  # 模型发起的工具调用（无则空列表）
    usage: Usage = Field(default_factory=Usage)  # token 用量
    model: str = ""  # 实际生成所用模型名（厂商回显，便于核对计费）
    finish_reason: str = ""  # 结束原因（stop / length / tool_calls 等）


class ChatChunk(BaseModel):
    """流式调用的单次增量（``stream()`` yield 产物）。

    流式场景下 ``content`` / ``tool_calls`` 为增量片段，需由调用方逐块拼接；
    最后一个 chunk 的 ``finish_reason`` 非空表示流结束。``usage`` 多数厂商
    仅在末块携带（部分厂商不提供）。
    """

    content: str = ""  # 增量文本片段
    tool_calls: list[ToolCall] = Field(default_factory=list)  # 增量工具调用片段
    usage: Optional[Usage] = None  # 用量（多数厂商仅在末块出现）
    finish_reason: Optional[str] = None  # 非空表示流结束


class BaseLLM(abc.ABC):
    """LLM 统一抽象基类。

    各 Provider 实现本接口，把厂商 SDK 响应归一为 ``ChatResponse`` / ``ChatChunk``。
    上层一律面向本接口编程，经 ``app.core.llm.gateway.get_provider(name)``
    取得具体实例——不直接依赖任何 Provider 子类。
    """

    @abc.abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: Optional[str] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> ChatResponse:
        """非流式对话补全。

        Args:
            messages: 对话消息列表（system / user / assistant / tool）。
            model: 模型名；``None`` 用 Provider 配置的 ``default_model``。
            tools: 工具定义列表（OpenAI tool schema 格式，即
                ``{"type": "function", "function": {...}}``）；``None`` 不启用工具。
            temperature: 采样温度；``None`` 用厂商默认。
            max_tokens: 最大输出 token；``None`` 用厂商默认。
            **kwargs: 透传给厂商 SDK 的额外参数（如 top_p、stop 等）。

        Returns:
            归一化的 ``ChatResponse``。

        Raises:
            BizException: 调用失败或响应解析失败（errno=LLM_ERRNO_CALL_FAILED /
                LLM_ERRNO_INVALID_RESPONSE），由全局 handler 转统一响应。
        """
        raise NotImplementedError

    @abc.abstractmethod
    def stream(
        self,
        messages: list[ChatMessage],
        *,
        model: Optional[str] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatChunk]:
        """流式对话补全（逐 chunk yield）。

        **返回异步迭代器**（同步获取、``async for`` 消费），逐块 yield 增量
        ``ChatChunk``；末块 ``finish_reason`` 非空表示流结束。实现须为
        「同步返回 async generator」模式：内部用 ``async def`` + ``yield`` 定义
        生成器，本方法直接 ``return`` 它——避免 ``async def`` 方法被误用为
        awaitable。上层用法::

            async for chunk in llm.stream(messages):
                process(chunk.content)

        Args 同 :meth:`chat`。
        """
        raise NotImplementedError

    async def aclose(self) -> None:
        """释放底层 client 连接（默认空实现，Provider 持有 client 时覆盖）。

        由 ``gateway.close_llm`` 在应用 shutdown 时统一调用，确保连接池优雅释放。
        """
        return None
