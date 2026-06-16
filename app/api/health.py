"""健康检查路由。

生产级最小可验证端点：供负载均衡 / K8s 探针判断服务存活。
"""
from fastapi import APIRouter

from app.core.config import get_settings
from app.utils.common import ApiResponse

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """存活探针：返回统一响应格式的服务状态与当前环境。"""
    return ApiResponse.ok({"env": get_settings().app.env}).to_payload()
