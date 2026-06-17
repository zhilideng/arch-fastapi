"""Redis 异步连接池（进程级单例）。

设计要点：
- **单例连接池**：进程级共享一个 ``redis.asyncio.Redis`` 实例，复用连接池。
  ``get_redis()`` 惰性创建单例，参考 ``app/utils/http_client.py`` 模式。
- **参数配置驱动**：连接 URL、数据库编号、连接池上限、解码响应等均来自
  ``RedisSettings`` 配置段。
- **缓存层降级**：连接失败（build/ping）不阻断应用启动——记 warning + 清空单例
  降级运行；Redis 属非核心依赖（仅 DB 等核心层 fail-fast），调用方首次使用若仍
  不可用由 ``app/utils/cache.py`` 转 BizException。
- **lifespan 接入**：应用启动时调用 ``init_redis`` 建立连接，关闭时调用
  ``close_redis`` 释放连接池。

注意：需在应用关闭时调用 ``close_redis()`` 关闭单例（factory.py lifespan 已接入）。
"""
from typing import Optional

import redis.asyncio

from app.core.logger import logger
from app.core.settings import RedisSettings

# 进程级单例 Redis 客户端；None 表示尚未创建。多 worker 进程各自独立持有，
# asyncio 单线程内无并发竞争，故无需锁。
_redis_client: Optional[redis.asyncio.Redis] = None


def _build_client(settings: RedisSettings) -> redis.asyncio.Redis:
    """按 RedisSettings 构造一个异步 Redis 客户端（含连接池）。

    仅在首次 ``init_redis`` 调用时执行；后续直接复用单例。
    单独拆函数便于测试时显式构造验证参数与配置一致。

    Args:
        settings: Redis 配置段，含 url/db/max_connections/decode_responses/encoding。

    Returns:
        配置好的 ``redis.asyncio.Redis`` 实例。

    Note:
        必须用 ``redis.asyncio.Redis.from_url``（异步连接池）；若误用同步的
        ``redis.ConnectionPool``，async 命令会抛
        ``TypeError: object Connection can't be used in 'await' expression``。
    """
    # 异步连接池：from_url 内部建 redis.asyncio.ConnectionPool，
    # max_connections 控制上限防 Redis 被打爆
    return redis.asyncio.Redis.from_url(
        settings.url,
        db=settings.db,
        max_connections=settings.max_connections,
        decode_responses=settings.decode_responses,
        encoding=settings.encoding,
    )


async def init_redis(settings: RedisSettings) -> None:
    """初始化 Redis 单例连接池（应用启动时调用）。

    创建客户端并尝试 PING 验证连通性。Redis 属缓存层（非核心依赖），连接失败时
    **不阻断应用启动**——记 warning 降级运行，首次实际使用若仍不可用由调用方按
    BizException 处理；这也避免无 Redis 的环境（如单元测试）启动即崩。

    Args:
        settings: Redis 配置段，来自 ``get_settings().redis``。
    """
    global _redis_client
    if _redis_client is not None:
        logger.warning("Redis 客户端已初始化，跳过重复初始化")
        return

    try:
        _redis_client = _build_client(settings)
        await _redis_client.ping()
        logger.info("Redis 连接池已初始化: {}", settings.url)
    except (redis.ConnectionError, redis.TimeoutError, OSError) as exc:
        # 缓存层降级：build/ping 任一失败都不阻断启动（仅 DB 等核心层 fail-fast）；
        # 清空单例，避免留下连不上的坏 client，调用方经 get_redis 获知不可用
        _redis_client = None
        logger.warning(
            "Redis 连接失败，缓存层降级运行 | url={} | 原因={}: {}",
            settings.url, exc.__class__.__name__, exc,
        )


async def close_redis() -> None:
    """关闭 Redis 单例连接池（应用关闭时调用）。

    需在 factory.py lifespan shutdown 时调用，确保连接池优雅释放。
    """
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("Redis 连接池已关闭")


def get_redis() -> redis.asyncio.Redis:
    """获取进程级单例 Redis 客户端。

    多次调用返回同一实例，复用底层连接池。缓存层不应自行
    ``redis.asyncio.Redis()``。

    Returns:
        已初始化的 ``redis.asyncio.Redis`` 实例。

    Raises:
        RuntimeError: 若 ``init_redis`` 未被调用（客户端为 None）。
    """
    if _redis_client is None:
        raise RuntimeError("Redis 客户端未初始化，请先调用 init_redis()")
    return _redis_client


def get_redis_optional() -> Optional[redis.asyncio.Redis]:
    """获取 Redis 单例；降级或未初始化时返回 None（不抛异常）。

    供健康检查（readyz）等只读探针使用——区分「在线」与「降级运行」状态：
    ``get_redis()`` 在降级时抛 ``RuntimeError``（cache 层 fail-loud 需要），
    而 readyz 需要把「Redis 不可用」判为「可降级（degraded）」而非服务失败，
    故提供此查询函数避免异常掩盖可降级语义。

    Returns:
        已初始化的 ``redis.asyncio.Redis`` 实例；未初始化或已降级时为 ``None``。
    """
    return _redis_client
