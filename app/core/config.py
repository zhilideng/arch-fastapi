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

_ENV_CHOICES = {"dev", "test", "prod"}


class AppSettings(BaseModel):
    name: str = "arch-fastapi"
    env: str = "dev"
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    log_level: str = "INFO"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    app: AppSettings = AppSettings()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        env = os.getenv("APP_ENV", "dev")
        if env not in _ENV_CHOICES:
            raise ValueError(
                f"APP_ENV 非法: {env!r}，允许 {sorted(_ENV_CHOICES)}"
            )
        yaml_path = Path(__file__).resolve().parents[2] / "configs" / f"{env}.yaml"
        if not yaml_path.exists():
            raise FileNotFoundError(f"环境配置文件缺失: {yaml_path}")
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls, yaml_file=yaml_path),
            file_secret_settings,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
