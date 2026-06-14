"""配置段模型集合（配置 schema 层）。

本包是配置 schema 层，与 ``app/core/config.py`` 的「加载机制」分离：
本包只声明有哪些配置段、字段、类型与默认值。所有配置段 class 统一收敛在
``sections`` 模块，便于集中维护。

组织约定：
- 配置段 class 统一放 ``sections`` 模块，不再按段拆分多文件；
- 敏感字段（密钥、令牌、连接串中的口令等）一律用 ``SecretStr``，且只经
  环境变量注入，不写入 yaml；
- 新增配置段后，需在 ``app/core/config.py`` 的 ``Settings`` 根配置里聚合
  对应字段，并在本 ``__init__`` 导出。

当前已导出：
- ``AppSettings`` —— 应用通用配置（名称、环境、host/port、debug、log_level）。
"""
from app.core.settings.settings import AppSettings

__all__ = ["AppSettings"]
