"""LLM 实例初始化与获取。"""
from __future__ import annotations

import os
from contextlib import contextmanager
from inspect import isawaitable
from pathlib import Path
from typing import Any

import openai
from dotenv import dotenv_values

from app.core.logger import logger
from app.core.settings import LangSmithConfig, LlmProviderConfig, LlmSettings
from app.exceptions import (
    BizException,
    LLM_ERRNO_CALL_FAILED,
    LLM_ERRNO_NOT_INITIALIZED,
    LLM_ERRNO_PROVIDER_NOT_FOUND,
)

llm_instances: dict[str, openai.AsyncOpenAI] = {}
langchain_models: dict[str, Any] = {}
default_provider_name: str = ""
# LangSmith 追踪配置（init_llm 注入，供 langchain_tracing_context 请求级读取）；
# 下划线前缀表「模块私有实现细节」，非业务实体命名，符合命名规范排除项。
_langsmith_config: LangSmithConfig | None = None


def init_llm(settings: LlmSettings) -> None:
    """按配置初始化 LLM 客户端实例与 LangChain 模型。

    单个 Provider 构造失败时跳过，不阻断应用启动；这里不对云端做 ping 预检。
    开头先按 ``settings.langsmith`` 配置 LangSmith 追踪（开关默认关，零上报）。
    """
    global default_provider_name, _langsmith_config
    llm_instances.clear()
    langchain_models.clear()
    default_provider_name = settings.default_provider

    # LangSmith 追踪：缓存配置 + 按开关设全局环境变量（关则什么都不做）
    _langsmith_config = settings.langsmith
    configure_langsmith_tracing(settings.langsmith)

    for name, cfg in settings.providers.items():
        api_key = resolve_api_key(name, cfg)
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
    """创建 LangChain ChatModel 实例。

    LangSmith 追踪已在 ``init_llm`` 开头按开关统一配置（全局一次性），此处不再
    重复调用，避免每个 Provider 构造时重复设环境变量。
    """
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


def configure_langsmith_tracing(cfg: LangSmithConfig) -> None:
    """按 LangSmith 开关配置全局追踪环境变量。

    受控变量同时覆盖 langsmith / langchain 两套前缀（``LANGSMITH_TRACING_V2`` 与
    ``LANGCHAIN_TRACING_V2``），兼容新旧命名——langchain 运行时按这些环境变量
    决定是否上报，必须在应用层显式收敛，否则外部 shell / IDE 注入的 ``true``
    （连同占位 key）会让本地/测试持续往 LangSmith 发请求并报 403。

    - **开关关（``enabled=false``，默认）**：把两套 tracing 变量**强制设为
      ``false``**，压制外部可能存在的 ``true``，实现真正的零上报（关键：不能
      只「不设」——外部 ``true`` 仍会触发上报）。
    - **开关开（``enabled=true``）**：设 ``true`` + ``LANGSMITH_PROJECT`` /
      ``LANGCHAIN_PROJECT``；密钥由 ``LANGSMITH_API_KEY`` / ``LANGCHAIN_API_KEY``
      环境变量另行注入，本函数不覆盖既有值。
    """
    tracing_vars = ("LANGSMITH_TRACING_V2", "LANGCHAIN_TRACING_V2")
    if not cfg.enabled:
        # 强制关闭：压制外部 shell/IDE 注入的 tracing=true（避免占位 key 报 403）
        for var in tracing_vars:
            os.environ[var] = "false"
        return
    for var in tracing_vars:
        os.environ[var] = "true"
    if cfg.project:
        os.environ["LANGSMITH_PROJECT"] = cfg.project
        os.environ["LANGCHAIN_PROJECT"] = cfg.project
    logger.info("LangSmith 追踪已启用 | project={}", cfg.project)


@contextmanager
def langchain_tracing_context():
    """按 LangSmith 开关决定是否进入追踪上下文（请求级临时追踪）。

    开关关（默认）：no-op，直接 yield，块内 LangChain 调用不上报。
    开关开：进入 ``tracing_v2_enabled``，块内 runs 上报到 LangSmith（project
    取配置值）。供 ``/v1/llm/langchain/test`` 等请求级临时追踪使用——与
    ``configure_langsmith_tracing`` 设的全局环境变量一致：开关关时两者皆静默。
    """
    cfg = _langsmith_config
    if cfg is None or not cfg.enabled:
        yield
        return
    try:
        from langchain_core.tracers.context import tracing_v2_enabled
    except ImportError as exc:
        raise BizException(
            "LangChain 未安装，无法启用 LangSmith 追踪",
            errno=LLM_ERRNO_CALL_FAILED,
        ) from exc
    with tracing_v2_enabled(project_name=cfg.project or None):
        yield


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
    env_name = f"LLM_API_KEY_{name.upper()}"
    return api_key or os.environ.get(env_name, "") or read_dotenv_value(env_name)


def read_dotenv_value(name: str) -> str:
    """从项目根 ``.env`` 读取自定义环境变量。

    pydantic-settings 会读取 ``.env`` 参与 Settings 构造，但不会把未知变量写回
    ``os.environ``；LLM_API_KEY_<NAME> 属于网关自定义约定，故这里显式兜底读取。
    """
    env_path = project_root() / ".env"
    if not env_path.exists():
        return ""
    value = dotenv_values(env_path).get(name)
    return str(value).strip() if value else ""


def project_root() -> Path:
    """定位项目根目录。"""
    cur = Path(__file__).resolve().parent
    for anc in (cur, *cur.parents):
        if (anc / ".git").exists() or (anc / "requirements.txt").exists():
            return anc
    return Path(__file__).resolve().parents[3]


async def close_llm() -> None:
    """关闭全部 LLM 客户端实例并清空缓存。"""
    global default_provider_name, _langsmith_config
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
    _langsmith_config = None
    if errors:
        detail = "; ".join(f"{name}: {exc}" for name, exc in errors)
        raise RuntimeError(f"LLM 实例关闭失败: {detail}")
