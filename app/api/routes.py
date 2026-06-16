"""路由聚合层：集中注册所有 API 路由。

职责单一——只负责把各路由模块的 router 挂到 app 上（include_router 调用）。
由 ``app/startup.py`` 的 ``register_routers`` 转调，保持 startup 作为
「所有注册点单一入口」的约定，本文件专职路由清单。

新增路由约定：
- 基础设施端点（健康检查等，无版本前缀）直接在 ``register_routes`` 内注册；
- 业务路由按版本归组，新增 ``register_vN_routes(app)`` 并在 ``register_routes`` 中调用，
  各模块路由放 ``app/api/vN/`` 目录。
"""
from fastapi import FastAPI

from app.api.health import router as health_router


def register_routes(app: FastAPI) -> None:
    """注册全部 API 路由。

    当前仅挂载基础设施路由（健康检查）；业务路由待版本目录就绪后，
    通过 ``register_v1_routes`` 等版本化函数挂载（见下方扩展点）。
    """
    # 基础设施路由（无版本前缀：探针/指标等固定路径）
    app.include_router(health_router)

    # ── 业务路由扩展点（按版本聚合）────────────────────────────────
    # 待 app/api/v1/ 下就绪业务路由模块后，在此挂载，例如：
    #     from app.api.v1 import register_v1_routes
    #     register_v1_routes(app)
    # 其中 register_v1_routes 内部按 prefix="/v1/<biz>" 逐个 include_router
    # （见「案例：register_v1_routes」范式）。
    # ──────────────────────────────────────────────────────────────
