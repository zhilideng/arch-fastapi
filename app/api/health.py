"""健康检查路由：存活探针（livez）/ 就绪探针（readyz）。

两类探针对应不同基础设施机制，回答不同问题：
- **livez**（含 ``/health`` 兼容别名）：进程是否存活。只看进程本身，绝不碰依赖——
  否则 DB 抖动会触发 K8s 重启 Pod，而重启治不好 DB，反致重启风暴（经典反模式）。
- **readyz**：进程能否正确对外服务。检查请求路径上的必需依赖（DB）；不就绪则
  返回 503 让负载均衡摘流量（不重启，等依赖恢复再接流量）。Redis 属可降级依赖，
  不可用时标 ``degraded`` 但仍判就绪——缓存层挂了应用仍能正确响应，仅回源变慢。

依赖检查带超时（``asyncio.wait_for``），避免某依赖卡死拖垮探针、被 K8s 误判超时。
超时阈值写死不进配置（与 CORS/RequestID 一致：基础设施策略各环境一致）。
"""
import asyncio
import time
from typing import Any

from fastapi import APIRouter
from starlette.responses import JSONResponse
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import get_engine
from app.core.logger import logger
from app.core.redis import get_redis_optional
from app.utils.common import ApiResponse

router = APIRouter(tags=["health"])

# 探针超时（秒），写死不进配置：与 CORS/RequestID 一致，基础设施策略各环境固定。
# 阈值留足真实往返余量，又远小于依赖灾难性卡顿——确保探针自身不被拖垮。
_DB_PROBE_TIMEOUT = 2.0
_REDIS_PROBE_TIMEOUT = 1.0


async def _check_db(engine: Any, timeout: float = _DB_PROBE_TIMEOUT) -> dict[str, Any]:
    """检查 DB 连通性：SELECT 1，带超时。

    engine 为 None（未初始化）、SELECT 1 异常或超时——均判 ``down``。DB 是核心
    依赖，down 时 readyz 将返回 503 摘流量（fail-fast 设计：DB 不可达即不就绪）。

    Args:
        engine: ``app.core.database.get_engine()`` 返回的异步引擎，可为 None。
        timeout: SELECT 1 超时秒数（默认 ``_DB_PROBE_TIMEOUT``）。

    Returns:
        ``{"status": "up"|"down", "latency_ms"?, "error"?}``。
    """
    if engine is None:
        return {"status": "down", "error": "数据库引擎未初始化"}

    async def _ping():
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    start = time.perf_counter()
    try:
        await asyncio.wait_for(_ping(), timeout=timeout)
    except asyncio.TimeoutError:
        return {"status": "down", "error": f"SELECT 1 超时（{timeout}s）"}
    except Exception as exc:  # noqa: BLE001 —— 探针须吞下一切异常转为 down 状态
        logger.warning("就绪检查：DB 探测失败 | 原因={}: {}", exc.__class__.__name__, exc)
        return {"status": "down", "error": str(exc)}
    return {"status": "up", "latency_ms": round((time.perf_counter() - start) * 1000, 2)}


async def _check_redis(
    client: Any, timeout: float = _REDIS_PROBE_TIMEOUT
) -> dict[str, Any]:
    """检查 Redis 连通性：PING，带超时。

    client 为 None（未初始化/降级）、PING 异常或超时——均判 ``degraded``（非 down）：
    Redis 属可降级依赖，不可用时应用仍能正确服务，仅缓存失效、回源变慢。故 readyz
    在 Redis degraded 时仍返回 200，仅在响应体标记。

    Args:
        client: ``app.core.redis.get_redis_optional()`` 返回的客户端，可为 None。
        timeout: PING 超时秒数（默认 ``_REDIS_PROBE_TIMEOUT``）。

    Returns:
        ``{"status": "up"|"degraded", "latency_ms"?, "error"?}``。
    """
    if client is None:
        return {"status": "degraded", "error": "Redis 未初始化或已降级"}

    start = time.perf_counter()
    try:
        await asyncio.wait_for(client.ping(), timeout=timeout)
    except asyncio.TimeoutError:
        return {"status": "degraded", "error": f"PING 超时（{timeout}s）"}
    except Exception as exc:  # noqa: BLE001 —— 探针须吞下一切异常转为 degraded 状态
        logger.warning("就绪检查：Redis 探测失败 | 原因={}: {}", exc.__class__.__name__, exc)
        return {"status": "degraded", "error": str(exc)}
    return {"status": "up", "latency_ms": round((time.perf_counter() - start) * 1000, 2)}


def _readiness(db: dict[str, Any], redis: dict[str, Any]) -> dict[str, Any]:
    """聚合两依赖检查结果为就绪总览（纯函数，不含 I/O）。

    判定优先级：DB down → ``not_ready``（核心依赖不可用，必须摘流量，优先级最高，
    即使 Redis 同时降级也以 not_ready 为准）；仅 Redis 降级 → ``degraded``（仍可
    服务）；两者均 up → ``ready``。

    Args:
        db: ``_check_db`` 返回的检查结果。
        redis: ``_check_redis`` 返回的检查结果。

    Returns:
        ``{"status": "ready"|"degraded"|"not_ready", "checks": {"db":..., "redis":...}}``。
    """
    if db["status"] != "up":
        status = "not_ready"
    elif redis["status"] != "up":
        status = "degraded"
    else:
        status = "ready"
    return {"status": status, "checks": {"db": db, "redis": redis}}


@router.get("/health")
async def health() -> dict:
    """存活探针（``/livez`` 兼容别名）：返回统一响应格式的服务状态与当前环境。"""
    return ApiResponse.ok({"env": get_settings().app.env}).to_payload()


@router.get("/livez")
async def livez() -> dict:
    """存活探针：只看进程，不碰依赖，进程能响应即 200。

    供 K8s livenessProbe / 负载均衡判断进程是否存活。绝不可检查依赖——否则 DB 抖动
    会触发重启，而重启治不好 DB，反致重启风暴。
    """
    return ApiResponse.ok(
        {"status": "alive", "env": get_settings().app.env}
    ).to_payload()


@router.get("/readyz")
async def readyz():
    """就绪探针：检查 DB/Redis 等关键依赖。

    - DB 不可达 → HTTP 503（``code=503``），让负载均衡摘流量（DB 是核心依赖，
      fail-fast：不可达即不就绪，等恢复再接流量）；
    - Redis 降级 → HTTP 200 但响应体 ``status=degraded``（Redis 可降级，挂了应用
      仍能正确服务，仅缓存失效、回源变慢，故不摘流量）；
    - 双 up → HTTP 200 ``status=ready``。

    供 K8s readinessProbe。响应体 ``data.checks`` 给出每项依赖状态与延迟。
    """
    db = await _check_db(get_engine())
    redis = await _check_redis(get_redis_optional())
    data = _readiness(db, redis)

    if data["status"] == "not_ready":
        # 用 JSONResponse 才能同时控制 HTTP 503 与统一响应体（直接 return dict 会 200）
        return JSONResponse(
            status_code=503,
            content=ApiResponse.fail(code=503, message="not ready", data=data).to_payload(),
        )
    message = "ok" if data["status"] == "ready" else "degraded"
    return ApiResponse.ok(data, message=message).to_payload()
