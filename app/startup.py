"""启动注册：集中加载配置、注册路由与中间件。

新增模块的注册点统一放此处，保持 factory.create_app 简洁。
"""
from fastapi import FastAPI
from app.api.health import router as health_router
from app.core.config import Settings, get_settings
from app.core.logger import logger, setup_logging


def load_config() -> Settings:
    """启动时加载配置（fail-fast）。

    - 触发 get_settings()：若 APP_ENV 非法 / yaml 缺失 / 字段校验失败，
      在此直接抛错，进程启动失败，而非拖到运行时第一次请求才暴雷；
    - 初始化日志（按 settings.app.log_level）；
    - 打印生效配置，便于启动期排查（当前 app 段无敏感字段，可直接打印）。
    """
    settings = get_settings()
    setup_logging(level=settings.app.log_level)
    app_cfg = settings.app
    logger.info(
        "配置加载完成 | env={} | name={} | host={} | port={} | debug={} | log_level={}",
        app_cfg.env, app_cfg.name, app_cfg.host, app_cfg.port,
        app_cfg.debug, app_cfg.log_level,
    )
    return settings


def register_routers(app: FastAPI) -> None:
    """注册 API 路由。"""
    app.include_router(health_router)


def register_middlewares(app: FastAPI) -> None:
    """注册中间件（JWT / TraceId / 限流等待后续实现）。"""
    # TODO: 接入 middleware/ 下的各中间件
    return None

