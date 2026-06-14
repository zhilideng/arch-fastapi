# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目当前状态（务必先读）

**配置中心 + 启动链已实现**：

- **配置中心** `app/core/config.py`（pydantic-settings + yaml + .env + 环境变量多源，含 `Settings`/`AppSettings`/`get_settings`，带 yaml 缺失 fail-fast）、`configs/{dev,test,prod}.yaml`、`.env.example`、`.gitignore` 就位。
- **启动链已打通**：`main.py`（uvicorn 入口，host/port/debug/log_level 全配置驱动，reload 仅 debug 开）→ `app/factory.py`（`create_app` + lifespan 启动加载配置挂 `app.state.settings`）→ `app/startup.py`（`load_config` fail-fast + 脱敏打印、`register_routers`/`register_middlewares`）→ `app/core/logger.py`（loguru，`diagnose=False` 防生产泄露）→ `app/api/health.py`（`/health` 存活探针）。
- **依赖**：`requirements.txt` 已含 `fastapi` / `uvicorn[standard]` / `loguru`。
- **测试**：`tests/` 共 **10 个测试全绿**（`test_config.py` 7 + `test_app.py` 3，覆盖多源加载、ENV 覆盖、应用工厂、`/health`、非法 env fail-fast）；真机已验证 `GET /health` 返回 `{"status":"ok","env":...}`。
- **文档约定**：代码注释一律中文（命名仍英文，见「关键实现约定」）。
- **Hook**：`.claude/` 下 Stop hook——`app/` / `main.py` / `tests/*.py` 有改动但 `CLAUDE.md` 未同步时，强制阻止回合结束（详见 `.claude/hooks/sync_claude_md.sh`）。

**开发环境为 Conda 环境 `arch-fatapi`（Python 3.11.15）**，具体命令见下文「开发命令」。

**下一步**：横向支撑层与数据层待补——`core/llm/`（统一 LLM 抽象，屏蔽厂商差异）、`middleware/`（JWT / TraceId / 限流）、`repositories/`（PostgreSQL / Redis / Milvus / ES 访问）、`tasks/`（Celery / Arq 异步任务）。各层均经 `startup.py` 注册、经 `core/config.py` 取配置。

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
- **代码注释用中文**：所有新增代码的注释一律使用中文，包括模块 / 类 / 函数的 docstring 与行内说明；变量、函数、类等命名仍遵循 PEP 8 用英文。

## 开发命令

**开发环境**：项目使用 Conda 虚拟环境 **`arch-fatapi`**（环境名如此，确实少一个 `t`，不是笔误；Python 3.11.15）。所有命令须在此环境内执行；旧的 `.venv` 已弃用、可删除。

```bash
conda run -n arch-fatapi pip install -r requirements.txt   # 安装依赖
conda run -n arch-fatapi python -m pytest tests/ -v        # 运行测试（须用 python -m，bin/pytest 入口找不到 app 包）
APP_ENV=dev conda run -n arch-fatapi python -c "from app.core.config import get_settings; print(get_settings().app.model_dump())"  # 查看生效配置
```

环境切换：`APP_ENV={dev,test,prod}` 选 yaml；敏感项覆盖：环境变量 `APP__<FIELD>` 或 `.env`（优先级 env > .env > yaml > 默认）。`uvicorn main:app` 待 `main.py` 实现真正入口后可用。
