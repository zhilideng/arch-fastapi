from app.core.config import AppSettings


def test_app_settings_defaults():
    s = AppSettings()
    assert s.name == "arch-fastapi"
    assert s.env == "dev"
    assert s.host == "0.0.0.0"
    assert s.port == 8000
    assert s.debug is False
    assert s.log_level == "INFO"


import pytest

from app.core.config import Settings


def test_settings_loads_dev_yaml_by_default(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    s = Settings()
    assert s.app.env == "dev"
    assert s.app.port == 8000
    assert s.app.debug is True
    assert s.app.log_level == "DEBUG"


def test_settings_switches_to_test_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    s = Settings()
    assert s.app.env == "test"
    assert s.app.debug is False
    assert s.app.log_level == "INFO"


def test_settings_env_var_overrides_yaml(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("APP__PORT", "9000")
    monkeypatch.setenv("APP__DEBUG", "false")
    s = Settings()
    assert s.app.port == 9000
    assert s.app.debug is False


def test_settings_rejects_invalid_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    with pytest.raises(ValueError):
        Settings()
