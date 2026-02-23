# Phase 1 实现进度报告

## 核心结论

Phase 1 核心对话系统**已完成全部 12 个步骤**，端到端可工作。所有服务已启动运行：

- FastAPI 后端 `:8000` — 运行中（hot reload）
- LiteLLM 代理 `:4000` — 运行中（通过 minimaxi 代理转发 Anthropic API）
- PostgreSQL `:5432` — 运行中（含 pgvector 扩展）
- React 前端 `:5173` — 运行中（Vite dev server）

**待验证**：LLM 端到端对话（需确认 API key 和代理 URL 可正常连通）。

---

## 已完成步骤

| # | 步骤 | 状态 | 说明 |
|---|------|------|------|
| 1 | 项目初始化 | ✅ | git init, pyproject.toml, uv sync |
| 2 | 环境配置 | ✅ | .env, pydantic-settings Settings |
| 3 | Docker Compose | ✅ | postgres(pgvector:pg16) + litellm |
| 4 | 数据库层 | ✅ | ORM 模型 + Alembic 迁移 + seed 脚本 |
| 5 | LLM 客户端 | ✅ | AsyncOpenAI → LiteLLM 代理 |
| 6 | 对话编排器 | ✅ | 流式/非流式 + SSE 事件 + 自动标题 |
| 7 | API 路由 | ✅ | 6 个端点（chat, stream, CRUD, models）|
| 8 | 中间件 + 入口 | ✅ | 全局异常处理 + 请求日志 + CORS |
| 9 | React 前端 | ✅ | 5 个组件 + SSE 流式 + Tailwind |
| 10 | Dockerfile | ✅ | 多阶段构建（node → python）|
| 11 | 测试 | ✅ | health check 测试通过 |
| 12 | Git 提交 | ✅ | 首次提交 62 文件 |

## 项目结构

