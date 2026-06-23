"""业务异常体系。

设计要点：
- ``BizException`` 为业务异常基类，``status_code``/``errno``/``message`` 均为类属性，
  子类只需覆盖这三个值即可定义一类业务异常，零样板；
- 构造时可传 ``message`` / ``errno`` 覆盖默认值——既支持「抛出即用默认消息」，
  也支持「调用方补充具体上下文」；
- errno 命名约定：「HTTP码前缀 + 0」便于记忆（404 -> 10404）；后续业务自定义码
  走 1xxxx 业务段，避免与 HTTP 类混淆。仅约定，不强制校验。

业务层统一 ``raise BizNotFoundError(...)``，由 ``handlers.py`` 的全局处理器转成
统一响应，业务代码不关心 HTTP 序列化细节。
"""


class BizException(Exception):
    """业务异常基类。

    Attributes:
        status_code: HTTP 状态码（响应 code 复用它），默认 400。
        errno: 业务错误细码（默认 0 = 未细分）。
        message: 默认人类可读消息。
    """

    status_code: int = 400
    errno: int = 0
    message: str = "业务异常"

    def __init__(self, message: str | None = None, *, errno: int | None = None) -> None:
        # message / errno 可在实例化时覆盖，便于调用方补充上下文；
        # 未传则沿用类属性默认值。
        if message is not None:
            self.message = message
        if errno is not None:
            self.errno = errno
        super().__init__(self.message)


class BizNotFoundError(BizException):
    """资源不存在（404）。"""

    status_code = 404
    errno = 10404
    message = "资源不存在"


class BizAuthError(BizException):
    """未授权 / 未认证（401）。"""

    status_code = 401
    errno = 10401
    message = "未授权"


class BizForbiddenError(BizException):
    """已认证但无权限（403）。"""

    status_code = 403
    errno = 10403
    message = "禁止访问"


class BizValidationError(BizException):
    """业务层参数校验失败（422）。"""

    status_code = 422
    errno = 10422
    message = "参数校验失败"


# ── 基础设施错误码（2xxxx 段：DB / Redis / ES ...）──────────────────────
# errno 全系统统一为 **int**（与 BizException.errno: int / ApiResponse.errno 对齐，
# 严禁字符串，否则前端拿到的 errno 类型不稳定）。编码分段约定：
# - HTTP 类异常：``1`` + HTTP 码（404 -> 10404、401 -> 10401 ...）；
# - 业务自定义：``1xxxx`` 业务段；
# - 基础设施层故障（DB / 缓存 / 检索引擎等）：``2xxxx`` 段，与上两者互不混淆。
# 集中定义于此外避免魔法数字散落各调用点；新增基础设施错误码在此追加常量。
DB_ERRNO_ENGINE_CREATE_FAILED = 20001  # 数据库引擎创建失败
DB_ERRNO_CONNECT_FAILED = 20002  # 连通性预检失败（启动期 fail-fast）
DB_ERRNO_QUERY_FAILED = 20003  # 查询执行失败（运行期）
DB_ERRNO_DISPOSE_FAILED = 20004  # 连接池释放失败（关闭期）
DB_ERRNO_NOT_INITIALIZED = 20005  # 使用前未初始化

# ── LLM 错误码（2xxxx 段的 21xxx 子段：LLM 网关层）──────────────────────
# LLM 同属横向基础设施层（外部云服务访问封装，与 DB/Redis 在 core/ 下并列），
# 故遵循「基础设施层故障走 2xxxx 段」约定。DB 占 20xxx（20001-20005），LLM
# 用 21xxx 子段与 DB 区分，Redis 未来可用 22xxx——按基础设施子类分段互不混淆。
LLM_ERRNO_NOT_INITIALIZED = 21001  # LLM 网关未初始化即调用（init_llm 未执行 / providers 空）
LLM_ERRNO_PROVIDER_NOT_FOUND = 21002  # 请求的 Provider 名不在配置 providers 字典中
LLM_ERRNO_CALL_FAILED = 21003  # 模型调用失败（网络异常 / 超时 / 非 2xx 响应 / 重试用尽）
LLM_ERRNO_INVALID_RESPONSE = 21004  # 响应解析失败（结构异常 / 必需字段缺失）
LLM_ERRNO_CAPABILITY_NOT_CONFIGURED = 21005  # Provider 未声明请求的 AI 能力模型
LLM_ERRNO_INVALID_INPUT = 21006  # Embedding / 多模态输入不合法或超过安全限制

# ── Skill 错误码（2xxxx 段的 23xxx 子段：skill 注册中心层）──────────────
# skill 注册中心同属横向基础设施层（core/skills/，与 DB/Redis/LLM 并列），
# 故遵循「基础设施层故障走 2xxxx 段」约定。DB 用 20xxx、LLM 用 21xxx、Redis
# 预留 22xxx，skill 用 23xxx 子段，按基础设施子类分段互不混淆。
SKILL_ERRNO_NOT_INITIALIZED = 23001  # 注册中心未初始化 / 关闭 / 空索引
SKILL_ERRNO_NOT_FOUND = 23002  # 请求的 skill 名不在注册索引中
SKILL_ERRNO_LOAD_FAILED = 23003  # SKILL.md 加载或解析失败
SKILL_ERRNO_DISABLED = 23004  # skill 存在但 enabled=false
SKILL_ERRNO_RUN_FAILED = 23005  # skill 执行失败（LLM 调用失败等）

# ── Milvus 错误码（2xxxx 段的 24xxx 子段：向量数据库层）──────────────
MILVUS_ERRNO_NOT_INITIALIZED = 24001  # 客户端未初始化或已降级
MILVUS_ERRNO_CONNECT_FAILED = 24002  # 客户端构造或启动连通性探测失败
MILVUS_ERRNO_OPERATION_FAILED = 24003  # collection / 数据操作失败
MILVUS_ERRNO_INVALID_RESPONSE = 24004  # SDK 返回结构缺失必需字段
