# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目当前状态（务必先读）

**配置中心 + 启动链 + 全局异常捕获 + 生产级结构化日志 + 全局异步 HTTP 封装 + 跨域中间件已实现**：

- **配置中心**：`app/core/config.py`（pydantic-settings + yaml + .env + 环境变量多源，仅承载 `Settings` 根配置 + 多源加载 + `get_settings`，带 yaml 缺失 fail-fast；configs 目录经 `_resolve_configs_dir()` 解析——可被环境变量 `APP_CONFIG_DIR` 覆盖（容器/生产挂载入口），项目根用 `.git`/`requirements.txt` 标记向上查找抗文件移位；对外仍 re-export `AppSettings`，引用路径不变）；**配置段模型** `app/core/settings/`（schema 层，所有 `XxxSettings` 集中在 `settings.py` 单文件定义，避免 config.py 臃肿（当前已含 App/Logging/DB/Redis 四段；HTTP 客户端参数与 CORS/RequestID 策略均写死不进配置）；新增 JWT/LLM 等段时在 `settings.py` 加 class + `__init__` 导出 + `Settings` 根聚合字段）；`configs/{dev,test,prod}.yaml`、`.env.example`（含 `APP_CONFIG_DIR` 说明）、`.gitignore` 就位。
- **启动链已打通**：`main.py`（纯入口，仅暴露模块级 `app` 与触发 `server.run()`）→ `app/core/server.py`（uvicorn 进程级启动：workers/loop/concurrency/keepalive/access_log 全配置驱动，reload 仅 dev 开）→ `app/factory.py`（`create_app` + lifespan 启动加载配置挂 `app.state.settings` + 初始化 DB/Redis 连接池，关闭时释放）→ `app/startup.py`（`load_config` fail-fast + 脱敏打印、`register_routers`/`register_middlewares`）→ `app/core/logger.py`（loguru 生产级：stdout + `logs/app.log` 全量 + `logs/error.log` ERROR 分流 三 sink，按环境双模式（dev/test serialize=false 人类可读单行 + stdout 彩色；prod serialize=true JSON 供聚合）、enqueue 多进程安全、按 rotation/retention/compression 轮转，patcher 注入 env/service）→ `app/api/health.py`（`/health` 存活探针，已返回统一 `ApiResponse` 格式）；**路由聚合层** `app/api/routes.py`（`register_routes(app)` 集中 `include_router` 所有路由——基础设施端点直接挂、业务路由预留 `register_vN_routes` 版本化扩展点（注释占位、零空函数、零 ImportError），由 `startup.register_routers` 薄封装转调，factory 不动、注册链路行为零变化）。
- **全局异常捕获 + 统一响应规范已实现**：`app/schemas/common.py`（`ApiResponse{code,message,data,errno?}`，`ok()`/`fail()` + `to_payload()`——data 始终输出、errno 仅业务异常输出，故不能用 `exclude_none`）；`app/exceptions/base.py`（`BizException` 基类 + `BizNotFoundError`/`BizAuthError`/`BizForbiddenError`/`BizValidationError` 四子类，`status_code`/`errno`/`message` 为类属性，构造可覆盖）；`app/exceptions/handlers.py`（四 handler：`BizException`→INFO、`StarletteHTTPException`+`FastAPIHTTPException` **双注册**覆盖默认（含路由 404，易错点）→WARNING、`RequestValidationError`→INFO（字段级错误入 data）、`Exception` 兜底→ERROR+堆栈按 `app.debug` 脱敏）；`startup.py` 加 `register_exception_handlers` 薄封装，`factory.create_app` 按「路由→异常→中间件」顺序注册。**code 复用 HTTP 状态码，业务细码走 `errno`**。注意：测 500 兜底 handler 时 `TestClient` 须 `raise_server_exceptions=False`（ServerErrorMiddleware 调 handler 后仍 re-raise）。
- **生产级结构化日志已实现**：`setup_logging(LoggingSettings)` 配 3 sink（stdout + `logs/app.log` 全量 + `logs/error.log` ERROR 分流），按环境双模式（dev/test serialize=false 人类可读，格式含 `[req_id=xxx]` 便于请求追踪；prod serialize=true 经 patcher 预生成**精简业务 JSON**——仅 time/level/logger/func/line/message/env/service/request_id(+exception)，弃 loguru 全字段序列化的 process/thread/elapsed 噪音）、enqueue 多进程安全、按 rotation/retention/compression 轮转，patcher 注入 env/service/request_id（request_id 从 `app.middleware.request_id.get_request_id()` 读取，请求上下文外为 `-`）；配置段 `LoggingSettings`（level/serialize/dir/rotation/retention/compression/diagnose/backtrace/enqueue，diagnose dev 开/prod 关防泄露），startup.load_config 传 settings.logging。
- **全局异步 HTTP 封装已实现**：`app/utils/http_client.py`（基于 `httpx.AsyncClient` 的进程级单例封装：`get_client()` 惰性创建复用连接池，禁止每次 new client 致连接泄漏；超时 `httpx.Timeout` 四阶段（connect/read/write/pool）+ 连接池 `httpx.Limits`（max_connections/max_keepalive/keepalive_expiry）+ TLS verify + 默认 UA + 重试策略均以**模块级常量写死**（不进配置，将来需按环境调优再改配置驱动）；**重试三条件同时满足**才重试——① `httpx.TransportError` 网络异常或状态码命中 `retry_on_status` ② 幂等方法（GET/HEAD/OPTIONS/PUT/DELETE）③ 未超 `max_retries`，指数退避 `factor*2**n`，非幂等 POST/PATCH 一律不重试；失败统一 `raise BizException(...) from exc`（零裸 Exception）由全局 handler 转统一响应；loguru 记请求/响应/重试。便捷方法 `get/post/put/delete/patch` + `request()` 核心入口；`close_client()` 优雅关闭（待 factory lifespan 接入）。
- **跨域中间件已实现（策略写死，不进配置）**：`app/middleware/cors.py`（`setup_cors(app)` 直接写死全放行策略注册 `starlette CORSMiddleware`——`allow_origins=["*"]` / 全方法 / 全头 / `allow_credentials=False` / `max_age=600`；因策略各环境一致，不为永不变化的值做配置抽象，故不进 yaml、无 `CorsSettings` 段；credentials 固定 False 规避 `["*"]+True` 非法组合）；`startup.register_middlewares` 调 `setup_cors(app)`（CORS 作为「路由→异常→中间件」最后注册，异常 handler 优先）。**将来上生产若需收敛来源**，再改回配置驱动（加 `CorsSettings` + yaml 段）。
- **RequestID 请求追踪中间件已实现（策略写死，不进配置）**：`app/middleware/request_id.py`（`setup_request_id(app)` 注册 `RequestIDMiddleware`；入站从 `X-Request-Id` 头读取或用 `uuid.uuid4().hex` 生成（32 字符无连字符），存入 `contextvars.ContextVar` 供请求生命周期访问；出站响应头回写 `X-Request-Id`；提供 `get_request_id()` 函数读取当前请求 id）；`startup.register_middlewares` 调 `setup_request_id(app)`（在 CORS 之后、业务中间件之前注册，确保日志尽早带 id）。日志已集成 request_id（dev 格式 `[req_id=xxx]`，prod JSON 含 `request_id` 字段）。
- **依赖**：`requirements.txt` 已含 `fastapi` / `uvicorn[standard]` / `loguru` / `httpx`（TestClient 端到端测试 + 全局异步 HTTP 客户端）；CORS 用 FastAPI/starlette 自带 CORSMiddleware，无需新依赖。
- **数据层建设中**：`app/core/database.py`（SQLAlchemy 异步封装）、`app/core/redis.py`（Redis 异步客户端）、`app/repositories/base.py`（Repository 基类）、`app/repositories/cache.py`（缓存抽象）、`app/repositories/`（DAO 层：PostgreSQL / Redis / Milvus / ES 访问封装）——由其他 agent 负责实现。
- **测试**：`tests/` 共 **52 个测试，50 passed / 2 failed**——`test_config.py`(7)、`test_app.py`(3)、`test_api_response.py`(5)、`test_exceptions.py`(12)、`test_logging.py`(4)、`test_http_client.py`(13，httpx.MockTransport：成功/重试成功/重试用尽/网络异常/非幂等不重试/单例/close/模块常量默认)、`test_cors_middleware.py`(5，验证写死全放行策略：预检头/任意源回 */credentials 不暴露/max_age)、`test_routes.py`(2，路由聚合层：register_routes 挂载 /health + 经其挂载的端点端到端统一响应)。注意：`test_config.py` 的 `test_app_settings_defaults` / `test_settings_loads_dev_yaml_by_default` 为 **pre-existing 失败**（`dev.yaml` port 由 8002 改 8003 漏同步测试；`settings.py` 的 `name` 默认值残留 `arch-fastapi111`），与本次 HTTP/CORS 无关，经决策暂不修复。真机已验证工厂链路 `create_app → register_middlewares → setup_cors` 真实挂载：`/health` 返回 `{"code":200,"message":"ok","data":{"env":"dev"}}`，CORS 预检回 `allow-origin: *` / `allow-methods` 全方法 / `max-age: 600`。
- **文档约定**：代码注释一律中文（命名仍英文，见「关键实现约定」）。
- **Hook**：`.claude/` 下 Stop hook——`app/` / `main.py` / `tests/*.py` 有改动但 `CLAUDE.md` 未同步时，强制阻止回合结束（详见 `.claude/hooks/sync_claude_md.sh`）。

