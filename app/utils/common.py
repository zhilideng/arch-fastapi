"""统一响应模型。

所有 API（正常与异常路径）共用此结构，保证对调用方响应一致、可预测：

    {
      "code": <HTTP 状态码>,
      "message": <人类可读消息>,
      "data": <业务数据，可为 null>,
      "errno": <业务错误细码，可选；仅业务异常响应输出>
    }

设计要点：
- code 复用 HTTP 状态码，保持 REST 语义；
- errno 用 Optional[int]，序列化时经 exclude_none 排除：正常响应与 HTTP 类异常响应
  不含此字段，仅 BizException 抛出时（fail(errno=...)）才出现，保持响应精简；
- ok()/fail() 两个类方法构造器，统一全项目构造方式，避免各处手拼 dict。
"""
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一响应封装。

    泛型 T 约束 data 类型，便于 OpenAPI 生成与静态检查；实际使用时多作为
    非泛型 ApiResponse（data 为 Any）。
    """

    code: int  # HTTP 状态码（成功 = 200）
    message: str  # 人类可读消息
    data: Optional[T] = None  # 业务数据；无数据时为 None（序列化为 null）
    errno: Optional[int] = None  # 业务错误细码；仅业务异常响应输出

    @classmethod
    def ok(cls, data: Any = None, message: str = "ok") -> "ApiResponse[Any]":
        """构造成功响应：code 固定 200，message 默认 'ok' 可覆盖。"""
        return cls(code=200, message=message, data=data)

    @classmethod
    def fail(
        cls,
        code: int,
        message: str,
        data: Any = None,
        errno: Optional[int] = None,
    ) -> "ApiResponse[Any]":
        """构造失败响应：errno 仅业务异常传值，序列化时经 to_payload() 条件输出。"""
        return cls(code=code, message=message, data=data, errno=errno)

    def to_payload(self) -> dict[str, Any]:
        """序列化为响应 dict。

        与 pydantic 默认 ``model_dump`` 的区别（核心规则）：
        - code/message/data **始终输出**（data 为 None 时输出 null，保证前端
          总能读 ``resp.data``，结构一致）；
        - errno **仅在非 None 时输出**（业务异常才带，正常/HTTP 类异常响应
          不含此字段，保持精简）。

        故不能用 ``exclude_none=True``（它会连 data=None 一起排除，与上面矛盾）；
        handler 与路由统一调用本方法构造响应体。
        """
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "data": self.data,
        }
        if self.errno is not None:
            payload["errno"] = self.errno
        return payload
