"""FastAPI 应用工厂。

集中创建 FastAPI 实例：通过 lifespan 在启动时加载配置（fail-fast），
并注册路由、中间件。业务代码与 uvicorn 均通过 create_app() 获取应用。
"""
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import startup
from app.core.config import get_settings
from app.core.logger import logger


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
    """应用生命周期：启动时加载配置并挂到 app.state，关闭时清理资源。"""
    try:
        # 启动：加载配置（失败则进程随启动失败而退出）
        settings = startup.load_config()
        app.state.settings = settings
        # 初始化数据库连接池
        from app.core.database import init_db
        await init_db(settings.db)
        # 初始化 Redis 连接池
        from app.core.redis import init_redis
        await init_redis(settings.redis)
        yield
    finally:
        # 关闭：逐项释放资源。任一项失败都不阻断后续清理，避免连接池泄漏。
        from app.core.redis import close_redis
        from app.core.database import dispose_db
        from app.utils.http_client import close_client

        await _cleanup_resources(
            [
                ("redis", close_redis),
                ("database", dispose_db),
                ("http_client", close_client),
            ]
        )


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用实例。"""
    app_cfg = get_settings().app
    app = FastAPI(
        title=app_cfg.name,
        description="AI Agent 取向的 FastAPI 后端",
        lifespan=lifespan,
    )
    startup.register_routers(app)
    startup.register_exception_handlers(app)
    startup.register_middlewares(app)
    return app
