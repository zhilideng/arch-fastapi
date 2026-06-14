## 项目结构
arch-fastapi /                           # 项目根目录
│
├── app/                              # 核心业务代码
│
│   ├── api/                          # API接口层（Controller）
│   │                                 # 路由定义、参数接收、结果返回
│   │
│   ├── services/                     # 业务服务层（Service）
│   │                                 # 业务编排、调用Agent/RAG/Skill
│   │
│   ├── agents/                       # Agent模块
│   │                                 # ReAct、Planner、Tool Agent
│   │
│   ├── workflows/                    # 工作流模块
│   │                                 # LangGraph、状态机、多Agent协作
│   │
│   ├── skills/                       # Skill能力中心
│   │                                 # 业务专家经验沉淀与复用
│   │
│   ├── rag/                          # RAG模块
│   │                                 # 检索、召回、重排、知识库管理
│   │
│   ├── memory/                       # Memory模块
│   │                                 # 对话记忆、用户画像、Checkpoint
│   │
│   ├── mcp/                          # MCP模块
│   │                                 # MCP Client、MCP Server管理
│   │
│   ├── repositories/                 # 数据访问层（DAO）
│   │                                 # PostgreSQL、Redis、Milvus、ES访问封装
│   │
│   ├── schemas/                      # 数据模型层
│   │                                 # Pydantic请求模型、响应模型
│   │
│   ├── middleware/                   # 中间件
│   │                                 # JWT认证、TraceId、日志、限流
│   │
│   ├── tasks/                        # 异步任务
│   │                                 # Celery、Arq、定时任务
│   │
│   ├── utils/                        # 通用工具库
│   │                                 # 时间、文件、加密、字符串处理
│   │
│   ├── core/                         # 系统基础能力
│   │
│   │   ├── config.py                 # 配置中心
│   │   │                             # 环境变量、数据库配置、模型配置
│   │   │
│   │   ├── logger.py                 # 日志模块
│   │   │                             # Loguru、结构化日志
│   │   │
│   │   ├── llm/                      # 模型统一管理
│   │   │                             # OpenAI、Qwen、DeepSeek等
│   │   │
│   │   └── prompt/                   # Prompt管理中心
│   │                                 # Prompt模板加载与版本管理
│   │
│   ├── startup.py                    # 系统启动注册
│   │                                 # 注册路由、中间件、数据库连接等
│   │
│   ├── factory.py                    # 应用工厂
│   │                                 # 创建FastAPI实例
│   │
│   └── __init__.py
│
├── tests/                            # 测试目录
│   │                                 # 单元测试、集成测试
│
├── scripts/                          # 运维脚本
│   │                                 # 数据初始化、知识库导入
│
├── configs/                          # 配置文件目录
│   │
│   ├── dev.yaml                      # 开发环境配置
│   ├── test.yaml                     # 测试环境配置
│   └── prod.yaml                     # 生产环境配置
│
├── main.py                           # 项目启动入口
│                                     # uvicorn main:app
│
├── requirements.txt                  # Python依赖
│
└── README.md                         # 项目说明
