"""全局异常体系包入口。

统一导出业务异常类（与异常处理器注册函数，后者在 handlers 实现后补导出），
业务层只需：
    from app.exceptions import BizNotFoundError
即可使用，无需关心内部文件组织。
"""
from app.exceptions.base import (
    DB_ERRNO_CONNECT_FAILED,
    DB_ERRNO_DISPOSE_FAILED,
    DB_ERRNO_ENGINE_CREATE_FAILED,
    DB_ERRNO_NOT_INITIALIZED,
    DB_ERRNO_QUERY_FAILED,
    LLM_ERRNO_CALL_FAILED,
    LLM_ERRNO_INVALID_RESPONSE,
    LLM_ERRNO_NOT_INITIALIZED,
    LLM_ERRNO_PROVIDER_NOT_FOUND,
    BizAuthError,
    BizException,
    BizForbiddenError,
    BizNotFoundError,
    BizValidationError,
)
from app.exceptions.handlers import register_exception_handlers

__all__ = [
    "BizException",
    "BizNotFoundError",
    "BizAuthError",
    "BizForbiddenError",
    "BizValidationError",
    "DB_ERRNO_ENGINE_CREATE_FAILED",
    "DB_ERRNO_CONNECT_FAILED",
    "DB_ERRNO_QUERY_FAILED",
    "DB_ERRNO_DISPOSE_FAILED",
    "DB_ERRNO_NOT_INITIALIZED",
    "LLM_ERRNO_NOT_INITIALIZED",
    "LLM_ERRNO_PROVIDER_NOT_FOUND",
    "LLM_ERRNO_CALL_FAILED",
    "LLM_ERRNO_INVALID_RESPONSE",
    "register_exception_handlers",
]
