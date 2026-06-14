"""结构化日志（基于 loguru）。

提供全局 logger 与 setup_logging：按配置级别输出到控制台，
生产环境关闭 diagnose，防止异常栈展开时泄露局部变量值（敏感信息）。
"""
import sys

from loguru import logger

# 默认日志格式：时间 | 级别 | 模块:函数:行号 - 消息
_DEFAULT_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)


def setup_logging(level: str = "INFO") -> None:
    """初始化全局日志配置。

    - 移除 loguru 默认 handler，避免重复输出；
    - 输出到 stdout，按 level 过滤；
    - diagnose=False：生产环境异常栈不展开局部变量值，避免敏感信息泄露。
    """
    logger.remove()
    logger.add(
        sys.stdout,
        level=level.upper(),
        format=_DEFAULT_FORMAT,
        backtrace=True,
        diagnose=False,
    )


__all__ = ["logger", "setup_logging"]
