# K-Assistant 测试与部署验证报告

> 日期：2026-02-23

## 核心结论

1. **修复了 3 个阻塞性问题**后，全部功能通过自测
   - `psycopg` 依赖缺失 → Memory 系统初始化失败
   - LiteLLM `store` 参数不兼容 → Memory 存储静默失败
   - LiteLLM 容器缺少 `curl` → Docker healthcheck 始终 unhealthy
2. `make dev` 一键部署方案可正常启动全部 5 个组件（PostgreSQL、LiteLLM、FastAPI、Vite、MCP）
3. 建议后续补充自动化集成测试脚本（当前为手动 curl 验证）

---

## 一、Bug 修复记录

### 1.1 缺少 psycopg 依赖

| 项目 | 内容 |
|------|------|
| **现象** | 启动时 `memory.init_failed`，`ImportError: Neither 'psycopg' nor 'psycopg2' library is available` |
| **原因** | Mem0 使用 pgvector 作为向量存储，需要 psycopg 驱动，但 `pyproject.toml` 未声明 |
| **修复** | `pyproject.toml` 添加 `psycopg[binary,pool]>=3.1.0` |
| **验证** | 重启后日志输出 `memory.initialized collection=k_assistant` |

### 1.2 LiteLLM store 参数不兼容

| 项目 | 内容 |
|------|------|
| **现象** | Memory 的 `add()` 返回空结果 `{'results': []}`，无报错（fire-and-forget 吞掉异常） |
| **原因** | Mem0 内部调 LLM 提取记忆时传了 OpenAI 的 `store` 参数，Anthropic 模型不支持，LiteLLM 返回 400 |
| **修复** | `litellm_config.yaml` 添加 `litellm_settings: drop_params: true` |
| **验证** | `memory_manager.add()` 成功返回提取的记忆条目 |

### 1.3 LiteLLM Docker healthcheck 失败

| 项目 | 内容 |
|------|------|
| **现象** | `docker compose ps` 显示 LiteLLM 容器 `unhealthy`，但服务实际可用 |
| **原因** | healthcheck 使用 `curl` 命令，但 LiteLLM 容器镜像内未安装 curl |
| **修复** | 改用 Python 内置 `urllib`：`python -c "import urllib.request; urllib.request.urlopen(...)"` |
| **验证** | 重建容器后状态变为 `healthy` |

---

## 二、make dev 部署方案测试

### 2.1 部署架构

```
make dev
  ├── docker compose up -d
  │     ├── PostgreSQL 16 + pgvector  (port 5432)
  │     └── LiteLLM Proxy             (port 4000)
  ├── uvicorn app.main:app --reload   (port 8000)
  │     ├── FastAPI 后端
  │     ├── Memory 系统 (Mem0 + HuggingFace embeddings)
  │     └── MCP Tool 服务器 (web-search)
  └── pnpm --dir web dev              (port 5173)
        └── Vite + React 前端 (proxy → 8000)
```

### 2.2 组件启动验证

| 组件 | 验证命令 | 预期结果 | 实测结果 |
|------|----------|----------|----------|
| PostgreSQL | `docker compose exec -T postgres pg_isready -U postgres` | accepting connections | OK (healthy) |
| LiteLLM | `curl -H "Authorization: Bearer sk-1234" http://localhost:4000/health` | healthy_endpoints: 3 | OK (3 models healthy) |
| FastAPI | `curl http://localhost:8000/health` | `{"status":"ok"}` | OK |
| Vite 前端 | `curl http://localhost:5173/` | HTTP 200 | OK |
| 前端代理 | `curl http://localhost:5173/api/models` | models JSON | OK |
| DB 表结构 | `psql -c "\dt"` | 6 tables (users, conversations, messages, k_assistant, mem0migrations, alembic_version) | OK |
| 种子数据 | `SELECT * FROM users` | Default User (UUID ...0001) | OK |
| Memory 初始化 | 启动日志 | `memory.initialized collection=k_assistant` | OK |
| MCP 工具注册 | 启动日志 | `tools.initialized servers=1 tools=1` | OK |

### 2.3 启动顺序依赖

```
PostgreSQL (healthy) → LiteLLM (depends_on postgres healthy)
                     → FastAPI (connects to postgres + litellm)
                       → Mem0 (uses postgres pgvector + litellm LLM)
                       → MCP (spawns web-search subprocess)
Vite 前端（独立启动，proxy 到 FastAPI）
```

关键点：
- PostgreSQL 必须先 healthy，LiteLLM 才会启动（docker-compose `depends_on` 保证）
- FastAPI 的 `app.startup` 中初始化 Memory 和 Tools，若 LiteLLM 未就绪可能导致 Memory 初始化失败（当前为 graceful degradation，不会阻塞启动）
- Vite 前端启动不依赖后端，但在后端未就绪时 proxy 请求会报 `ECONNREFUSED`（短暂，后端就绪后自动恢复）

