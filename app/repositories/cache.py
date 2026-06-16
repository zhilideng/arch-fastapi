"""Redis 缓存访问封装（cache-aside 模式）。

设计要点：
- **基于单例连接池**：使用 ``app.core.redis.get_redis()`` 获取进程级单例。
- **JSON 序列化**：存储对象自动 ``json.dumps``，读取自动 ``json.loads``，支持复杂类型。
- **TTL 支持**：set 操作可选传秒数过期时间；get_or_set 工厂模式默认 TTL。
- **失败转业务异常**：连接/读写失败统一抛 ``BizException``，由全局 handler 转响应。

注意：Redis 配置段 ``decode_responses=True``，存储 bytes 需自行编码；当前 JSON 序列化
仅支持可 JSON 化的类型（str/int/float/bool/list/dict/None）。
"""
import json
from typing import Any, Callable, Optional, TypeVar

from app.core.logger import logger
from app.core.redis import get_redis
from app.exceptions import BizException

T = TypeVar("T")  # 泛型：缓存值的类型


async def cache_get(key: str) -> Optional[Any]:
    """获取缓存值（自动 JSON 反序列化）。

    Args:
        key: 缓存键。

    Returns:
        缓存值（反序列化后的 Python 对象）；键不存在返回 None。

    Raises:
        BizException: Redis 操作失败。
    """
    redis = get_redis()
    try:
        value = await redis.get(key)
        if value is None:
            logger.debug("缓存未命中: {}", key)
            return None
        logger.debug("缓存命中: {}", key)
        return json.loads(value)
    except (json.JSONDecodeError, OSError) as exc:
        raise BizException(f"缓存读取失败: {key}，原因: {exc}") from exc


async def cache_set(key: str, value: Any, ttl: Optional[int] = None) -> None:
    """设置缓存值（自动 JSON 序列化）。

    Args:
        key: 缓存键。
        value: 缓存值（可 JSON 化的 Python 对象）。
        ttl: 过期秒数；None 表示永不过期（慎用，可能 OOM）。

    Raises:
        BizException: Redis 操作失败或值不可序列化。
    """
    redis = get_redis()
    try:
        serialized = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise BizException(f"缓存值不可序列化: {key}，原因: {exc}") from exc

    try:
        if ttl is not None:
            await redis.set(key, serialized, ex=ttl)
            logger.debug("缓存已设置（TTL {}s）: {}", ttl, key)
        else:
            await redis.set(key, serialized)
            logger.debug("缓存已设置（永不过期）: {}", key)
    except (OSError, redis.RedisError) as exc:
        raise BizException(f"缓存写入失败: {key}，原因: {exc}") from exc


async def cache_delete(key: str) -> None:
    """删除缓存键。

    Args:
        key: 缓存键。

    Raises:
        BizException: Redis 操作失败。
    """
    redis = get_redis()
    try:
        await redis.delete(key)
        logger.debug("缓存已删除: {}", key)
    except (OSError, redis.RedisError) as exc:
        raise BizException(f"缓存删除失败: {key}，原因: {exc}") from exc


async def get_or_set(
    key: str,
    factory: Callable[[], Any],
    ttl: Optional[int] = None,
) -> Any:
    """Cache-aside 模式：先查缓存，未命中则调用工厂函数并回写。

    典型用法：
        result = await get_or_set("user:123", lambda: fetch_user_from_db(123), ttl=3600)

    Args:
        key: 缓存键。
        factory: 异步工厂函数（缓存未命中时调用，返回值需可 JSON 化）。
        ttl: 回写缓存的过期秒数；None 表示永不过期。

    Returns:
        缓存值或工厂函数返回值。

    Raises:
        BizException: Redis 操作失败或工厂函数抛异常。
    """
    cached = await cache_get(key)
    if cached is not None:
        return cached

    logger.info("缓存未命中，调用工厂函数: {}", key)
    value = await factory()
    await cache_set(key, value, ttl=ttl)
    return value
