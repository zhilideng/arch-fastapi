"""配置中心（多源加载）。

技术选型：YAML + Pydantic Settings + 环境变量覆盖。
- YAML：按 APP_ENV 选择 configs/{dev,test,prod}.yaml 作为基础配置；
- Pydantic Settings：用 BaseSettings 做类型化、校验化的配置模型；
- 环境变量覆盖：优先级为 初始化参数 > 环境变量 > .env > yaml > 模型默认值；
  嵌套字段用双下划线分隔，例如 APP__PORT 覆盖 app.port。

业务代码统一通过 get_settings() 获取配置，不直接实例化 Settings。
"""
import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

# 允许的环境标识，与 configs/ 下的 yaml 文件名一一对应
_ENV_CHOICES = ("dev", "test", "prod")
# 未显式指定 APP_ENV 时的默认环境
_DEFAULT_ENV = "dev"


class AppSettings(BaseModel):
    """应用通用配置（对应 yaml 的 app 段）。

    这些字段非敏感，可入 yaml；后续涉及 DB / JWT / LLM 等敏感项时，
    应新增独立配置段并使用 SecretStr，且仅经环境变量注入。
    """

    name: str = "arch-fastapi"  # 应用名称
    env: str = "dev"  # 当前运行环境标识，应与所选 yaml 文件名一致
    host: str = "0.0.0.0"  # 服务监听地址
    port: int = 8000  # 服务监听端口
    debug: bool = False  # 是否开启调试模式（生产环境必须为 False）
    log_level: str = "INFO"  # 日志级别


class Settings(BaseSettings):
    """根配置，聚合各配置段。

    通过 settings_customise_sources 声明多源加载优先级：
    初始化参数 > 环境变量 > .env > yaml(按 APP_ENV 选) > Secret 文件。
    """

    model_config = SettingsConfigDict(
        env_file=".env",  # 从项目根的 .env 读取（不入库，见 .gitignore）
        env_file_encoding="utf-8",
        env_nested_delimiter="__",  # 嵌套分隔符：APP__PORT -> app.port
        extra="ignore",  # 忽略模型未声明的字段（容器注入的无关 env 不会报错）
    )

    app: AppSettings = AppSettings()  # 应用通用配置段

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """定制配置源及其优先级（返回顺序即从高到低）。

        1) init_settings       —— 构造时传入的参数，优先级最高；
        2) env_settings        —— 系统环境变量（如 APP__PORT、APP_ENV）；
        3) dotenv_settings     —— .env 文件；
        4) yaml                —— 按 APP_ENV 选择的 configs/{env}.yaml；
        5) file_secret_settings —— Secret 文件，当前未使用。

        同时在此完成环境校验与 yaml 缺失的 fail-fast：
        - APP_ENV 非法（不在 dev/test/prod）-> ValueError；
        - 对应 yaml 文件缺失 -> FileNotFoundError。
        """
        # 读取目标环境，缺省取 dev
        env = os.getenv("APP_ENV", _DEFAULT_ENV)
        if env not in _ENV_CHOICES:
            raise ValueError(
                f"APP_ENV 非法: {env!r}，允许 {list(_ENV_CHOICES)}"
            )
        # 定位 configs/{env}.yaml：config.py 上溯两级到项目根，再进 configs/
        yaml_path = Path(__file__).resolve().parents[2] / "configs" / f"{env}.yaml"
        if not yaml_path.exists():
            raise FileNotFoundError(f"环境配置文件缺失: {yaml_path}")
        # 返回优先级从高到低的配置源列表
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls, yaml_file=yaml_path),
            file_secret_settings,
        )


@lru_cache
def get_settings() -> Settings:
    """获取全局配置单例。

    使用 lru_cache 缓存，进程内只加载一次；如需运行时重载
    （例如测试场景），调用 get_settings.cache_clear() 清除缓存。
    """
    return Settings()
