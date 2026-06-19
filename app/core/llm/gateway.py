"""LLM 实例初始化与获取。"""
from __future__ import annotations

import os
from inspect import isawaitable
from typing import Any

import openai

from app.core.logger import logger
from app.core.settings import LlmProviderConfig, LlmSettings
from app.exceptions import (
    BizException,
    LLM_ERRNO_CALL_FAILED,
    LLM_ERRNO_NOT_INITIALIZED,
    LLM_ERRNO_PROVIDER_NOT_FOUND,
)

llm_instances: dict[str, openai.AsyncOpenAI] = {}
langchain_models: dict[str, Any] = {}
default_provider_name: str = ""


def init_llm(settings: LlmSettings) -> None:
    """按配置初始化 LLM 客户端实例与 LangChain 模型。

    单个 Provider 构造失败时跳过，不阻断应用启动；这里不对云端做 ping 预检。
    """
    global default_provider_name
    llm_instances.clear()
    langchain_models.clear()
    default_provider_name = settings.default_provider

    for name, cfg in settings.providers.items():
        api_key = cfg.api_key.get_secret_value() or os.environ.get(
            f"LLM_API_KEY_{name.upper()}",
            "",
        )
        try:
            llm_instances[name] = openai.AsyncOpenAI(
                base_url=cfg.base_url,
                api_key=api_key,
                timeout=cfg.timeout,
                max_retries=cfg.max_retries,
            )
        except Exception as exc:  # noqa: BLE001 —— 单个 Provider 失败不阻断启动
            logger.warning(
                "LLM 实例初始化失败，已跳过（降级运行）| name={} | {}",
                name,
                exc,
            )
            continue

        try:
            langchain_models[name] = build_langchain_llm(name, cfg)
        except BizException as exc:
            logger.warning(
                "LangChain LLM 构造失败，已跳过（降级运行）| name={} | {}",
                name,
                exc,
            )

        logger.info(
            "LLM 实例已初始化 | name={} | base_url={} | model={}",
            name,
            cfg.base_url,
            cfg.default_model,
        )

    if llm_instances:
        logger.info(
            "LLM 初始化完成 | providers={} | default={}",
            sorted(llm_instances),
            default_provider_name,
        )
    else:
        logger.warning("LLM 初始化完成但未创建任何实例（providers 配置为空，降级运行）")


def get_llm(name: str | None = None) -> openai.AsyncOpenAI:
    """获取已初始化的 LLM 客户端实例。"""
    target = resolve_name(name)
    client = llm_instances.get(target)
    if client is None:
        raise BizException(
            f"未知 LLM Provider: {target}（已注册: {sorted(llm_instances)}）",
            errno=LLM_ERRNO_PROVIDER_NOT_FOUND,
        )
    return client


def get_provider(name: str | None = None) -> openai.AsyncOpenAI:
    """获取 LLM 客户端实例的兼容入口。"""
    return get_llm(name)


def get_langchain_llm(name: str | None = None) -> Any:
    """获取已初始化的 LangChain ChatModel 实例。"""
    target = resolve_name(name)
    model = langchain_models.get(target)
    if model is None:
        raise BizException(
            f"LangChain LLM 未初始化: {target}（已初始化: {sorted(langchain_models)}）",
            errno=LLM_ERRNO_NOT_INITIALIZED,
        )
    return model




def build_langchain_llm(name: str, cfg: LlmProviderConfig) -> Any:
    """创建 LangChain ChatModel 实例。"""
    try:
        from langchain.chat_models import init_chat_model
    except ImportError as exc:
        raise BizException(
            "LangChain 未安装，请先安装 langchain 相关依赖",
            errno=LLM_ERRNO_CALL_FAILED,
        ) from exc

    try:
        model = init_chat_model(
            model=cfg.default_model,
            model_provider="openai",
            api_key=resolve_api_key(name, cfg),
            base_url=cfg.base_url,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("LangChain LLM 初始化失败 | name={} | {}", name, exc)
        raise BizException(
            f"LangChain LLM 初始化失败: {name}",
            errno=LLM_ERRNO_CALL_FAILED,
        ) from exc

    logger.info("LangChain LLM 已初始化 | name={} | model={}", name, cfg.default_model)
    return model


def resolve_name(name: str | None = None) -> str:
    """解析最终使用的 Provider 名称。"""
    if not llm_instances:
        raise BizException(
            "LLM 网关未初始化（providers 为空或 init_llm 未执行）",
            errno=LLM_ERRNO_NOT_INITIALIZED,
        )
    return name or default_provider_name


def resolve_api_key(name: str, cfg: LlmProviderConfig) -> str:
    """解析 Provider 的 API Key。"""
    api_key = cfg.api_key.get_secret_value()
    return api_key or os.environ.get(f"LLM_API_KEY_{name.upper()}", "")


async def close_llm() -> None:
    """关闭全部 LLM 客户端实例并清空缓存。"""
    global default_provider_name
    errors: list[tuple[str, Exception]] = []
    for name, client in list(llm_instances.items()):
        try:
            result = client.close()
            if isawaitable(result):
                await result
        except Exception as exc:  # noqa: BLE001 —— shutdown 阶段尽力释放全部实例
            errors.append((name, exc))
            logger.exception("LLM 实例关闭失败 | name={} | {}", name, exc)

    llm_instances.clear()
    langchain_models.clear()
    default_provider_name = ""
    if errors:
        detail = "; ".join(f"{name}: {exc}" for name, exc in errors)
        raise RuntimeError(f"LLM 实例关闭失败: {detail}")