**开发环境为 Conda 环境 `arch-fatapi`（Python 3.11.15）**，具体命令见下文「开发命令」。

**下一步**：横向支撑层与数据层待补——`core/llm/`（统一 LLM 抽象，屏蔽厂商差异）、`middleware/`（CORS/RequestID 已完成且写死，将来生产收敛来源需改回配置驱动；HTTP 客户端参数同写死，将来需按环境调优再改配置驱动；剩 JWT / 限流；另 `utils/http_client.close_client()` 待接入 factory lifespan shutdown）、`repositories/`（PostgreSQL / Redis / Milvus / ES 访问）、`tasks/`（Celery / Arq 异步任务）。各层均经 `startup.py` 注册、经 `core/config.py` 取配置。

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

- **启动链顺序**：`main.py`（`uvicorn main:app`）→ `app/factory.py`（应用工厂，创建 FastAPI 实例）→ `app/startup.py`（集中注册路由、异常处理器、中间件等；路由注册转调 `app/api/routes.py` 聚合层）。新增模块的注册点统一放 `startup.py`，**业务路由清单**集中在 `app/api/routes.py`（基础设施端点直接挂、业务路由按 `register_vN_routes` 版本化扩展）。
- **统一响应 + 全局异常捕获**：所有 API 出口（路由与异常 handler）统一走 `app/schemas/common.py` 的 `ApiResponse{code,message,data,errno?}`（`code` 复用 HTTP 状态码；`errno` 仅业务异常输出）；业务异常 `raise app.exceptions.BizXxxError`（禁止裸 `raise Exception`），由 `app/exceptions/handlers.py` 四个 handler 统一转响应；500 兜底按 `app.debug` 脱敏（生产固定「服务内部错误」，堆栈只进日志）。新增业务异常子类在 `app/exceptions/base.py` 加 class（覆盖 status_code/errno/message）。
- **配置驱动**：按环境区分，配置文件放 `configs/`，由 `core/config.py` 统一加载。
- **分层依赖单向**：`api → services → {agents/rag/skills/workflows/memory/mcp} → repositories`，跨层调用禁止逆向。
- **LLM 访问收敛**：所有模型调用经 `core/llm/`，便于切换厂商与统一计费/限流。
- **代码注释用中文**：所有新增代码的注释一律使用中文，包括模块 / 类 / 函数的 docstring 与行内说明；变量、函数、类等命名仍遵循 PEP 8 用英文。
- **Git 提交信息用中文**：所有 commit 的标题与正文一律用中文描述，不写英文 message；类型前缀用中文动词（新增 / 修复 / 重构 / 文档 / 配置 / 测试 / 杂项）替代英文 conventional 前缀（feat / fix / refactor / docs / chore / test），例如写「新增：配置中心多源加载」而非「feat(config): add multi-source loading」。

