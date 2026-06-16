"""全局异常处理器。

把各类异常统一转成 ApiResponse 格式的 JSONResponse，并按级写日志（日志分级依据
「是否系统故障」而非「是否出错」）：

- BizException（业务异常）-> INFO：业务异常是预期内的，不算系统故障，不刷 ERROR；
- StarletteHTTPException（含路由 404 与手动 raise）-> WARNING（待实现）；
- RequestValidationError（参数校验失败）-> INFO（待实现）；
- Exception（兜底 500）-> ERROR + 完整堆栈，按 app.debug 脱敏（待实现）。

FastAPI 按异常类型精确派发，注册顺序不影响匹配；由 register_exception_handlers
统一挂载到 app。
"""
from fastapi import HTTPException as FastAPIHTTPException
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logger import logger
from app.exceptions.base import BizException
from app.utils.common import ApiResponse


async def biz_exception_handler(request: Request, exc: BizException) -> JSONResponse:
    """业务异常 -> 统一响应。

    读异常自身的 status_code/errno/message，errno（含默认 0）随响应输出，便于
    前端区分「业务异常（有 errno）」与「HTTP 类异常（无 errno）」。INFO 级日志。
    """
    logger.info(
        "业务异常 | {} {} | status={} errno={} msg={}",
        request.method,
        request.url.path,
        exc.status_code,
        exc.errno,
        exc.message,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=ApiResponse.fail(
            exc.status_code, exc.message, errno=exc.errno
        ).to_payload(),
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """HTTP 异常（含路由 404 与手动 raise HTTPException）-> 统一响应。WARNING 级。

    本 handler 同时挂到 StarletteHTTPException 与 FastAPIHTTPException（见
    register_exception_handlers）：前者兜底路由未命中抛出的 starlette HTTPException，
    后者覆盖 FastAPI 默认的 HTTPException handler——默认 handler 按子类优先匹配，
    必须显式覆盖才能接管手动 ``raise HTTPException``，这是常见易错点。
    """
    logger.warning(
        "HTTP 异常 | {} {} | status={} detail={}",
        request.method,
        request.url.path,
        exc.status_code,
        exc.detail,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=ApiResponse.fail(exc.status_code, str(exc.detail)).to_payload(),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """参数校验失败 -> 统一响应，data 放 pydantic 字段级错误列表便于前端定位。INFO 级。"""
    logger.info(
        "参数校验失败 | {} {} | errors={}",
        request.method,
        request.url.path,
        exc.errors(),
    )
    return JSONResponse(
        status_code=422,
        content=ApiResponse.fail(422, "参数校验失败", data=exc.errors()).to_payload(),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """兜底：未捕获异常 -> 500。按 app.debug 脱敏，ERROR 级 + 完整堆栈（进日志不进响应）。

    - debug=true：message 带原始异常信息（str(exc)），便于开发/排查；
    - debug=false：固定「服务内部错误」，绝不向客户端泄露内部细节（与 logger 的
      diagnose=False 双保险）；
    - 完整堆栈经 logger.exception() 写入日志，响应体不含堆栈。

    BizException / HTTPException / RequestValidationError 已有专用 handler，按
    子类优先匹配，不会落到此兜底处理。
    """
    # 从 app.state 读脱敏开关；settings 由 lifespan 挂载，缺失时默认脱敏（安全优先）
    settings = getattr(request.app.state, "settings", None)
    debug = bool(settings and getattr(settings.app, "debug", False))
    logger.exception(
        "未捕获异常 | {} {} | {}", request.method, request.url.path, exc
    )
    message = str(exc) if debug else "服务内部错误"
    return JSONResponse(
        status_code=500,
        content=ApiResponse.fail(500, message).to_payload(),
    )


def register_exception_handlers(app) -> None:
    """注册全局异常处理器到 app。

    随各类 handler 逐步实现，在此追加 app.add_exception_handler(...)。
    """
    app.add_exception_handler(BizException, biz_exception_handler)
    # 覆盖 FastAPI/Starlette 默认 HTTP 异常处理，统一为 ApiResponse 格式：
    # StarletteHTTPException 兜底路由 404，FastAPIHTTPException 接管手动 raise。
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(FastAPIHTTPException, http_exception_handler)
    # 参数校验失败：data 放字段级错误列表。
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    # 兜底：所有未捕获异常 -> 500（脱敏）。放最后，子类异常已被上面接管。
    app.add_exception_handler(Exception, unhandled_exception_handler)
