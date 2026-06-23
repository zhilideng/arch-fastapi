# arch-fastapi

> 面向 **AI Agent 应用**的现代 FastAPI 后端脚手架 —— 把真实项目早期最容易散掉的部分提前收拢：启动链、多环境配置、结构化日志、统一响应、全局异常、异步数据层、Redis 缓存、Milvus 向量检索、请求追踪、访问日志、**LLM 网关**与**Skill 注册中心**，并提供清晰的业务分层范式。

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=flat-square&logo=fastapi&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.x%20async-D71F00?style=flat-square)
![Redis](https://img.shields.io/badge/Redis-asyncio-DC382D?style=flat-square&logo=redis&logoColor=white)
![Milvus](https://img.shields.io/badge/Milvus-AsyncMilvusClient-00A1EA?style=flat-square)
![OpenAI](https://img.shields.io/badge/LLM-OpenAI%20Compatible-111827?style=flat-square)
![LangChain](https://img.shields.io/badge/LangChain-ChatModel-1C3C3C?style=flat-square&logo=langchain&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-blue?style=flat-square)

---

## 目录

- [为什么是 arch-fastapi](#为什么是-arch-fastapi)
- [✨ 特性清单](#-特性清单)
- [架构概览](#架构概览)
- [目录结构](#目录结构)
- [快速开始](#快速开始)
- [核心能力](#核心能力)
- [AI 能力：LLM 网关与 Skill](#ai-能力llm-网关与-skill)
- [业务开发范式](#业务开发范式)
- [API 响应规范](#api-响应规范)
- [配置说明](#配置说明)
- [日志与可观测性](#日志与可观测性)
- [测试](#测试)
- [生产部署](#生产部署)
- [路线图](#路线图)
- [设计原则](#设计原则)
- [License](#license)

---

## 为什么是 arch-fastapi

`arch-fastapi` 不是一个只演示 Hello World 的模板，而是一套**偏生产化**的后端骨架。它假设你接下来要长期维护一个 AI 后端，于是把那些"每个项目都要重写一遍、但每次都写得不一样"的横切关注点提前固化好。

适合用来启动这些项目：

- 🤖 AI Agent / RAG / Workflow 后端服务
- 🔌 多模型供应商统一接入网关
- 🧱 需要标准分层的 FastAPI 业务系统
- 🏢 内部平台、原型产品、SaaS API 服务
- 🚀 想从第一天就保留生产化扩展空间的 Python 后端

---

## ✨ 特性清单

> ✅ = 已实现并接入启动链；☐ = 规划中（见 [路线图](#路线图)）。

### 配置与启动

- ✅ **多源配置中心** —— `pydantic-settings + yaml + .env + 环境变量` 多源加载，支持 `dev/test/prod` 多环境，yaml 缺失 fail-fast
- ✅ **factory 模式启动链** —— `main.py → app/server.py`，集中 `create_app / lifespan / run`，启动期初始化 DB/Redis/Milvus/LLM/Skill，关闭期逆序释放
- ✅ **统一响应规范** —— `ApiResponse{code, message, data, errno?}`，成功与失败响应形态一致
- ✅ **全局异常捕获** —— 业务异常 / HTTP 异常 / 参数校验异常 / 未知异常四类统一收口，500 兜底按 `debug` 脱敏
- ✅ **业务错误码分段** —— HTTP 类 `1+状态码`、业务 `1xxxx`、基础设施层 `2xxxx`（DB 20xxx / LLM 21xxx / Skill 23xxx / Milvus 24xxx），全系统 `errno` 统一为 `int`

### 可观测性与中间件

- ✅ **生产级结构化日志** —— Loguru 三 sink（stdout + 全量 `app.log` + ERROR 分流 `error.log`），dev 人类可读单行 / prod 精简 JSON，`enqueue` 多进程安全，按 rotation/retention/compression 轮转
- ✅ **RequestID 请求追踪** —— `X-Request-Id` 入站透传 / 自动生成 / 出站回写，日志与访问日志全程携带
- ✅ **AccessLog 访问日志** —— 自写中间件接管 uvicorn access log，带 `request_id` 与耗时，注册顺序保证 id 不丢失
- ✅ **CORS 跨域** —— 配置驱动，dev/test 全放行、prod 白名单收敛
- ✅ **全局异步 HTTP 封装** —— 进程级 `httpx.AsyncClient` 单例 + 连接池 + 四阶段超时 + 幂等方法指数退避重试

### 数据访问

- ✅ **SQLAlchemy 2.0 异步数据层** —— async engine + `async_sessionmaker`，启动期 `SELECT 1` 连通性预检 fail-fast，`get_db()` 依赖注入
- ✅ **Redis 异步缓存层** —— `redis.asyncio` 单例连接池，非核心依赖（连不上降级运行不阻断启动），cache-aside 封装 + JSON 序列化 + TTL
- ✅ **Milvus 异步向量库访问层** —— `AsyncMilvusClient` 单例与启动探测，collection 管理、批量 insert/upsert、delete/get/query/search，检索结果归一，失败可降级
- ✅ **业务分层范式** —— 已提供 `user` 模块 `api → schemas → services → repositories/{models,dao}` 全链路案例

### AI 能力

- ✅ **LLM 网关** —— OpenAI SDK 统一接入 **OpenAI / DeepSeek / Qwen / Claude / Zhipu** 兼容端点，支持 chat / streaming / tool_calling / usage
- ✅ **LangChain ChatModel 集成** —— `get_langchain_llm()` 复用网关配置，LangSmith tracing 开关可控（关时强制压制外部注入变量，零上报）
- ✅ **Skill 注册中心** —— Anthropic Agent Skills 风格能力包，启动期扫描 `SKILL.md` 建索引、请求期懒加载正文、按需缓存、统一 `run` 入口

### 工程规范

- ✅ **健康探针** —— `/livez` 只看进程、`/readyz` 并发检查 DB/Redis/Milvus；可选依赖失败标 degraded，K8s / 容器友好
- ✅ **分层依赖单向** —— `api → services → {agents/rag/skills/...} → repositories`，禁止反向依赖
- ✅ **LLM 访问收敛** —— 所有模型调用经 `core/llm/`，业务层不直接依赖厂商 SDK

---

## 架构概览

分层架构，依赖自上而下单向流动：

```text
client
  │
  ▼
api/                  Controller：路由、参数校验、统一响应
  │
  ▼
services/             Service：业务编排
  │
  ├──► agents/         # Agent 能力预留
  ├──► workflows/      # LangGraph / 状态机 / 多 Agent 协作预留
  ├──► skills/         # ✅ 业务技能与专家经验（Skill 注册中心）
  ├──► rag/            # 检索、召回、重排、知识库管理预留
  ├──► memory/         # 对话记忆、用户画像、Checkpoint 预留
  └──► mcp/            # MCP Client / Server 管理预留
  │
  ▼
repositories/         DAO：PostgreSQL / Milvus（✅）/ ES 访问封装

core/                 配置、日志、数据库、Redis、Milvus、LLM、Skill 等横向基础能力
middleware/           CORS、RequestID、AccessLog（✅），后续可扩 JWT / 限流
tasks/                Celery / Arq / 定时任务预留
```

启动链保持简单明确：

```text
main.py  ─►  app/server.py  ─►  app/api/routes.py
 (入口)       (组装/生命周期)      (业务路由聚合)
```

> 新增横向能力优先接入 `app/server.py`，新增业务路由统一挂到 `app/api/routes.py`。

---

## 目录结构

```text
arch-fastapi/
├── app/
│   ├── api/                 # 路由层：health、v1/users、v1/llm、v1/skills
│   │   └── v1/              # namespace package（无 __init__.py）
│   ├── services/            # 业务编排层（user_service、skill_service）
│   ├── schemas/             # Pydantic 请求/响应模型（含统一 ApiResponse）
│   ├── repositories/        # models/（ORM 实体）+ dao/（Repository）
│   ├── core/                # config / logger / database / redis / llm / skills
│   ├── middleware/          # cors / request_id / access_log
│   ├── utils/               # http_client、cache、通用响应
│   ├── exceptions/          # BizException 家族 + 全局 handler + 错误码常量
│   ├── agents/              # Agent 能力预留
│   ├── workflows/           # 工作流能力预留
│   ├── rag/                 # RAG 能力预留
│   ├── memory/              # 记忆能力预留
│   ├── mcp/                 # MCP 能力预留
│   ├── skills/              # ✅ Skill 数据资产（<name>/SKILL.md）
│   ├── tasks/               # 异步任务预留
│   └── server.py            # FastAPI 应用组装与运行
├── configs/
│   ├── dev.yaml
│   ├── test.yaml
│   └── prod.yaml
├── main.py                  # 入口：导出 create_app，直接执行时 run
├── requirements.txt
├── LICENSE
└── README.md
```

---

## 快速开始

项目默认使用 Conda 环境 `arch-fatapi`（Python 3.11）。

```bash
# 1. 创建环境并安装依赖
conda create -n arch-fatapi python=3.11 -y
conda run -n arch-fatapi pip install -r requirements.txt

# 2. 启动开发服务（dev 自动 reload）
APP_ENV=dev conda run -n arch-fatapi python main.py

# 或使用 uvicorn factory 模式
APP_ENV=dev conda run -n arch-fatapi uvicorn "app.server:create_app" --factory --reload
```

默认开发端口见 `configs/dev.yaml`（当前为 `8003`）。启动后访问：

| 入口 | 地址 |
| --- | --- |
| OpenAPI 文档 | `http://127.0.0.1:8003/docs` |
| 存活探针 | `http://127.0.0.1:8003/livez` |
| 就绪探针 | `http://127.0.0.1:8003/readyz` |
| 用户列表 | `http://127.0.0.1:8003/v1/users` |
| Skill 列表 | `http://127.0.0.1:8003/v1/skills` |

---

## 核心能力

### 统一响应 + 全局异常

所有 API 出口统一走 `ApiResponse`，业务异常由 service 抛 `BizXxxError`、全局 handler 转响应，**路由层不写 try/except**。

```json
// 成功
{ "code": 200, "message": "ok", "data": {} }

// 业务异常（errno 仅异常时输出）
{ "code": 404, "message": "资源不存在", "data": null, "errno": 10404 }
```

- `code` 复用 HTTP 状态码
- `errno` 仅业务/基础设施异常输出，全系统统一为 `int`
- 错误码分段：HTTP 类 `1+状态码`、业务 `1xxxx`、基础设施 `2xxxx`（DB 20xxx / LLM 21xxx / Skill 23xxx）

### 配置中心

`app/core/config.py` 承载 `Settings` 根配置，按环境加载 `configs/{dev,test,prod}.yaml`，业务代码不硬编码环境差异。

```text
加载优先级：环境变量  >  .env  >  configs/{APP_ENV}.yaml  >  代码默认值
```

### 结构化日志

`app/core/logger.py` 统一配置：

- **dev/test**：人类可读单行，含 `[req_id=xxx]`
- **prod**：精简 JSON（time/level/logger/func/line/message/env/service/request_id），适合日志采集
- 三 sink：`stdout` + `logs/app.log`（全量）+ `logs/error.log`（ERROR 分流）
- `enqueue` 多进程安全，按 rotation / retention / compression 轮转

### 中间件链

注册顺序（starlette 后 add 者更外层）：`RequestID`（最外）→ `AccessLog` → `CORS`（最内）。

- **RequestID**：入站读 `X-Request-Id` 或生成 32 位 id，存 `contextvars`，出站回写
- **AccessLog**：`call_next` 计时，`{client} "{method} {path}" {status} {duration_ms}ms`
- **CORS**：dev/test `allow_origins=["*"]`，prod 白名单 + `expose_headers=[X-Request-Id]`

### 异步 HTTP client

`app/utils/http_client.py` 进程级 `httpx.AsyncClient` 单例，超时/连接池/重试策略写死（不进配置）。**重试三条件同时满足**才重试：① 网络异常或命中重试状态码 ② 幂等方法（GET/HEAD/OPTIONS/PUT/DELETE）③ 未超 `max_retries`，指数退避；POST/PATCH 一律不重试。

### 数据层

- **SQLAlchemy**：进程级 async engine 单例 + `async_sessionmaker`，启动期 `SELECT 1` 预检，连不上 `raise BizException(DB_CONNECT_FAILED)` 拒启动（核心依赖 fail-fast）
- **Redis**：进程级单例连接池，构建/ping 失败 warning + 降级运行（非核心依赖），`get_redis_optional()` 供探针区分在线/降级
- **Milvus**：进程级 `AsyncMilvusClient`，启动只读探测失败时降级；`VectorRepository` 提供 collection 管理、分批写入、标量查询与向量检索，token 只经环境变量注入

---

## AI 能力：LLM 网关与 Skill

### LLM 网关（`app/core/llm/`）

业务层一律走 `core/llm/`，不直接依赖厂商 SDK。4+ 家 Provider 统一走 OpenAI 兼容端点，靠 `base_url + api_key + default_model` 切换：

| Provider | 端点 | 默认模型 |
| --- | --- | --- |
| OpenAI | `api.openai.com/v1/` | `gpt-4o-mini` |
| DeepSeek | `api.deepseek.com/v1/` | `deepseek-chat` |
| Qwen | `dashscope.aliyuncs.com/compatible-mode/v1/` | `qwen-plus` |
| Claude | Anthropic OpenAI 兼容端点 | `claude-3-5-sonnet` |
| Zhipu | `open.bigmodel.cn/api/paas/v4/` | `glm-4-flash` |

能力：`chat`（非流式）/ `stream`（流式）/ `tool_calling` / `usage`。密钥统一经 `LLM_API_KEY_<大写NAME>` 环境变量注入，不写入 yaml/代码。

验证连通性：

```bash
# 直接验证某 Provider
curl "http://127.0.0.1:8003/v1/llm/zhipu/test?prompt=只回复两个字：成功"

# 经 LangChain ChatModel 验证
curl "http://127.0.0.1:8003/v1/llm/langchain/test?provider=zhipu&prompt=只回复两个字：成功"
```

### Skill 注册中心（`app/core/skills/`）

Anthropic Agent Skills 风格的能力包机制：

- **数据资产**：`app/skills/<name>/SKILL.md`（YAML frontmatter + markdown 正文）
- **启动期**：`init_skills()` 扫描 `base_dir/*/SKILL.md` 建轻量索引 `skill_index`
- **请求期**：`load(name)` 懒加载正文组装 `SkillBundle`，按 `cache_loaded` 缓存
- **执行**：`SkillService` 把正文作 `SystemMessage`、用户输入作 `HumanMessage`，经 `get_langchain_llm()` 调用
- **健壮性**：非核心依赖，`enabled=false` / 目录缺失 / 单个坏 skill 均 warning 降级，不阻断启动；`__pycache__` 与隐藏目录静默忽略

API：

```bash
GET  /v1/skills            # 列出全部 Skill 元数据
GET  /v1/skills/{name}     # 查看某 Skill 详情
POST /v1/skills/{name}/run # 执行（body 传用户输入）
```

内置 demo：`app/skills/summarize/SKILL.md`。

---

## 业务开发范式

新增业务模块按 `user` 示例扩展，一表对应五件套：

```text
app/api/v1/<biz>_router.py          # 路由层（文件名带 _router 后缀）
app/schemas/<biz>.py                # 请求/响应模型
app/services/<biz>_service.py       # 业务编排
app/repositories/models/<biz>.py    # ORM 模型
app/repositories/dao/<biz>.py       # Repository / DAO
```

分层规则：

- `api` 只做参数接收、依赖注入、调用 service、返回统一响应
- `services` 负责业务判断与流程编排
- `repositories/dao` 只做数据访问，不写业务规则
- `repositories/models` 只定义 ORM 实体
- 依赖方向自上而下，**禁止 repository 反向 import service**
- 新增业务路由在 `app/api/routes.py` 统一挂载版本前缀 `/vN`

> `app/api/vN/` 是 namespace package，**不放 `__init__.py`**。

---

## 配置说明

常用环境变量：

| 变量 | 用途 |
| --- | --- |
| `APP_ENV` | 选择配置环境：`dev` / `test` / `prod` |
| `APP_CONFIG_DIR` | 覆盖配置目录，适合容器或生产挂载 |
| `DB__URL` | 覆盖数据库连接串（注意 env_prefix 为空，故是 `DB__URL`） |
| `LLM_API_KEY_OPENAI` | OpenAI Provider 密钥 |
| `LLM_API_KEY_DEEPSEEK` | DeepSeek Provider 密钥 |
| `LLM_API_KEY_QWEN` | Qwen Provider 密钥 |
| `LLM_API_KEY_CLAUDE` | Claude Provider 密钥 |
| `LLM_API_KEY_ZHIPU` | Zhipu Provider 密钥 |
| `LANGSMITH_API_KEY` | 启用 LangSmith tracing 时使用（开关在 yaml `llm.langsmith.enabled`） |

查看生效配置：

```bash
APP_ENV=dev conda run -n arch-fatapi python -c "from app.core.config import get_settings; print(get_settings().app.model_dump())"
```

---

## 日志与可观测性

请求追踪链路：

- 入站 `X-Request-Id` 存在则透传，不存在则自动生成 32 位 request_id
- 出站响应头回写 `X-Request-Id`
- 应用日志与访问日志自动带 request_id（dev 格式 `[req_id=xxx]`，prod JSON 含 `request_id` 字段）

健康探针：

- `/livez`：存活探针，只看进程不碰依赖
- `/readyz`：并发检查 DB / Redis / Milvus（Redis/Milvus 不可用判为 degraded，DB 不可用返回 503）

---

## 测试

```bash
# 运行全部测试（须用 python -m，bin/pytest 入口找不到 app 包）
conda run -n arch-fatapi python -m pytest tests/ -v

# 仅验证应用能否构建
APP_ENV=test conda run -n arch-fatapi python -c \
  "from app.server import create_app; app = create_app(enable_lifespan=False); print(app.title)"
```

---

## 生产部署

`app.server.run()` 配置驱动：dev 自动 reload 单进程，prod 按 `AppSettings` 起多 worker。

```bash
# 方式一：直接用 main.py（调优参数已在 prod.yaml 配好）
APP_ENV=prod conda run -n arch-fatapi python main.py

# 方式二：gunicorn + UvicornWorker（容器化推荐，滚动更新更成熟）
APP_ENV=prod gunicorn "app.server:create_app" -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000 --factory
```

生产建议：

- ✅ 敏感配置走环境变量或密钥系统注入，不进 yaml
- ✅ `APP_ENV=prod`、`debug=false`
- ✅ 收敛 CORS 白名单与日志级别
- ✅ 使用 systemd / docker / k8s 负责重启与滚动更新
- ✅ `/livez` 作 liveness probe，`/readyz` 作 readiness probe
- ✅ 安装 `uvloop`（`loop: auto` 自动启用，比 asyncio 快 2-4 倍）

---

## 路线图

> ✅ 已完成 · ☐ 规划中

**基础设施**

- ✅ 配置中心（多源加载）
- ✅ factory 模式启动链
- ✅ 生产级结构化日志（Loguru）
- ✅ 统一响应 + 全局异常捕获
- ✅ 业务错误码分段（含基础设施层 2xxxx）
- ✅ RequestID 请求追踪
- ✅ AccessLog 访问日志
- ✅ CORS（配置驱动）
- ✅ 全局异步 HTTP client（重试/超时/连接池）
- ✅ 健康探针（livez / readyz）
- ☐ 限流（Rate Limit，暂时不做，不是业务和服务都有那么高的并发）

**数据层**

- ✅ SQLAlchemy 2.0 异步数据层
- ✅ Redis 异步缓存层
- ✅ user 业务分层案例
- ✅ Milvus 向量库访问封装

**AI 能力**

- ✅ LLM Provider 统一入口（5 家）
- ✅ LangChain ChatModel 集成
- ✅ Skill 注册中心
- ☐ LLM fallback 降级 / pricing 计费
- ☐ Embedding / 多模态
- ☐ Prompt 模板与版本管理
- ☐ RAG 检索链路
- ☐ Agent / Workflow 编排
- ☐ Memory 对话记忆
- ☐ MCP Client / Server

**任务与运维**

- ☐ Celery / Arq 异步任务

---

## 设计原则

- **简单启动链** —— 入口少、责任清晰、可测试
- **配置收敛** —— 业务代码不硬编码环境差异
- **错误收口** —— API 响应稳定，异常链路可观测
- **基础设施集中** —— 日志、DB、Redis、HTTP、LLM 都有统一入口
- **分层清晰** —— Controller、Service、DAO、Model 各司其职
- **AI 友好** —— 为 Agent、RAG、Workflow、MCP、Memory 预留演进空间

---

## License

本项目基于 [MIT License](./LICENSE) 开源。