---

## 三、API 端点测试

### 3.1 聊天功能

| 测试场景 | 方法 | 端点 | 结果 |
|----------|------|------|------|
| 非流式聊天 | POST | `/api/chat` | OK — 返回 conversation_id + message |
| 流式聊天 | POST | `/api/chat/stream` | OK — SSE events: metadata → message → done |
| 对话续聊 | POST (带 conversation_id) | `/api/chat/stream` | OK — 消息追加到同一会话 |
| 多模型切换 | POST (model=claude-haiku/sonnet) | `/api/chat/stream` | OK — 不同模型均可响应 |
| 无效模型 | POST (model=nonexistent) | `/api/chat` | OK — 返回 502 + 错误信息 |
| 缺少 message | POST (无 message 字段) | `/api/chat` | OK — 返回 422 验证错误 |

**流式响应格式验证：**

```
event: metadata
data: {"conversation_id": "uuid", "model": "claude-sonnet"}

event: message        # 可多次
data: {"content": "...chunk..."}

event: done
data: {"message_id": "uuid"}
```

### 3.2 会话管理

| 测试场景 | 方法 | 端点 | 结果 |
|----------|------|------|------|
| 列出会话 | GET | `/api/conversations` | OK — 按 updated_at 降序 |
| 获取会话详情（含消息） | GET | `/api/conversations/{id}` | OK — 包含完整消息列表 |
| 删除会话 | DELETE | `/api/conversations/{id}` | OK — 204 No Content |
| 查询不存在的会话 | GET | `/api/conversations/{id}` | OK — 404 |

### 3.3 记忆系统

| 测试场景 | 方法 | 端点 | 结果 |
|----------|------|------|------|
| 列出记忆 | GET | `/api/memories` | OK — 返回所有记忆条目 |
| 搜索记忆 | GET | `/api/memories/search?q=programming` | OK — 返回相关记忆 |
| 删除记忆 | DELETE | `/api/memories/{id}` | OK — 204 |
| 聊天时自动存储记忆 | POST chat → GET memories | OK — 异步存储，约 10-15s 延迟 |
| 聊天时召回记忆 | POST chat (新会话) | OK — 系统提示中注入记忆上下文 |

**记忆端到端流程：**

```
1. 用户发送 "I have a golden retriever named Max"
2. LLM 正常回复（流式）
3. 后台 fire-and-forget: Mem0 调 LLM 提取记忆 → 写入 pgvector
4. 新会话中用户问 "What do you know about me?"
5. 系统搜索相关记忆 → 注入 system prompt → LLM 回复引用记忆内容
```

实测记忆提取结果：
- 输入："My favorite programming language is Python and I work at TechCorp"
- 提取："Likes Python programming" + "Works at TechCorp"（两条独立记忆）

### 3.4 MCP 工具调用

| 测试场景 | 方法 | 结果 |
|----------|------|------|
| web_search 工具调用 | POST chat "Search for weather in Tokyo" | OK — tool_call → tool_result → message |
| 工具注册 | 启动日志 | OK — `tools.registered server=web-search tool=web_search` |

**工具调用流式响应格式：**

```
event: metadata
event: tool_call       # {"tool": "web_search", "arguments": {...}}
event: tool_result     # {"tool": "web_search", "result": "..."}
event: message         # LLM 基于工具结果的回复
event: done
```

### 3.5 模型管理

| 测试场景 | 方法 | 端点 | 结果 |
|----------|------|------|------|
| 列出模型 | GET | `/api/models` | OK — 返回 claude-sonnet, claude-haiku, claude-opus |

---

## 四、修改的文件清单

| 文件 | 修改内容 |
|------|----------|
| `pyproject.toml` | 添加 `psycopg[binary,pool]>=3.1.0` 依赖 |
| `litellm_config.yaml` | 添加 `litellm_settings: drop_params: true` |
| `docker-compose.yml` | LiteLLM healthcheck 从 `curl` 改为 `python urllib` |

---

## 五、已知限制与后续建议

1. **Memory 存储延迟**：fire-and-forget 模式下，Mem0 需调 LLM 提取记忆，延迟 10-15s，不影响用户体验但需了解
2. **无自动化集成测试**：当前仅有 `test_health` 单元测试，建议补充 API 集成测试
3. **LiteLLM 启动时间**：容器启动到 healthy 约需 15-20s，`make dev` 中 FastAPI 可能在此期间启动，Memory 初始化可能需重启后端
4. **单用户模式**：Phase 1 使用 hardcoded user ID，所有记忆共享同一用户
