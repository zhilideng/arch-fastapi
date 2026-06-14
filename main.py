"""应用入口。

直接 `python main.py` 或 `uvicorn main:app` 启动。
host / port / debug / log_level 全部来自配置中心，不硬编码。
"""
import uvicorn

from app.core.config import get_settings
from app.factory import create_app

# 模块级 app：供 `uvicorn main:app` 加载
app = create_app()


def main() -> None:
    """以配置驱动启动 uvicorn 服务。"""
    app_cfg = get_settings().app
    uvicorn.run(
        "main:app",
        host=app_cfg.host,
        port=app_cfg.port,
        reload=app_cfg.debug,  # 仅开发环境热重载
        log_level=app_cfg.log_level.lower(),
    )


if __name__ == "__main__":
    main()
