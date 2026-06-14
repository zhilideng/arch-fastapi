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

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

# 各配置段模型统一收纳于 settings/ 包，按文件拆分避免本文件臃肿；
# 此处 re-export 以保持 ``from app.core.config import AppSettings`` 的对外兼容。
from app.core.settings import AppSettings

# 允许的环境标识，与 configs/ 下的 yaml 文件名一一对应
_ENV_CHOICES = ("dev", "test", "prod")
# 未显式指定 APP_ENV 时的默认环境
_DEFAULT_ENV = "dev"


def _project_root() -> Path:
    """定位项目根目录。

    从本文件向上查找最近的「项目根标记」目录（含 ``.git`` 或
    ``requirements.txt``），抗 ``config.py`` 文件位置变更（如后续重构为
    ``app/core/config/`` 包时不会因深度变化而指错位置）；若均未命中，
    退回到基于当前文件上溯两级的旧式锚点，保证总有兜底。
    """
    cur = Path(__file__).resolve().parent
    for anc in (cur, *cur.parents):
        if (anc / ".git").exists() or (anc / "requirements.txt").exists():
            return anc
    return Path(__file__).resolve().parents[2]  # 兜底：上溯两级到项目根


def _resolve_configs_dir() -> Path:
    """解析 configs 目录路径（部署期可覆盖）。

    优先级：
    1) 环境变量 ``APP_CONFIG_DIR`` —— 绝对路径直接用；相对路径基于项目根；
       供容器 / 生产环境把 yaml 挂载到任意目录（如 /etc/<app>、ConfigMap）。
    2) 默认 ``<项目根>/configs``。

    设计动机：配置文件位置是「部署期变量」而非「编译期常量」，故不应硬编码
    在代码里，而应由环境变量注入；项目根则用结构标记定位而非脆弱的上溯层级。
    """
    env_dir = os.getenv("APP_CONFIG_DIR")
    if env_dir:
        p = Path(env_dir).expanduser()
        return p if p.is_absolute() else _project_root() / p
    return _project_root() / "configs"


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
        # 定位 configs/{env}.yaml：configs 目录经 _resolve_configs_dir() 解析，
        # 可被环境变量 APP_CONFIG_DIR 覆盖（容器/生产挂载入口）。
        yaml_path = _resolve_configs_dir() / f"{env}.yaml"
        if not yaml_path.exists():
            raise FileNotFoundError(
                f"环境配置文件缺失: {yaml_path}"
                f"（configs 目录可经环境变量 APP_CONFIG_DIR 覆盖）"
            )
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
