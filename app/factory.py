"""FastAPI 应用工厂。

集中创建 FastAPI 实例：通过 lifespan 在启动时加载配置（fail-fast），
并注册路由、中间件。业务代码与 uvicorn 均通过 create_app() 获取应用。
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import startup


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时加载配置并挂到 app.state，关闭时清理资源。"""
    # 启动：加载配置（失败则进程随启动失败而退出）
    settings = startup.load_config()
    app.state.settings = settings
    yield
    # 关闭：待加 DB / Redis 连接清理


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用实例。"""
    app = FastAPI(
        title="arch-fastapi",
        description="AI Agent 取向的 FastAPI 后端",
        lifespan=lifespan,
    )
    startup.register_routers(app)
    startup.register_middlewares(app)
    return app


