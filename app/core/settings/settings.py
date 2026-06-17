"""配置段模型集合（配置 schema 层）。

本文件集中定义所有业务域的配置模型（Pydantic BaseModel），与
``app/core/config.py`` 的「加载机制」职责分离：这里只声明有哪些配置段、
字段、类型与默认值，不关心多源加载与优先级。

组织约定：
- 所有配置段 class 统一收敛于本文件，不再按段拆分多文件；
- 敏感字段（密钥、令牌、连接串中的口令等）一律用 ``SecretStr``，且只经
  环境变量注入，不写入 yaml；
- 新增配置段后，需在 ``app/core/config.py`` 的 ``Settings`` 根配置里聚合
  对应字段。

当前已定义：
- ``AppSettings`` —— 应用通用配置（名称、环境、host/port、debug、log_level）；
- ``LoggingSettings`` —— 日志配置（级别/序列化/目录/轮转/保留/压缩/diagnose/enqueue）；
- ``DBSettings`` —— 数据库配置（连接串/连接池/echo）；
- ``RedisSettings`` —— Redis 缓存配置（url/db/max_connections/decode_responses/encoding）。

注：HTTP 客户端参数与 CORS 跨域策略当前均写死（分别见 ``app/utils/http_client.py``
与 ``app/middleware/cors.py``），不进配置；将来需按环境调优时再改配置驱动。
"""
from pydantic import BaseModel


class AppSettings(BaseModel):
    """应用通用配置（对应 yaml 的 app 段）。

    这些字段非敏感，可入 yaml；后续涉及 DB / JWT / LLM 等敏感项时，
    应新增独立配置段并使用 SecretStr，且仅经环境变量注入。
    """

    name: str = "arch-fastapi111"  # 应用名称
    env: str = "dev"  # 当前运行环境标识，应与所选 yaml 文件名一致
    host: str = "0.0.0.0"  # 服务监听地址
    port: int = 8000  # 服务监听端口
    debug: bool = False  # 是否开启调试模式（生产环境必须为 False）
    log_level: str = "INFO"  # 日志级别
    # —— uvicorn 运行期调优（生产相关，非敏感，可入 yaml）——
    workers: int | None = None  # worker 进程数；None=自动(min(cpu*2,4))，显式数字则用该值（dev reload 时忽略）
    loop: str = "auto"  # 事件循环：auto=优先 uvloop 回退 asyncio；亦可显式 uvloop/asyncio
    limit_concurrency: int | None = None  # 最大并发连接数（背压保护）；None=不限
    timeout_keep_alive: int = 5  # keep-alive 超时秒数
    access_log: bool = False  # uvicorn 自带访问日志：已由 AccessLog 中间件接管（见 app/middleware/access_log.py，能带 request_id），此处关闭避免重复打印


class LoggingSettings(BaseModel):
    """日志配置段（对应 yaml 的 logging 段）。

    驱动 ``app/core/logger.py`` 的 sink/格式/轮转行为。``level`` 与
    ``AppSettings.log_level`` 分离：本字段管 logger，``AppSettings.log_level``
    管 uvicorn（server.py），两者在各 yaml 里分别配置但取值保持一致。
    """

    level: str = "INFO"  # logger 级别
    serialize: bool = True  # 统一 JSON 输出（全环境，便于聚合系统解析）
    dir: str = "logs"  # 日志目录（相对项目根）
    rotation: str = "00:00"  # 按天轮转（每天 00:00 触发；如需可改大小如 "20 MB"）
    retention: str = "30 days"  # 保留时长
    compression: str = "zip"  # 归档压缩
    diagnose: bool = False  # 异常栈展开变量（dev 开 / prod 关，防敏感信息泄露）
    backtrace: bool = True  # 异常完整回溯
    enqueue: bool = True  # 多进程安全队列（prod multi-worker 必须）


class DBSettings(BaseModel):
    """数据库配置段（对应 yaml 的 db 段）。

    驱动 ``app/core/database.py`` 的 SQLAlchemy 引擎与连接池行为。
    URL 敏感（含口令），仅经环境变量注入（DB__URL——env_prefix 空，故 db 段变量名是 DB__URL 而非 APP__DB__URL），yaml 留占位。
    """

    url: str = "postgresql+asyncpg://user:pass@localhost:5432/app"  # PostgreSQL async 连接串（敏感，真值走环境变量）
    pool_size: int = 10  # 连接池核心连接数
    max_overflow: int = 20  # 连接池峰值溢出数
    pool_recycle: int = 3600  # 连接回收秒数（防 DB 断开连接）
    echo: bool = False  # 是否打印 SQL（dev 开，prod 关）


class RedisSettings(BaseModel):
    """Redis 缓存配置段（对应 yaml 的 redis 段）。

    驱动 ``app/core/redis.py`` 的连接池与超时行为。
    """

    url: str = "redis://localhost:6379/0"  # Redis 连接 URL
    db: int = 0  # 数据库编号（url 路径优先，未指定时用本值）
    max_connections: int = 20  # 连接池最大连接数
    decode_responses: bool = True  # 是否自动解码响应为 str（存对象时需 JSON 序列化）
    encoding: str = "utf-8"  # 字符编码（decode_responses=True 时生效）
