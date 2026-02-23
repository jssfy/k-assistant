# K-Assistant

个人 AI 助手 — FastAPI + React + LiteLLM 多模型对话系统。

## 快速开始

### 前置条件

- Docker & Docker Compose
- [uv](https://docs.astral.sh/uv/) (Python 包管理)
- Node.js ≥ 20 + pnpm

### 1. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，填入必要的 API Key：

```env
# 必填：Anthropic API Key（直连或代理）
ANTHROPIC_API_KEY=sk-ant-xxx

# 可选：自定义 Anthropic API 代理地址
ANTHROPIC_BASE_URL=https://api.minimaxi.com/anthropic

# 可选：OpenAI API Key（如需 GPT 模型）
OPENAI_API_KEY=sk-xxx
```

### 2. 启动基础服务

```bash
docker compose up -d
```

等待服务就绪（约 15-20 秒）：

```bash
# 检查状态
docker compose ps

# 验证 PostgreSQL
docker compose exec postgres pg_isready -U postgres

# 验证 LiteLLM
curl http://localhost:4000/health/liveliness
```

### 3. 初始化数据库

首次运行需要执行迁移和种子数据：

```bash
uv sync
uv run alembic upgrade head
PYTHONPATH=. uv run python scripts/seed.py
```

### 4. 启动后端

```bash
uv run uvicorn app.main:app --reload --port 8000
```

验证：`curl http://localhost:8000/health` → `{"status":"ok"}`

### 5. 启动前端

```bash
pnpm --dir web install
pnpm --dir web dev
```

打开 http://localhost:5173 即可使用。

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

### 示例：非流式对话

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "你好"}'
```

### 示例：流式对话

```bash
curl -N -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "你好"}'
```

### 示例：指定模型 / 继续对话

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "继续", "model": "claude-haiku", "conversation_id": "xxx"}'
```

## 模型配置

通过 LiteLLM 配置（`litellm_config.yaml`），前端可选模型：

| 前端选择 | LiteLLM 发出的 model 参数 |
|---------|--------------------------|
| `claude-sonnet` | `anthropic/claude-sonnet-4-20250514` |
| `claude-haiku` | `anthropic/claude-haiku-4-5-20251001` |
| `claude-opus` | `anthropic/claude-opus-4-20250514` |

> **注意**：如果 `ANTHROPIC_BASE_URL` 配置了第三方服务地址，实际调用的模型取决于该服务如何处理请求，项目代码只保证将模型名正确传递。详见 [Phase 1 进度文档](docs/phase1-progress-2026-02-23.md) 中的验证方法。

添加新模型：编辑 `litellm_config.yaml`，然后 `docker compose restart litellm`。

## 开发

### 运行测试

```bash
uv run pytest -v
```

### 查看数据库

```bash
# 进入 psql 交互终端
docker compose exec postgres psql -U postgres -d k_assistant

# 常用查询
\dt                                          # 查看所有表
SELECT * FROM users;                         # 查看用户
SELECT id, title, model, created_at FROM conversations ORDER BY created_at DESC;  # 对话列表
SELECT role, LEFT(content, 80), token_usage FROM messages ORDER BY created_at;    # 消息记录
\q                                           # 退出
```

### 数据库迁移

```bash
# 生成迁移
uv run alembic revision --autogenerate -m "description"

# 执行迁移
uv run alembic upgrade head

# 回滚
uv run alembic downgrade -1
```

### 停止服务

```bash
docker compose down        # 停止容器（保留数据）
docker compose down -v     # 停止容器 + 删除数据卷
```

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | FastAPI, SQLAlchemy (async), Alembic |
| 数据库 | PostgreSQL 16 + pgvector |
| LLM 代理 | LiteLLM |
| 前端 | React 19, TypeScript, Tailwind CSS 4, Vite |
| 包管理 | uv (Python), pnpm (Node) |

## 项目结构

```
├── app/                  # FastAPI 后端
│   ├── api/              # 路由 + 依赖注入
│   ├── core/             # LLM 客户端 + 对话编排
│   ├── db/               # 数据库引擎 + session
│   ├── middleware/        # 异常处理 + 日志
│   ├── models/           # ORM 模型
│   ├── schemas/          # Pydantic 模型
│   ├── config.py         # 配置
│   └── main.py           # 入口
├── web/                  # React 前端
├── alembic/              # 数据库迁移
├── scripts/              # 工具脚本
├── tests/                # 测试
├── docs/                 # 设计文档
├── docker-compose.yml    # 基础服务
├── litellm_config.yaml   # 模型配置
└── Dockerfile            # 生产构建
```
