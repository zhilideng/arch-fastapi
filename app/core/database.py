"""SQLAlchemy 异步数据层核心。

提供进程级 async engine 单例、sessionmaker 工厂、以及 FastAPI 依赖注入。
配置驱动，连接参数来自 DBSettings。

设计原则：
- 进程级单例：engine 和 sessionmaker 全局唯一，复用连接池（参考 http_client.py）；
- 配置驱动：所有连接参数从 DBSettings 读取，便于按环境调优；
- 失败统一：数据库异常 raise BizException(...)，由全局 handler 转统一响应；
- 生命周期：init_db 在 factory.py lifespan 启动时调用，dispose_db 关闭时调用。
"""
from functools import lru_cache
from typing import AsyncGenerator

from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from loguru import logger

from app.core.settings import DBSettings
from app.exceptions.base import BizException


# 模块级变量（惰性初始化）
_engine = None
_async_session_maker = None


def _create_engine(db_settings: DBSettings):
    """创建 SQLAlchemy 异步引擎。

    参数来自 DBSettings：
    - url：PostgreSQL async 连接串（如 postgresql+asyncpg://user:pass@host:5432/db）；
    - pool_size：连接池核心连接数（默认 10）；
    - max_overflow：连接池峰值溢出数（默认 20）；
    - pool_recycle：连接回收秒数（默认 3600，防 DB 断开连接）；
    - echo：是否打印 SQL（dev 开，prod 关）。

    注意：SQLite in-memory 测试时用 NullPool（连接池无意义）。
    """
    url = db_settings.url
    # SQLite in-memory 用 NullPool（测试环境），不传 pool_size/max_overflow
    if url.startswith("sqlite"):
        engine_args = {
            "poolclass": NullPool,
            "pool_recycle": db_settings.pool_recycle,
            "pool_pre_ping": True,
            "echo": db_settings.echo,
        }
        pool_size = None
        max_overflow = None
    else:
        engine_args = {
            "pool_size": db_settings.pool_size,
            "max_overflow": db_settings.max_overflow,
            "pool_recycle": db_settings.pool_recycle,
            "pool_pre_ping": True,
            "echo": db_settings.echo,
        }
        pool_size = db_settings.pool_size
        max_overflow = db_settings.max_overflow

    try:
        engine = create_async_engine(url, **engine_args)
        logger.info(
            "数据库引擎创建成功 | url={} | pool_size={} | max_overflow={}",
            url.split("@")[-1] if "@" in url else url,  # 脱敏打印
            pool_size,
            max_overflow,
        )
        return engine
    except Exception as exc:
        logger.error("数据库引擎创建失败: {}", exc)
        raise BizException(
            message="数据库引擎创建失败",
            errno="DB_ENGINE_CREATE_FAILED",
        ) from exc


def _create_session_maker(engine):
    """创建 async_sessionmaker 工厂。

    使用 AsyncSession，并开启 expire_on_commit=False（避免访问已提交对象
    触发懒加载异常，FastAPI 异步场景推荐）。
    """
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


def get_engine():
    """获取数据库引擎单例（进程级唯一）。

    注意：首次调用前必须先调用 init_db(db_settings)，否则返回 None。
    此设计供 factory.py lifespan 显式初始化后，其他模块通过此函数获取。
    """
    return _engine


def get_session_maker():
    """获取 sessionmaker 工厂（进程级唯一）。

    注意：首次调用前必须先调用 init_db(db_settings)，否则返回 None。
    供 get_db() 依赖内部使用，或直接用于测试场景手动创建 session。
    """
    return _async_session_maker


def init_db(db_settings: DBSettings):
    """初始化数据库连接池（lifespan 启动时调用）。

    创建全局 engine 和 sessionmaker，进程内复用。
    可重复调用（幂等），已初始化则跳过。
    """
    global _engine, _async_session_maker

    if _engine is not None:
        logger.warning("数据库引擎已初始化，跳过重复初始化")
        return

    _engine = _create_engine(db_settings)
    _async_session_maker = _create_session_maker(_engine)
    logger.info("数据库初始化完成")


async def dispose_db():
    """释放数据库连接池（lifespan 关闭时调用）。

    关闭 engine，释放所有连接。
    可重复调用（幂等），已释放则跳过。
    """
    global _engine, _async_session_maker

    if _engine is None:
        logger.warning("数据库引擎未初始化，无需释放")
        return

    try:
        await _engine.dispose()
        logger.info("数据库连接池释放完成")
    except Exception as exc:
        logger.error("数据库连接池释放失败: {}", exc)
        raise BizException(
            message="数据库连接池释放失败",
            errno="DB_DISPOSE_FAILED",
        ) from exc
    finally:
        _engine = None
        _async_session_maker = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖注入：获取 async session。

    用法：
        @app.get("/users")
        async def list_users(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(User))
            return result.scalars().all()

    每个请求独立 session，请求结束后自动关闭（确保事务回滚或提交）。
    """
    session_maker = get_session_maker()
    if session_maker is None:
        raise BizException(
            message="数据库未初始化",
            errno="DB_NOT_INITIALIZED",
        )

    async with session_maker() as session:
        try:
            yield session
        finally:
            # sessionmaker 的 async context 自动关闭，无需显式调用
            # 这里保留 finally 块便于后续添加清理逻辑（如事务回滚）
            pass
