"""结构化日志（基于 loguru）。

提供全局 logger、setup_logging 与 intercept_uvicorn_logs：
- setup_logging：按配置级别输出到 stdout，生产关闭 diagnose 防敏感信息泄露；
- intercept_uvicorn_logs：把 uvicorn 的标准库 logging 接入 loguru，
  使应用日志与 uvicorn 访问 / 错误日志格式统一，便于生产排查。
"""
import logging
import sys

from loguru import logger

# 默认日志格式：时间 | 级别 | 模块:函数:行号 - 消息
_DEFAULT_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)


class InterceptHandler(logging.Handler):
    """标准库 logging -> loguru 桥接 handler。

    uvicorn 默认走标准库 logging，与 loguru 输出割裂；用此 handler 把
    uvicorn 的日志记录转发给 loguru，统一格式与目的地。
    """

    def emit(self, record: logging.LogRecord) -> None:
        # 把标准库级别名映射到 loguru 级别；未知级别降级为数值级别
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        # 回溯栈帧找到真正的日志发起者，让 loguru 显示正确的模块/函数/行号
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def intercept_uvicorn_logs(level: str = "INFO") -> None:
    """接管 uvicorn 三类日志，接入 loguru 统一输出。

    将 uvicorn / uvicorn.error / uvicorn.access 的 handler 替换为
    InterceptHandler，并关闭向上传播（propagate=False），避免重复打印。
    """
    handler = InterceptHandler()
    logging.basicConfig(handlers=[handler], level=level.upper(), force=True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        target = logging.getLogger(name)
        target.handlers = [handler]
        target.propagate = False


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


__all__ = ["logger", "setup_logging", "intercept_uvicorn_logs", "InterceptHandler"]
