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
- ``AppSettings`` —— 应用通用配置（名称、环境、host/port、debug、log_level）。
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
