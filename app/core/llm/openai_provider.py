"""OpenAI 兼容 Provider 统一实现（覆盖 OpenAI / DeepSeek / Qwen / Claude 四家）。

设计要点：
- 4 家 Provider 统一走 **OpenAI 兼容端点**，靠构造时注入的 ``base_url`` +
  ``api_key`` 切换厂商，**共用同一套调用代码**——这是「统一模型调用接口」的
  实现基石（无需为每家写独立 Provider，区别仅在配置）；
- 持有 ``openai.AsyncOpenAI`` 客户端实例，构造廉价（不连云），故由
  ``gateway.init_llm`` 在应用启动期即建；
- **超时 / 重试复用 openai SDK 内置**（``timeout`` / ``max_retries`` 参数透传），
  自动处理 429 / 5xx 指数退避，无需自写重试循环——比 ``http_client`` 简洁；
- ``chat`` 走 ``stream=False`` 归一为 ``ChatResponse``；``stream`` 走
  ``stream=True`` 逐 chunk 归一为 ``ChatChunk`` yield；
- 任何异常（网络 / 超时 / 非 2xx / 解析失败）统一 ``raise BizException``，
  errno 走 ``LLM_ERRNO_*``，由全局 handler 转统一响应，禁止裸 Exception。

Claude 已知限制：经 Anthropic 官方 OpenAI 兼容端点接入，其原生 system prompt、
tool calling 返回结构、流式 chunk 字段细节有损；未来深度用 agent 能力再评估
升级 anthropic SDK 双轨（届时新增一个 Provider 实现即可，本文件不动，``base``
抽象与 ``gateway`` 均无需改）。
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, Optional

import openai

from app.core.llm.base import (
    BaseLLM,
    ChatChunk,
    ChatMessage,
    ChatResponse,
    ToolCall,
    Usage,
)
from app.core.logger import logger
from app.core.settings import LlmProviderConfig
from app.exceptions import (
    BizException,
    LLM_ERRNO_CALL_FAILED,
    LLM_ERRNO_INVALID_RESPONSE,
)


def _messages_to_openai(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    """把统一 ``ChatMessage`` 列表转为 openai SDK 的 messages 字典列表。

    - system / user：直接 ``{"role", "content"}``；
    - assistant 带 tool_calls 时附 ``tool_calls``（还原为 openai 的
      ``[{"id", "type": "function", "function": {"name", "arguments"}}]``，
      arguments 序列化回 JSON 字符串）；
    - tool：``{"role": "tool", "content", "tool_call_id"}``（回传工具执行结果）。
    """
    out: list[dict[str, Any]] = []
    for m in messages:
        item: dict[str, Any] = {"role": m.role, "content": m.content}
        if m.tool_calls:
            item["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                    },
                }
                for tc in m.tool_calls
            ]
        if m.tool_call_id is not None:
            item["tool_call_id"] = m.tool_call_id
        out.append(item)
    return out


def _parse_arguments(raw: str) -> dict[str, Any]:
    """把厂商返回的 tool_call arguments JSON 字符串 parse 为 dict。

    parse 失败（厂商偶发返回非合法 JSON）记 warning 并回退为空 dict，不抛异常
    中断整次调用——宁可丢工具入参，也不让单条解析错误炸掉整个响应。
    """
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("tool_call arguments JSON 解析失败，回退空 dict | raw={!r} | {}", raw, exc)
        return {}
    if not isinstance(parsed, dict):
        # 极少数情况 parse 出非对象（如纯数字 / 字符串），保证 dict 契约
        logger.warning("tool_call arguments 非对象，回退空 dict | parsed={!r}", parsed)
        return {}
    return parsed


class OpenAIProvider(BaseLLM):
    """基于 openai SDK 的统一 Provider（4 家共用）。

    靠构造时注入的 ``LlmProviderConfig``（base_url / api_key / default_model 等）
    切换厂商；所有 4 家 Provider 实例化为本类，区别仅在 config。
    """

    def __init__(self, name: str, config: LlmProviderConfig) -> None:
        import os

        self._name = name  # Provider 名（openai/deepseek/qwen/claude），用于日志
        self._config = config
        # 解析 api_key：优先取配置值（pydantic-settings 已合并 env/yaml）；为空则
        # 从环境变量 LLM_API_KEY_<NAME 大写> 兜底。为何不直接用 pydantic-settings 的
        # LLM__PROVIDERS__<NAME>__API_KEY：dict[str, model] 的深度 env 覆盖存在 key
        # 大小写坑（环境变量里的 OPENAI 与 yaml 小写 openai 不匹配会落成两个 key，
        # 且单独注入 api_key 会让必填的 base_url/default_model 校验失败），故密钥统一
        # 走此约定变量名——注入可靠且贴近业界惯例（与 OPENAI_API_KEY 同风格）。
        api_key = config.api_key.get_secret_value() or os.environ.get(
            f"LLM_API_KEY_{name.upper()}", ""
        )
        # AsyncOpenAI 构造廉价（仅建对象、不连云）；timeout/max_retries 透传，
        # SDK 自动按 max_retries 对 429/5xx 指数退避重试，无需自写循环。
        self._client = openai.AsyncOpenAI(
            base_url=config.base_url,
            api_key=api_key,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )

    @property
    def name(self) -> str:
        """Provider 名。"""
        return self._name

    def _resolve_model(self, model: Optional[str]) -> str:
        """解析实际使用的模型名：未指定则用配置的 default_model。"""
        return model or self._config.default_model

    @staticmethod
    def _build_kwargs(
        messages: list[ChatMessage],
        model: str,
        tools: Optional[list[dict[str, Any]]],
        temperature: Optional[float],
        max_tokens: Optional[int],
        stream: bool,
        **extra: Any,
    ) -> dict[str, Any]:
        """组装 openai SDK ``create()`` 入参字典（剔除 None 项避免覆盖厂商默认）。"""
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": _messages_to_openai(messages),
            "stream": stream,
        }
        if tools is not None:
            kwargs["tools"] = tools
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        kwargs.update(extra)
        return kwargs

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
        """非流式对话补全（见基类 :meth:`BaseLLM.chat`）。"""
        resolved_model = self._resolve_model(model)
        req_kwargs = self._build_kwargs(
            messages, resolved_model, tools, temperature, max_tokens, stream=False, **kwargs
        )
        logger.info(
            "LLM chat | provider={} | model={} | msgs={}",
            self._name,
            resolved_model,
            len(messages),
        )
        try:
            resp = await self._client.chat.completions.create(**req_kwargs)
        except openai.APIError as exc:
            # 含 APIConnectionError / APITimeoutError / RateLimitError / AuthenticationError
            # 等子类；SDK 内置重试用尽后仍失败落到此。
            logger.warning(
                "LLM 调用失败 | provider={} | model={} | {}",
                self._name,
                resolved_model,
                exc,
            )
            raise BizException(
                f"LLM 调用失败: provider={self._name} model={resolved_model} 原因: {exc.__class__.__name__}",
                errno=LLM_ERRNO_CALL_FAILED,
            ) from exc

        # 归一：choices 极端情况可能为空，防御性判空
        if not resp.choices:
            logger.warning("LLM 响应无 choices | provider={} | model={}", self._name, resolved_model)
            raise BizException(
                f"LLM 响应异常: 无 choices | provider={self._name} model={resolved_model}",
                errno=LLM_ERRNO_INVALID_RESPONSE,
            )

        choice = resp.choices[0]
        msg = choice.message
        # tool_calls 归一：arguments JSON 字符串 -> dict
        tool_calls: list[ToolCall] = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=_parse_arguments(tc.function.arguments),
                    )
                )
        usage = Usage()
        if resp.usage is not None:
            usage = Usage(
                prompt_tokens=resp.usage.prompt_tokens,
                completion_tokens=resp.usage.completion_tokens,
                total_tokens=resp.usage.total_tokens,
            )
        return ChatResponse(
            content=msg.content or "",
            tool_calls=tool_calls,
            usage=usage,
            model=resp.model,
            finish_reason=choice.finish_reason or "",
        )

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
        """流式对话补全（见基类 :meth:`BaseLLM.stream`）。

        同步返回 async generator（供 ``async for`` 消费）：实现委托给内部
        ``_stream_impl`` async generator，本方法直接 ``return`` 它，避免
        ``async def`` 方法被误用为 awaitable。
        """
        return self._stream_impl(
            messages, model, tools, temperature, max_tokens, **kwargs
        )

    async def _stream_impl(
        self,
        messages: list[ChatMessage],
        model: Optional[str],
        tools: Optional[list[dict[str, Any]]],
        temperature: Optional[float],
        max_tokens: Optional[int],
        **kwargs: Any,
    ) -> AsyncIterator[ChatChunk]:
        """流式实现的 async generator（由 :meth:`stream` 委托）。

        流式场景下 tool_calls 的 ``arguments`` 是分片到达的（每块含 index 与
        function.arguments 增量），这里逐块原样归一输出增量片段，由上层按
        index 拼接；usage 仅在末块出现（需调用方传
        ``stream_options={"include_usage": True}`` 才有）。
        """
        resolved_model = self._resolve_model(model)
        req_kwargs = self._build_kwargs(
            messages, resolved_model, tools, temperature, max_tokens, stream=True, **kwargs
        )
        logger.info(
            "LLM stream | provider={} | model={} | msgs={}",
            self._name,
            resolved_model,
            len(messages),
        )
        try:
            stream = await self._client.chat.completions.create(**req_kwargs)
        except openai.APIError as exc:
            logger.warning(
                "LLM 流式调用失败 | provider={} | model={} | {}",
                self._name,
                resolved_model,
                exc,
            )
            raise BizException(
                f"LLM 流式调用失败: provider={self._name} model={resolved_model} 原因: {exc.__class__.__name__}",
                errno=LLM_ERRNO_CALL_FAILED,
            ) from exc

        try:
            async for chunk in stream:
                if not chunk.choices:
                    # 末块可能仅含 usage（choices 空），尝试提取 usage
                    if chunk.usage is not None:
                        yield ChatChunk(
                            usage=Usage(
                                prompt_tokens=chunk.usage.prompt_tokens,
                                completion_tokens=chunk.usage.completion_tokens,
                                total_tokens=chunk.usage.total_tokens,
                            )
                        )
                    continue
                choice = chunk.choices[0]
                delta = choice.delta
                tool_calls: list[ToolCall] = []
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        # 流式增量：id / function.name 仅首块出现，arguments 分片；
                        # 缺省给空串，上层按 index 拼接完整调用。
                        fname = tc.function.name if (tc.function and tc.function.name) else ""
                        fargs = tc.function.arguments if (tc.function and tc.function.arguments) else ""
                        tool_calls.append(
                            ToolCall(
                                id=tc.id or "",
                                name=fname,
                                arguments=_parse_arguments(fargs),
                            )
                        )
                usage: Optional[Usage] = None
                if chunk.usage is not None:
                    usage = Usage(
                        prompt_tokens=chunk.usage.prompt_tokens,
                        completion_tokens=chunk.usage.completion_tokens,
                        total_tokens=chunk.usage.total_tokens,
                    )
                yield ChatChunk(
                    content=delta.content or "",
                    tool_calls=tool_calls,
                    usage=usage,
                    finish_reason=choice.finish_reason,
                )
        except openai.APIError as exc:
            # 流式过程中网络中断 / 服务端错误
            logger.warning(
                "LLM 流式中断 | provider={} | model={} | {}",
                self._name,
                resolved_model,
                exc,
            )
            raise BizException(
                f"LLM 流式中断: provider={self._name} model={resolved_model} 原因: {exc.__class__.__name__}",
                errno=LLM_ERRNO_CALL_FAILED,
            ) from exc

    async def aclose(self) -> None:
        """关闭底层 openai client（释放连接池）。"""
        await self._client.close()
