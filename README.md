# arch-fastapi

> 面向 AI Agent 应用的现代 FastAPI 后端脚手架。  
> 内置配置中心、结构化日志、统一响应、全局异常处理、异步数据库、Redis 缓存、请求追踪、访问日志、LLM 网关与清晰的业务分层范式。

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=flat-square&logo=fastapi&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.x-D71F00?style=flat-square)
![Redis](https://img.shields.io/badge/Redis-async-DC382D?style=flat-square&logo=redis&logoColor=white)
![LLM](https://img.shields.io/badge/LLM-OpenAI%20Compatible-111827?style=flat-square)

## 为什么是 arch-fastapi

`arch-fastapi` 不是一个只演示 Hello World 的模板，而是一套偏生产化的后端骨架。它把真实项目早期最容易散掉的部分提前收拢好：启动链、配置、多环境、日志、错误码、数据库会话、缓存封装、跨域、Request ID、健康探针、业务分层和 LLM 访问入口。

适合用来启动这些项目：

- AI Agent / RAG / Workflow 后端服务
- 多模型供应商统一接入网关
- 需要标准分层的 FastAPI 业务系统
- 内部平台、原型产品、SaaS API 服务
- 想从第一天就保留生产化扩展空间的 Python 后端

## 核心能力

| 能力 | 说明 |
| --- | --- |
| 配置中心 | `pydantic-settings + yaml + .env + 环境变量` 多源加载，支持 `dev/test/prod` 多环境 |
| 启动链 | `main.py -> app/server.py`，集中创建应用、注册路由、异常处理器、中间件和 lifespan |
| 统一响应 | `ApiResponse{code,message,data,errno?}`，API 成功与失败响应形态一致 |
| 全局异常 | 业务异常、HTTP 异常、参数校验异常、未知异常统一收口 |
| 结构化日志 | Loguru 三 sink：stdout、全量日志、错误日志；prod 输出精简 JSON |
| 请求追踪 | `X-Request-Id` 自动生成/透传，日志与响应头闭环 |
| 访问日志 | 自定义 AccessLog 接管 uvicorn access log，带 request_id 与耗时 |
| CORS | 配置驱动，开发环境全放行，生产环境白名单 |
| 异步 HTTP | 进程级 `httpx.AsyncClient` 单例、连接池、超时、幂等重试 |
| 数据层 | SQLAlchemy 2.0 async engine/session，启动期 DB 连通性预检 |
| 缓存层 | redis.asyncio 单例连接池，Redis 不可用时可降级运行 |
| 业务分层 | 已提供 `user` 模块的 api -> schemas -> services -> repositories 全链路案例 |
| LLM 网关 | OpenAI SDK 统一接入 OpenAI / DeepSeek / Qwen / Claude / Zhipu 等兼容端点 |
| 健康探针 | `/livez` 只看进程，`/readyz` 检查 DB/Redis，适合容器与 K8s |

## 架构概览

```text
client
  |
  v
api/                  # Controller：路由、参数校验、统一响应
  |
  v
services/             # Service：业务编排
  |
  +--> agents/         # Agent 能力预留
  +--> workflows/      # LangGraph / 状态机 / 多 Agent 协作预留
  +--> skills/         # 业务技能与专家经验预留
  +--> rag/            # 检索、召回、重排、知识库管理预留
  +--> memory/         # 对话记忆、用户画像、Checkpoint 预留
  +--> mcp/            # MCP Client / Server 管理预留
  |
  v
repositories/         # DAO：PostgreSQL / Redis / Milvus / ES 访问封装

core/                 # 配置、日志、数据库、Redis、LLM、Prompt 等横向基础能力
middleware/           # CORS、RequestID、AccessLog，后续可扩 JWT / 限流
tasks/                # Celery / Arq / 定时任务预留
```

启动链保持简单明确：

```text
main.py -> app/server.py -> app/api/routes.py
```

新增横向能力优先接入 `app/server.py`，新增业务路由统一挂到 `app/api/routes.py`。

## 目录结构

```text
arch-fastapi/
├── app/
│   ├── api/                 # 路由层：health、v1/users、v1/llm
│   ├── services/            # 业务编排层
│   ├── schemas/             # Pydantic 请求/响应模型
│   ├── repositories/        # models + dao 数据访问层
│   ├── core/                # config/logger/database/redis/llm/prompt
│   ├── middleware/          # cors/request_id/access_log
│   ├── utils/               # HTTP client、cache、通用响应
│   ├── agents/              # Agent 能力预留
│   ├── workflows/           # 工作流能力预留
│   ├── rag/                 # RAG 能力预留
│   ├── memory/              # 记忆能力预留
│   ├── mcp/                 # MCP 能力预留
│   ├── skills/              # Skill 能力预留
│   ├── tasks/               # 异步任务预留
│   └── server.py            # FastAPI 应用组装与运行
├── configs/
│   ├── dev.yaml
│   ├── test.yaml
│   └── prod.yaml
├── main.py                  # 入口：导出 create_app，直接执行时 run
├── requirements.txt
└── README.md
```

## 快速开始

项目默认使用 Conda 环境 `arch-fatapi`，Python 版本为 3.11。

```bash
conda create -n arch-fatapi python=3.11 -y
conda run -n arch-fatapi pip install -r requirements.txt
```

启动开发服务：

```bash
APP_ENV=dev conda run -n arch-fatapi python main.py
```

或使用 uvicorn factory 模式：

```bash
APP_ENV=dev conda run -n arch-fatapi uvicorn "app.server:create_app" --factory --reload
```

默认开发端口见 `configs/dev.yaml`，当前为 `8003`。

访问：

- OpenAPI 文档：`http://127.0.0.1:8003/docs`
- 存活探针：`http://127.0.0.1:8003/livez`
- 就绪探针：`http://127.0.0.1:8003/readyz`
- 用户列表：`http://127.0.0.1:8003/v1/users`

## 配置说明

配置加载优先级：

```text
环境变量 > .env > configs/{APP_ENV}.yaml > 代码默认值
```

常用环境变量：

| 变量 | 用途 |
| --- | --- |
| `APP_ENV` | 选择配置环境：`dev` / `test` / `prod` |
| `APP_CONFIG_DIR` | 覆盖配置目录，适合容器或生产挂载 |
| `DB__URL` | 覆盖数据库连接串 |
| `LLM_API_KEY_OPENAI` | OpenAI Provider 密钥 |
| `LLM_API_KEY_DEEPSEEK` | DeepSeek Provider 密钥 |
| `LLM_API_KEY_QWEN` | Qwen Provider 密钥 |
| `LLM_API_KEY_CLAUDE` | Claude Provider 密钥 |
| `LLM_API_KEY_ZHIPU` | Zhipu Provider 密钥 |
| `LANGCHAIN_API_KEY` | 启用 LangSmith tracing 时使用 |

查看生效配置：

```bash
APP_ENV=dev conda run -n arch-fatapi python -c "from app.core.config import get_settings; print(get_settings().app.model_dump())"
```

## API 响应规范

成功响应：

```json
{
  "code": 200,
  "message": "ok",
  "data": {}
}
```

业务异常响应：

```json
{
  "code": 404,
  "message": "资源不存在",
  "data": null,
  "errno": 10404
}
```

约定：

- `code` 复用 HTTP 状态码
- `errno` 只用于业务异常和基础设施异常
- `errno` 全系统统一为 `int`
- 路由层不写 try/except，业务错误由 service 抛出，再由全局 handler 转响应

## LLM 网关

LLM 层位于 `app/core/llm/`，目标是让业务代码不直接依赖厂商 SDK。

当前 Provider 统一走 OpenAI 兼容端点，通过 `base_url + api_key + default_model` 切换厂商：

- OpenAI
- DeepSeek
- Qwen
- Claude OpenAI-compatible endpoint
- Zhipu

测试 Zhipu Provider：

```bash
LLM_API_KEY_ZHIPU=your_key APP_ENV=dev conda run -n arch-fatapi python main.py
curl "http://127.0.0.1:8003/v1/llm/zhipu/test?prompt=只回复两个字：成功"
```

测试 LangChain ChatModel：

```bash
curl "http://127.0.0.1:8003/v1/llm/langchain/test?provider=zhipu&prompt=只回复两个字：成功"
```

## 业务开发范式

新增业务模块推荐按 `user` 示例扩展：

```text
app/api/v1/<biz>_router.py          # 路由层
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
- 依赖方向保持自上而下，禁止 repository 反向 import service
- 新增业务路由在 `app/api/routes.py` 统一挂载版本前缀

## 日志与可观测性

日志由 `app/core/logger.py` 统一配置：

- dev/test：人类可读单行日志，包含 `[req_id=xxx]`
- prod：精简 JSON，适合日志采集系统
- stdout：控制台输出
- `logs/app.log`：全量日志
- `logs/error.log`：ERROR 分流
- AccessLog：记录 client、method、path、status、duration

请求追踪：

- 入站 `X-Request-Id` 存在则透传
- 不存在则自动生成 32 位 request_id
- 出站响应头回写 `X-Request-Id`
- 应用日志与访问日志自动带 request_id

## 测试

运行本地测试：

```bash
conda run -n arch-fatapi python -m pytest tests/ -v
```

如果只验证应用能否构建：

```bash
APP_ENV=test conda run -n arch-fatapi python -c "from app.server import create_app; app = create_app(enable_lifespan=False); print(app.title)"
```

## 生产部署

直接启动：

```bash
APP_ENV=prod conda run -n arch-fatapi python main.py
```

Gunicorn + UvicornWorker：

```bash
APP_ENV=prod gunicorn "app.server:create_app" -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000 --factory
```

生产建议：

- 使用环境变量或密钥系统注入敏感配置
- `APP_ENV=prod`
- `debug=false`
- 收敛 CORS 白名单
- 使用外部进程管理器负责重启、滚动更新与健康检查
- 将 `/livez` 用作 liveness probe，将 `/readyz` 用作 readiness probe

## 路线图

- [x] 配置中心
- [x] 启动链
- [x] 全局异常处理
- [x] 结构化日志
- [x] RequestID
- [x] AccessLog
- [x] CORS
- [x] 异步 HTTP client
- [x] SQLAlchemy 异步数据层
- [x] Redis 缓存层
- [x] user 业务分层案例
- [x] LLM Provider 统一入口
- [ ] JWT 认证
- [ ] 限流
- [ ] LLM fallback / pricing
- [ ] Embedding / 多模态
- [ ] Prompt 模板与版本管理
- [ ] RAG 检索链路
- [ ] Agent / Workflow 编排
- [ ] Celery / Arq 异步任务

## 设计原则

- 简单启动链：入口少、责任清晰、可测试
- 配置收敛：业务代码不硬编码环境差异
- 错误收口：API 响应稳定，异常链路可观测
- 基础设施集中：日志、DB、Redis、HTTP、LLM 都有统一入口
- 分层清晰：Controller、Service、DAO、Model 各司其职
- AI 友好：为 Agent、RAG、Workflow、MCP、Memory 预留演进空间

## License

当前仓库尚未声明开源许可证。对外发布前建议补充 `LICENSE` 文件。
