# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目当前状态（务必先读）

**配置中心已实现**：`app/core/config.py`（pydantic-settings + yaml + .env + 环境变量多源，含 `Settings`/`AppSettings`/`get_settings`，带 yaml 缺失 fail-fast）、`configs/{dev,test,prod}.yaml`、`.env.example`、`.gitignore`、`requirements.txt` 均就位；`tests/test_config.py` 7 个测试全绿；仓库已 `git init`（main 分支）。

其余 `app/**/*.py`（除 `core/config.py`）仍为空，`main.py` 仍是 PyCharm 默认模板，`app/factory.py` / `app/startup.py` 待实现——配置中心之外的启动链尚未打通。下一步应推进 `app/factory.py`（FastAPI 应用工厂）与 `main.py` 真正入口。

## 目标架构（AI Agent 取向的 FastAPI 后端，来自 README）

采用**分层架构**，依赖自上而下单向流动，禁止反向依赖（如 repository 不得 import service）：

```
api/        Controller 层：FastAPI 路由、参数校验、结果返回
  └─ services/   业务编排层：编排下面的能力模块
       ├─ agents/      ReAct / Planner / Tool Agent
       ├─ workflows/   LangGraph / 状态机 / 多 Agent 协作
       ├─ skills/      业务专家经验沉淀与复用
       ├─ rag/         检索 / 召回 / 重排 / 知识库管理
       ├─ memory/      对话记忆 / 用户画像 / Checkpoint
       └─ mcp/         MCP Client / Server 管理
  ├─ schemas/        Pydantic 请求/响应模型
  └─ repositories/   DAO 层：PostgreSQL / Redis / Milvus / ES 访问封装
```

横向支撑层：
- `core/config.py` — 配置中心，按环境加载 `configs/{dev,test,prod}.yaml`，业务代码不硬编码配置。
- `core/logger.py` — Loguru 结构化日志。
- `core/llm/` — LLM 统一抽象（OpenAI / Qwen / DeepSeek 等），**屏蔽厂商差异**；业务层一律走此处，不直接调厂商 SDK。
- `core/prompt/` — Prompt 模板加载与版本管理。
- `middleware/` — JWT 认证、TraceId、日志、限流。
- `tasks/` — 异步任务（Celery / Arq / 定时任务）。

## 关键实现约定

- **启动链顺序**：`main.py`（`uvicorn main:app`）→ `app/factory.py`（应用工厂，创建 FastAPI 实例）→ `app/startup.py`（集中注册路由、中间件、数据库连接等）。新增模块的注册点统一放 `startup.py`。
- **配置驱动**：按环境区分，配置文件放 `configs/`，由 `core/config.py` 统一加载。
- **分层依赖单向**：`api → services → {agents/rag/skills/workflows/memory/mcp} → repositories`，跨层调用禁止逆向。
- **LLM 访问收敛**：所有模型调用经 `core/llm/`，便于切换厂商与统一计费/限流。

## 开发命令

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt  # 初始化依赖
.venv/bin/pytest tests/ -v                                            # 运行测试
APP_ENV=dev .venv/bin/python -c "from app.core.config import get_settings; print(get_settings().app.model_dump())"  # 查看生效配置
```

环境切换：`APP_ENV={dev,test,prod}` 选 yaml；敏感项覆盖：环境变量 `APP__<FIELD>` 或 `.env`（优先级 env > .env > yaml > 默认）。`uvicorn main:app` 待 `main.py` 实现真正入口后可用。