```
k-assistant/
├── app/                        # FastAPI 后端
│   ├── api/
│   │   ├── chat.py             # 6 个 API 路由
│   │   └── deps.py             # 依赖注入（Phase 1 固定用户）
│   ├── core/
│   │   ├── chat.py             # 对话编排器（流式/非流式）
│   │   └── llm.py              # LLM 客户端封装
│   ├── db/
│   │   ├── base.py             # DeclarativeBase + Mixin
│   │   └── session.py          # 异步 session 管理
│   ├── middleware/
│   │   ├── error_handler.py    # 全局异常 → JSON
│   │   └── logging.py          # 请求日志中间件
│   ├── models/
│   │   ├── user.py             # 用户模型
│   │   ├── conversation.py     # 对话模型
│   │   └── message.py          # 消息模型
│   ├── schemas/
│   │   ├── chat.py             # 请求/响应 Pydantic 模型
│   │   └── common.py           # 通用错误响应
│   ├── config.py               # pydantic-settings 配置
│   └── main.py                 # FastAPI 入口 + lifespan
├── web/                        # React 前端
│   └── src/
│       ├── components/
│       │   ├── ChatArea.tsx     # 消息列表 + 输入区域
│       │   ├── ChatInput.tsx    # 输入框（Enter/Shift+Enter）
│       │   ├── MessageBubble.tsx # 消息气泡（Markdown 渲染）
│       │   ├── ModelSelector.tsx # 模型下拉选择
│       │   └── Sidebar.tsx     # 对话列表侧边栏
│       ├── api.ts              # API 客户端 + SSE 流式
│       ├── types.ts            # TypeScript 类型定义
│       └── App.tsx             # 主组件 + 状态管理
├── alembic/                    # 数据库迁移
├── scripts/seed.py             # 种子数据
├── tests/                      # 测试
├── docs/                       # 调研文档
├── docker-compose.yml          # postgres + litellm
├── litellm_config.yaml         # LiteLLM 模型配置
├── Dockerfile                  # 多阶段生产构建
├── pyproject.toml              # Python 依赖
└── .env                        # 环境变量
```

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/api/chat` | 非流式对话 |
| POST | `/api/chat/stream` | SSE 流式对话 |
| GET | `/api/conversations` | 对话列表 |
| GET | `/api/conversations/{id}` | 对话详情 + 历史消息 |
| DELETE | `/api/conversations/{id}` | 删除对话 |
| GET | `/api/models` | 可用模型列表 |

## 技术栈

| 层 | 技术 | 版本 |
|----|------|------|
| 后端框架 | FastAPI + Uvicorn | 0.115+ |
| ORM | SQLAlchemy (async) | 2.0+ |
| 数据库 | PostgreSQL + pgvector | 16 |
| 迁移 | Alembic (async) | 1.14+ |
| LLM 代理 | LiteLLM | latest |
| 前端 | React + TypeScript | 19.x + 5.9 |
| UI | Tailwind CSS | 4.x |
| 构建 | Vite | 7.x |
| 包管理 | uv (Python) / pnpm (Node) | 0.7 / 10.14 |

## 关键架构决策

1. **SSE（非 WebSocket）** — 单向流足够，curl 可调试
2. **LiteLLM 代理** — 统一多模型接口，支持自定义 base URL（如 minimaxi 代理）
3. **开发阶段 app 不入 Docker** — uvicorn --reload 本地跑，快速迭代
4. **fetch + ReadableStream** — EventSource 只支持 GET，POST 需要 ReadableStream
5. **pydantic-settings extra=ignore** — .env 中可放额外变量不报错

## 模型配置与验证

### 当前配置

通过 LiteLLM 配置（`litellm_config.yaml`），当前注册了 3 个模型别名：

| 前端选择 | LiteLLM 发出的 model 参数 |
|---------|--------------------------|
| `claude-sonnet` | `anthropic/claude-sonnet-4-20250514` |
| `claude-haiku` | `anthropic/claude-haiku-4-5-20251001` |
| `claude-opus` | `anthropic/claude-opus-4-20250514` |

### ANTHROPIC_BASE_URL 说明

当前配置 `ANTHROPIC_BASE_URL=https://api.minimaxi.com/anthropic`。这是一个第三方服务地址，请求链路为：

```
FastAPI → LiteLLM → api.minimaxi.com/anthropic → ?
```

LiteLLM 向该地址发送的请求中包含 model 参数，但**该服务实际如何处理请求是不透明的**——它可能：
- 原样转发到 Anthropic API（纯反代）
- 映射到其他模型
- 有自己的路由/降级逻辑

**前端模型选择器的实际效果取决于该服务的行为**，项目代码只保证将用户选择的模型名正确传递给了 LiteLLM。

### 如何验证实际调用的模型

无法仅通过模型的自我声明来判断，以下方法可辅助验证：

1. **对比能力差异** — 用同一道复杂推理题测试不同模型，如果回答质量明显不同，说明后端大概率路由到了不同模型
2. **检查 LiteLLM 日志** — `docker compose logs litellm` 查看实际发出的请求参数
3. **检查 response headers** — 部分代理会在响应头中透传原始模型信息
4. **直连对比** — 如有条件，将 `ANTHROPIC_BASE_URL` 改为 `https://api.anthropic.com`（直连），对比同一问题的响应，确认第三方服务是否有差异
5. **token 计费** — 登录 Anthropic 控制台查看 API 用量，确认是否有对应的调用记录（仅适用于使用自己的 API key 直连场景）

## 启动方式

```bash
# 1. 启动基础服务
docker compose up -d

# 2. 启动后端（开发模式）
uv run uvicorn app.main:app --reload --port 8000

# 3. 启动前端（开发模式）
pnpm --dir web dev

# 访问 http://localhost:5173
```

## Phase 2 建议方向

- 用户认证（JWT / OAuth）
- Tool Calls / Function Calling 支持
- 文件上传 + RAG（向量检索）
- 定时任务 / 提醒系统
- 多轮对话上下文窗口管理
- 部署方案（Docker Compose 全量编排）