## 开发命令

**开发环境**：项目使用 Conda 虚拟环境 **`arch-fatapi`**（环境名如此，确实少一个 `t`，不是笔误；Python 3.11.15）。所有命令须在此环境内执行；旧的 `.venv` 已弃用、可删除。

```bash
conda run -n arch-fatapi pip install -r requirements.txt   # 安装依赖
conda run -n arch-fatapi python -m pytest tests/ -v        # 运行测试（须用 python -m，bin/pytest 入口找不到 app 包）
APP_ENV=dev conda run -n arch-fatapi python -c "from app.core.config import get_settings; print(get_settings().app.model_dump())"  # 查看生效配置
```

环境切换：`APP_ENV={dev,test,prod}` 选 yaml；configs 目录覆盖：环境变量 `APP_CONFIG_DIR`（默认 `<项目根>/configs`，容器/生产挂载到 `/etc/<app>` 等位置时设置）；敏感项覆盖：环境变量 `APP__<FIELD>` 或 `.env`（优先级 env > .env > yaml > 默认）。开发启动：`python main.py` 或 `uvicorn main:app`（dev 环境自动 reload，`python main.py` 入口已通）。

## 生产部署

`main.py` 的 `main()` 配置驱动：开发（`env=dev`）自动 reload 单进程，生产（`env=prod`）按 `AppSettings` 调优参数起多 worker（`workers`/`loop`/`limit_concurrency`/`timeout_keep_alive`/`access_log`，见 `configs/prod.yaml`）。两种部署方式：

```bash
# 方式一：直接用 main.py（调优参数已在 prod.yaml 配好）
APP_ENV=prod python main.py
# 方式二：gunicorn + UvicornWorker 外置进程管理（滚动更新更成熟，容器化推荐）
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
```

生产建议 `pip install uvloop`（`loop: auto` 自动启用，比 asyncio 快 2-4 倍；Windows 不支持则自动回退）。由 systemd / docker / k8s 负责重启与滚动更新；`APP_ENV=prod` 务必 `debug=false`、`log_level` 不过度冗长。uvicorn 日志经 `intercept_uvicorn_logs` 接入 loguru，与应用日志格式统一。
