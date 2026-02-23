# K-Assistant

个人 AI 助手 — FastAPI + React + LiteLLM 多模型对话系统，支持记忆、工具调用和定时任务。

## 架构概览

```
┌─────────────┐     ┌──────────────────────────────────────────────────┐
│  React 前端  │────▶│                 FastAPI 后端                      │
│  :5173       │     │                                                  │
└─────────────┘     │  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │
                    │  │ Chat API │  │ Task API │  │ Internal Tools│  │
                    │  └─────┬────┘  └─────┬────┘  └───────┬───────┘  │
                    │        │             │               │           │
                    │        ▼             ▼               ▼           │
                    │  ┌──────────────────────────────────────────┐    │
                    │  │          LLM (via LiteLLM :4000)         │    │
                    │  │  tool_choice=auto → MCP Tools / 内部工具   │    │
                    │  └──────────────────────────────────────────┘    │
                    │        │             │               │           │
                    │  ┌─────▼────┐  ┌─────▼────┐  ┌──────▼──────┐   │
                    │  │  Mem0    │  │ MCP 工具  │  │ APScheduler │   │
                    │  │ (记忆)   │  │ (搜索等)  │  │  (定时任务)  │   │
                    │  └──────────┘  └──────────┘  └─────────────┘   │
                    │                                                  │
                    │  ┌──────────────────────────────────────────┐    │
                    │  │       PostgreSQL + pgvector               │    │
                    │  └──────────────────────────────────────────┘    │
                    └──────────────────────────────────────────────────┘
```

**三个阶段**：
- **Phase 1**：核心对话（多模型、流式、对话历史）
- **Phase 2**：记忆系统（Mem0）+ 工具调用（MCP）
- **Phase 3**：定时任务（APScheduler + NL 解析 + 聊天管理）

## 快速开始

### 前置条件

