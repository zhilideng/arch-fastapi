"""LLM 网关工厂与进程级单例管理。

设计要点：
- 进程级 ``_providers`` 字典缓存全部已注册 Provider 单例。``init_llm`` 启动期
  遍历配置 ``providers`` 构造（``AsyncOpenAI`` 构造廉价、不连云，故启动期建
  无网络开销）；
- ``get_provider(name=None)`` 返回指定 Provider（``None`` 回退 ``default_provider``），
  未知名字或未初始化抛 ``BizException``（fail-loud，避免静默用错 Provider）；
- ``close_llm`` 关闭全部 Provider client，接入 ``app.server.lifespan`` shutdown；
- **不在启动期对云端做 ping 预检**——LLM 调用是付费网络调用，不适合启动 fail-fast；
  连通性由首次真实调用暴露（失败转 ``BizException``）。与 DB「启动期预检 fail-fast」
  对照，LLM 按 ``http_client`` 模式「惰性、调用时失败转异常」。

多 Provider 切换：上层 ``get_provider("deepseek")`` 即可换厂商，无需改业务代码——
这是「多模型 Provider」的统一入口。
"""
from __future__ import annotations

from typing import Optional

from app.core.llm.base import BaseLLM
from app.core.llm.openai_provider import OpenAIProvider
from app.core.logger import logger
from app.core.settings import LlmSettings
from app.exceptions import (
    BizException,
    LLM_ERRNO_NOT_INITIALIZED,
    LLM_ERRNO_PROVIDER_NOT_FOUND,
)

# 进程级 Provider 单例缓存：name -> Provider 实例。
# 多 worker 进程各自独立持有；asyncio 单线程内无并发竞争，无需锁。
_providers: dict[str, BaseLLM] = {}
# 默认 Provider 名（init_llm 时从配置读取缓存，避免每次 get_provider 都查 settings）
_default_provider: str = ""


def init_llm(settings: LlmSettings) -> None:
    """启动期初始化：按配置构造全部 Provider 单例。

    遍历 ``settings.providers`` 为每个 Provider 建一个 ``OpenAIProvider`` 实例
    （``AsyncOpenAI`` 构造廉价、不连云，故启动期建无网络开销）。

    空配置（``providers`` 为空）时不抛异常——网关降级为「无 Provider 可用」，
    首次 ``get_provider`` 时才 fail-loud。这允许「未配置 LLM 的环境正常启动」
    （如纯 DB/Redis 服务），仅在真正调用 LLM 时才报错。

    Args:
        settings: LLM 配置段（含 ``default_provider`` 与 ``providers`` 字典）。
    """
    global _default_provider
    _providers.clear()
    _default_provider = settings.default_provider

    for name, cfg in settings.providers.items():
        try:
            _providers[name] = OpenAIProvider(name, cfg)
        except Exception as exc:  # noqa: BLE001 —— 构造失败不阻断启动
            # LLM 属非核心依赖：单个 Provider 构造失败（如 api_key 缺失导致 openai
            # SDK 凭证校验抛错）时跳过并降级运行，与 Redis「连不上降级」哲学一致。
            # 这避免「未配密钥的环境无法启动应用」——真正调用该 Provider 时才由
            # get_provider（未注册）/ 调用失败（凭证无效）暴露问题。
            logger.warning(
                "LLM Provider 构造失败，已跳过（降级运行）| name={} | {}",
                name,
                exc,
            )
            continue
        logger.info(
            "LLM Provider 已注册 | name={} | base_url={} | default_model={}",
            name,
            cfg.base_url,
            cfg.default_model,
        )
    if _providers:
        logger.info(
            "LLM 网关初始化完成 | 已注册 {} 个 Provider | default={}",
            len(_providers),
            _default_provider,
        )
    else:
        logger.warning("LLM 网关初始化完成但未注册任何 Provider（providers 配置为空，降级运行）")


def get_provider(name: Optional[str] = None) -> BaseLLM:
    """获取 Provider 单例。

    Args:
        name: Provider 名；``None`` 用配置的 ``default_provider``。

    Returns:
        对应的 ``BaseLLM`` 实例。

    Raises:
        BizException: 未初始化（``_providers`` 空）或 ``name`` 不存在（fail-loud）。
    """
    if not _providers:
        raise BizException(
            "LLM 网关未初始化（providers 为空或 init_llm 未执行）",
            errno=LLM_ERRNO_NOT_INITIALIZED,
        )
    target = name or _default_provider
    provider = _providers.get(target)
    if provider is None:
        raise BizException(
            f"未知 LLM Provider: {target}（已注册: {sorted(_providers)}）",
            errno=LLM_ERRNO_PROVIDER_NOT_FOUND,
        )
    return provider


async def close_llm() -> None:
    """关闭全部 Provider client，释放连接池。

    单个 Provider 关闭失败不阻断其余（尽力释放全部资源），最后汇总抛错。
    由 ``app.server.lifespan`` shutdown 调用。
    """
    global _default_provider
    errors: list[tuple[str, Exception]] = []
    for name, provider in list(_providers.items()):
        try:
            await provider.aclose()
        except Exception as exc:  # noqa: BLE001 —— shutdown 必须尽力释放全部 Provider
            errors.append((name, exc))
            logger.exception("LLM Provider 关闭失败 | name={} | {}", name, exc)
    _providers.clear()
    _default_provider = ""
    if errors:
        detail = "; ".join(f"{n}: {e}" for n, e in errors)
        raise RuntimeError(f"LLM Provider 关闭失败: {detail}")
