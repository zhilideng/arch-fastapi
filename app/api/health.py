"""健康检查路由。

生产级最小可验证端点：供负载均衡 / K8s 探针判断服务存活。
"""
from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """存活探针：返回服务状态与当前环境。"""
    return {"status": "ok", "env": get_settings().app.env}
