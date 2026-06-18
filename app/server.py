"""应用服务器组装与运行入口。

本模块集中承载应用启动相关逻辑：
- ``create_app``：创建 FastAPI 实例并注册路由、异常处理器和中间件；
- ``lifespan``：启动期加载配置并初始化 DB/Redis，关闭期释放资源；
- ``run``：把 ``AppSettings`` 翻译为 uvicorn 启动参数。

``main.py`` 只负责导出 ``create_app`` 与触发 ``run``，启动阅读路径保持为
``main.py -> app.server``。
"""
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
import multiprocessing

from fastapi import FastAPI
import uvicorn

from app.api.routes import register_routes
from app.core.config import Settings, get_settings
from app.core.logger import intercept_uvicorn_logs, logger, setup_logging
from app.exceptions import register_exception_handlers as register_exception
from app.middleware.access_log import setup_access_log
from app.middleware.cors import setup_cors
from app.middleware.request_id import setup_request_id

# ASGI app 工厂定位串（factory 模式）：reload 模式必须传字符串，统一用
# app.server:create_app，避免模块级创建 app 带来的导入期副作用。
_APP_IMPORT_STRING = "app.server:create_app"


def load_config() -> Settings:
    """启动时加载配置并初始化日志。"""
    settings = get_settings()
    setup_logging(settings.logging)
    intercept_uvicorn_logs(level=settings.app.log_level)

    app_cfg = settings.app
    logger.info(
        "配置加载完成 | env={} | name={} | host={} | port={} | debug={} | log_level={}",
        app_cfg.env,
        app_cfg.name,
        app_cfg.host,
        app_cfg.port,
        app_cfg.debug,
        app_cfg.log_level,
    )
    return settings


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器。"""
    register_exception(app)


def register_middlewares(app: FastAPI, settings: Settings) -> None:
    """注册中间件。

    注册顺序遵循 Starlette 语义：后注册者在更外层。请求进入顺序为
    RequestID -> AccessLog -> CORS -> 路由。
    """
    setup_cors(app, settings.cors)
    setup_access_log(app)
    setup_request_id(app)


async def _cleanup_resources(
    steps: list[tuple[str, Callable[[], Awaitable[None]]]]
) -> None:
    """按顺序释放资源；单项失败不阻断后续清理，最后汇总抛错。"""
    errors: list[tuple[str, Exception]] = []
    for name, close in steps:
        try:
            await close()
        except Exception as exc:  # noqa: BLE001 —— shutdown 必须尽力释放全部资源
            errors.append((name, exc))
            logger.exception("应用关闭资源释放失败 | resource={} | {}", name, exc)

    if errors:
        detail = "; ".join(f"{name}: {exc}" for name, exc in errors)
        raise RuntimeError(f"应用关闭资源释放失败: {detail}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化资源，关闭时清理资源。"""
    try:
        settings = load_config()
        app.state.settings = settings

        from app.core.database import init_db
        await init_db(settings.db)

        from app.core.redis import init_redis
        await init_redis(settings.redis)

        # LLM 网关初始化（在 DB/Redis 之后）：构造全部 Provider 单例。
        # 不对云端做 ping 预检——LLM 调用是付费网络调用，连通性由首次真实
        # 调用暴露（失败转 BizException），与 DB「启动期预检 fail-fast」对照。
        from app.core.llm.gateway import init_llm

        init_llm(settings.llm)

        yield
    finally:
        from app.core.redis import close_redis
        from app.core.database import dispose_db
        from app.utils.http_client import close_client
        from app.core.llm.gateway import close_llm

        await _cleanup_resources(
            [
                ("redis", close_redis),
                ("database", dispose_db),
                ("http_client", close_client),
                ("llm", close_llm),
            ]
        )


def create_app(*, enable_lifespan: bool = True) -> FastAPI:
    """创建并配置 FastAPI 应用实例。

    Args:
        enable_lifespan: 是否启用真实启动/关闭生命周期。生产与常规启动保持
            True；只验证路由/异常处理器等纯 ASGI 行为的测试可传 False，避免触发
            DB/Redis 等外部依赖初始化。
    """
    settings = get_settings()
    app_cfg = settings.app
    app = FastAPI(
        title=app_cfg.name,
        description="AI Agent 取向的 FastAPI 后端",
        lifespan=lifespan if enable_lifespan else None,
    )
    app.state.settings = settings
    register_routes(app)
    register_exception_handlers(app)
    register_middlewares(app, settings)
    return app


def _resolve_workers(configured: int | None) -> int:
    """解析 worker 进程数。"""
    if configured and configured > 0:
        return configured
    return min(multiprocessing.cpu_count() * 2, 4)


def _resolve_loop(configured: str) -> str:
    """解析事件循环。"""
    if configured == "auto":
        try:
            import uvloop  # noqa: F401
        except ImportError:
            return "asyncio"
        return "uvloop"
    return configured


def run() -> None:
    """按配置驱动启动 uvicorn 服务。"""
    app_cfg = get_settings().app
    reload = app_cfg.env == "dev"
    uvicorn.run(
        app=_APP_IMPORT_STRING,
        factory=True,
        host=app_cfg.host,
        port=app_cfg.port,
        reload=reload,
        workers=None if reload else _resolve_workers(app_cfg.workers),
        loop=_resolve_loop(app_cfg.loop),
        limit_concurrency=app_cfg.limit_concurrency,
        timeout_keep_alive=app_cfg.timeout_keep_alive,
        access_log=app_cfg.access_log,
        log_level=app_cfg.log_level.lower(),
    )