- Docker & Docker Compose
- [uv](https://docs.astral.sh/uv/)（Python 包管理）
- Node.js ≥ 20 + pnpm

### 一键启动

```bash
# 首次安装（依赖 + 数据库 + 前端）
make setup

# 启动全部服务（Docker + 后端 + 前端）
make dev
```

### 手动启动

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 ANTHROPIC_API_KEY 等

# 2. 启动基础服务
docker compose up -d

# 3. 安装依赖 + 初始化数据库
uv sync
uv run alembic upgrade head
PYTHONPATH=. uv run python scripts/seed.py

# 4. 启动后端
uv run uvicorn app.main:app --reload --port 8000

# 5. 启动前端
pnpm --dir web install && pnpm --dir web dev
```

验证：`curl http://localhost:8000/health` → `{"status":"ok"}`

打开 http://localhost:5173 使用前端。

## Makefile 命令

```bash
make help       # 显示所有命令
make setup      # 首次安装
make dev        # 启动全部（Docker + 后端 + 前端）
make dev-api    # 仅启动后端
make dev-web    # 仅启动前端
make up/down    # 启动/停止 Docker 服务
make test       # 运行测试
make psql       # 进入数据库终端
make kill       # 停止本地进程
make kill-all   # 停止全部
```

## API 使用示例

### 对话

```bash
# 非流式对话
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "你好"}'

# 流式对话（SSE）
curl -N -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "你好"}'

# 指定模型 + 继续对话
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "继续", "model": "claude-haiku", "conversation_id": "xxx"}'
```

### 对话管理

```bash
# 对话列表
curl http://localhost:8000/api/conversations

# 对话详情 + 历史消息
curl http://localhost:8000/api/conversations/{id}

# 删除对话
curl -X DELETE http://localhost:8000/api/conversations/{id}

# 可用模型
curl http://localhost:8000/api/models
```

### 定时任务（curl）

```bash
# 创建任务 — 自然语言（LLM 自动解析 cron）
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "description": "每天早上9点搜索AI领域最新新闻并总结"
  }'

# 创建任务 — 显式 cron
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Weekly Report",
    "description": "生成本周工作总结",
    "cron_expression": "0 18 * * 5",
    "timezone": "Asia/Shanghai"
  }'

# 列出所有任务
curl http://localhost:8000/api/tasks

# 查看单个任务
curl http://localhost:8000/api/tasks/{task_id}

# 更新任务（暂停）
curl -X PUT http://localhost:8000/api/tasks/{task_id} \
  -H "Content-Type: application/json" \
  -d '{"is_active": false}'

# 更新任务（恢复 + 改 cron）
curl -X PUT http://localhost:8000/api/tasks/{task_id} \
  -H "Content-Type: application/json" \
  -d '{"is_active": true, "cron_expression": "0 10 * * *"}'

# 手动触发执行
curl -X POST http://localhost:8000/api/tasks/{task_id}/run

# 查看执行历史
curl http://localhost:8000/api/tasks/{task_id}/executions

# 删除任务
curl -X DELETE http://localhost:8000/api/tasks/{task_id}
```

### 聊天式任务管理

除了 curl，你也可以直接通过聊天创建和管理定时任务：

```
用户: "帮我创建一个定时任务，每天早上9点搜索AI新闻"
助手: "已创建定时任务「Daily AI News」，每天 9:00 执行，下次运行时间：明天 09:00"

用户: "列出我的所有定时任务"
助手: "你有 2 个定时任务：1. Daily AI News（每天 9:00）✅ 活跃  2. Weekly Report..."

用户: "暂停 Daily AI News 任务"
助手: "已暂停任务「Daily AI News」"
```

LLM 会自动识别任务管理意图并调用内部 `manage_tasks` 工具，无需记忆 API 格式。

## 配置

### 环境变量（`.env`）

```env
# 必填
ANTHROPIC_API_KEY=sk-ant-xxx

# 可选
ANTHROPIC_BASE_URL=https://api.minimaxi.com/anthropic  # API 代理
OPENAI_API_KEY=sk-xxx                                    # GPT 模型
DEFAULT_MODEL=claude-sonnet                               # 默认模型
MEM0_ENABLED=true                                         # 记忆系统
MCP_SERVERS_CONFIG=mcp_servers.json                       # MCP 工具配置
SCHEDULER_ENABLED=true                                    # 定时任务
```

### 模型配置

通过 LiteLLM 配置（`litellm_config.yaml`）：

| 前端选择 | 实际模型 |
|---------|---------|
| `claude-sonnet` | `anthropic/claude-sonnet-4-20250514` |
| `claude-haiku` | `anthropic/claude-haiku-4-5-20251001` |
| `claude-opus` | `anthropic/claude-opus-4-20250514` |

添加新模型：编辑 `litellm_config.yaml`，然后 `docker compose restart litellm`。

### MCP 工具配置

编辑 `mcp_servers.json` 添加工具服务器：

```json
{
  "servers": [
    {
      "name": "web-search",
      "command": "npx",
      "args": ["-y", "@anthropic/mcp-server-web-search"],
      "env": {"BRAVE_API_KEY": "xxx"}
    }
  ]
}
```

## 开发

### 运行测试

```bash
uv run pytest -v
```

### 数据库操作

```bash
# 进入 psql
make psql

# 常用查询
\dt                                          # 所有表
SELECT * FROM users;                         # 用户
SELECT id, title, model FROM conversations ORDER BY created_at DESC;
SELECT id, name, cron_expression, is_active FROM scheduled_tasks;
SELECT task_id, status, result FROM task_executions ORDER BY created_at DESC;

# 数据库迁移
uv run alembic revision --autogenerate -m "description"
uv run alembic upgrade head
uv run alembic downgrade -1
```

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | FastAPI, SQLAlchemy (async), Alembic |
| 数据库 | PostgreSQL 16 + pgvector |
| LLM 代理 | LiteLLM |
| 记忆 | Mem0 |
| 工具 | MCP (Model Context Protocol) |
| 定时任务 | APScheduler 3.x + PostgreSQL 持久化 |
| 前端 | React 19, TypeScript, Tailwind CSS 4, Vite |
| 包管理 | uv (Python), pnpm (Node) |

## 项目结构

```
├── app/
│   ├── api/              # 路由（chat, tasks）+ 依赖注入
│   ├── core/             # LLM 客户端、对话编排、工具管理、内部工具
│   ├── db/               # 数据库引擎 + session
│   ├── middleware/        # 异常处理 + 日志
│   ├── models/           # ORM 模型（User, Conversation, Message, ScheduledTask, TaskExecution）
│   ├── schemas/          # Pydantic 模型
│   ├── scheduler/        # 定时任务引擎、NL 解析、任务执行器
│   ├── config.py         # 配置
│   └── main.py           # 入口 + lifespan
├── web/                  # React 前端
├── alembic/              # 数据库迁移
├── mcp_servers/          # MCP 服务器配置
├── scripts/              # 工具脚本（seed.py）
├── tests/                # 测试
├── docs/                 # 设计文档
├── docker-compose.yml    # PostgreSQL + LiteLLM
├── litellm_config.yaml   # 模型配置
├── Makefile              # 开发命令
└── pyproject.toml        # Python 项目配置
```
