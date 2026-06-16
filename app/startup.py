"""启动注册：集中加载配置、注册路由与中间件。

新增模块的注册点统一放此处，保持 factory.create_app 简洁。
"""
from fastapi import FastAPI
from app.api.routes import register_routes
from app.core.config import Settings, get_settings
from app.core.logger import intercept_uvicorn_logs, logger, setup_logging
from app.exceptions import register_exception_handlers as register_exception
from app.middleware.cors import setup_cors

def load_config() -> Settings:
    """启动时加载配置（fail-fast）。

    - 触发 get_settings()：若 APP_ENV 非法 / yaml 缺失 / 字段校验失败，
      在此直接抛错，进程启动失败，而非拖到运行时第一次请求才暴雷；
    - 初始化日志（按 settings.app.log_level）；
    - 打印生效配置，便于启动期排查（当前 app 段无敏感字段，可直接打印）。
    """
    settings = get_settings()
    setup_logging(settings.logging)
    # 把 uvicorn 日志接入 loguru，应用日志与访问/错误日志格式统一
    intercept_uvicorn_logs(level=settings.app.log_level)
    app_cfg = settings.app
    logger.info(
        "配置加载完成 | env={} | name={} | host={} | port={} | debug={} | log_level={}",
        app_cfg.env, app_cfg.name, app_cfg.host, app_cfg.port,
        app_cfg.debug, app_cfg.log_level,
    )
    return settings


def register_routers(app: FastAPI) -> None:
    """注册 API 路由。

    薄封装：转调 ``app.api.routes.register_routes``，保持本文件作为
    「所有注册点单一清单」的风格，与 register_exception_handlers / register_middlewares 同形。
    实际路由清单（include_router 调用）集中在 ``app/api/routes.py``。
    """
    register_routes(app)


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器（统一响应格式 + 500 兜底脱敏）。

    薄封装：内部转调 app.exceptions 的实现，保持本文件作为「所有注册点单一清单」
    的风格，与 register_routers / register_middlewares 同形。
    """
    register_exception(app)


def register_middlewares(app: FastAPI) -> None:
    """注册中间件（作为「路由→异常→中间件」注册链的最后阶段）。

    已接入：
    - CORS 跨域中间件（配置驱动，见 ``app/middleware/cors.py``）；

    待加：
    - JWT 认证 / TraceId / 限流等中间件。
    """
    setup_cors(app)
