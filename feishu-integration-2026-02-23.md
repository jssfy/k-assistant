# Phase 4: 飞书双向集成 — 实现记录

## 核心结论

- **完成 8 个步骤**的飞书集成实现：配置、客户端、输出层、DB迁移、任务输出路由、内部工具、Webhook接收、主应用注册
- **功能降级安全**：`FEISHU_ENABLED=false`（默认）时所有飞书功能不加载，零影响
- **两种发送模式**：Webhook（无需认证，适合群推送）+ Bot API（需 token，适合回复消息）
- **消息接收双通道**：WebSocket 长连接（主要，无需公网域名）+ HTTP webhook（保留作后备）

## 新建文件

| 文件 | 用途 |
|------|------|
| `app/feishu/__init__.py` | 包初始化 |
| `app/feishu/client.py` | FeishuClient 单例：token 管理、Bot API、Webhook 发送 |
| `app/feishu/handler.py` | 共享消息处理逻辑：事件去重、文本提取、LLM 处理+回复 |
| `app/feishu/webhook.py` | HTTP 事件接收路由：URL验证 + 调用 handler 共享逻辑 |
| `app/feishu/ws_listener.py` | FeishuWSListener 单例：daemon 线程运行 lark.ws.Client 长连接 |
| `app/output/__init__.py` | 包初始化 |
| `app/output/base.py` | SendResult 数据类 |
| `app/output/feishu.py` | 飞书发送函数（自动检测 webhook/bot API 模式） |
| `app/output/router.py` | 输出路由分发器 |
| `alembic/versions/8a8ed330400f_*.py` | task_executions 新增 output_status JSONB 列 |

## 修改文件

| 文件 | 变更 |
|------|------|
| `app/config.py` | 添加 6 个 FEISHU_* 配置项 |
| `app/main.py` | 注册 feishu_client + feishu_ws_listener 生命周期 + feishu_router |
| `app/core/internal_tools.py` | 添加 send_feishu 工具（schema + 执行逻辑） |
| `app/scheduler/task_runner.py` | 任务执行后调用 output dispatch |
| `app/models/task_execution.py` | 添加 output_status 列 |
| `app/schemas/task.py` | TaskExecutionOut 添加 output_status 字段 |
| `pyproject.toml` | 添加 `lark-oapi>=1.3.0` 依赖 |
| `.env.example` | 添加飞书配置示例 |

## 配置操作指南

### 1. 获取飞书应用凭证

在 [飞书开放平台](https://open.feishu.cn) → 你的应用：

| 配置项 | 获取位置 |
|--------|----------|
| `FEISHU_APP_ID` | 左侧导航 →「凭证与基础信息」→ App ID |
| `FEISHU_APP_SECRET` | 左侧导航 →「凭证与基础信息」→ App Secret |
| `FEISHU_VERIFICATION_TOKEN` | 左侧导航 →「事件与回调」→「加密策略」标签页 → Verification Token |
| `FEISHU_ENCRYPT_KEY` | 左侧导航 →「事件与回调」→「加密策略」标签页 → Encrypt Key |
| `FEISHU_WEBHOOK_URL` | 在目标群 → 群设置 → 群机器人 → 添加自定义机器人 → 获取 webhook 地址 |

### 2. 事件订阅方式

飞书支持两种事件接收模式，**当前代码两种均已实现**：

| 模式 | 说明 | 是否需要公网域名 | 代码支持 |
|------|------|:---:|:---:|
| **长连接（WebSocket）** | 客户端主动连飞书，推荐 | 不需要 | 已实现（`ws_listener.py`） |
| **HTTP 回调（Webhook）** | 飞书 POST 到你的回调 URL | 需要 | 已实现（`webhook.py`） |

**推荐：长连接模式（默认启用）**

应用启动时自动建立 WebSocket 长连接，无需配置公网域名。在飞书开放平台配置：
1. 在「事件与回调」页面 → 订阅方式旁点击编辑按钮
2. 选择「使用长连接接收事件」
3. 无需填写回调 URL，保存即可

**备选：HTTP 回调模式**

如需使用 HTTP 回调模式（需要公网域名）：
1. 在「事件与回调」页面 → 订阅方式旁点击编辑按钮
2. 选择「将事件发送至请求地址」
3. 填入回调 URL：`https://<your-domain>/webhook/feishu`
4. 飞书会发送 challenge 验证请求，代码会自动响应

> 两条接收路径共享同一个去重缓存，即使同时开启也不会重复处理。

### 3. 需要开通的权限

在左侧导航 →「权限管理」中，开通以下权限：

- `im:message` — 获取与发送单聊、群组消息
- `im:message.group_at_msg` — 接收群聊中 @ 机器人消息
- `im:resource` — 获取消息中的资源文件

### 4. 需要订阅的事件

在「事件与回调」→「添加事件」中，订阅：

- **接收消息** `im.message.receive_v1` — 用户给机器人发消息时触发

### 5. 加密策略说明

| 变量 | 必需性 | 说明 |
|------|--------|------|
| `FEISHU_VERIFICATION_TOKEN` | 生产环境建议必填 | 验证请求来源是否真的是飞书，防伪造。留空则跳过验证 |
| `FEISHU_ENCRYPT_KEY` | 可选，当前建议不填 | 对事件体 AES 加密传输。**当前代码未实现解密**，如在飞书后台设置了则会解析失败 |

### 6. 最小化 .env 配置示例

```bash
FEISHU_ENABLED=true
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_VERIFICATION_TOKEN=xxx
# FEISHU_ENCRYPT_KEY=          # 飞书后台不要设置，留空
# FEISHU_WEBHOOK_URL=          # 可选，用于定时任务推送和 send_feishu 工具的默认目标
```

## 关键设计点

### FeishuClient Token 管理
- asyncio.Lock 保护并发刷新
- 5 分钟提前刷新缓冲
- Double-check pattern 避免重复请求

### 消息接收架构（双通道）

**共享处理逻辑 (`handler.py`)**：
- `dedup_event()` — OrderedDict 有界去重缓存（上限 1000），webhook 和 WS 共享
- `extract_text_from_dict()` — 从 webhook 原始 dict 提取文本
- `extract_text_from_sdk_event()` — 从 SDK P2ImMessageReceiveV1 对象提取文本
- `process_feishu_message()` — 调用 `core.chat()` + `reply_message()`，复用完整对话能力
- 群聊仅响应 @机器人 消息，自动去除 @mention 文本

**WebSocket 长连接 (`ws_listener.py`)**：
- 使用 `lark-oapi` SDK 的 `lark.ws.Client`，SDK 负责认证、心跳（120s）、自动重连
- Daemon 线程运行独立 event loop（解决 uvloop 冲突：SDK 模块级 `loop` 变量需 monkey-patch）
- 事件回调通过 `asyncio.run_coroutine_threadsafe()` 桥接到主 asyncio 事件循环
- 线程模型：

```
Main Thread (asyncio/uvloop)              Daemon Thread "feishu-ws" (独立 event loop)
  │                                         │
  ├─ FastAPI serves HTTP                    ├─ lark.ws.Client.start() [blocks]
  │                                         │   ├─ websockets.connect(wss://...)
  │                                         │   ├─ _receive_message_loop()
  │                                         │   └─ _ping_loop()
  │                                         │
  │  ◄── run_coroutine_threadsafe ──────────│  _on_message_receive() [sync]
  │                                         │
  ├─ process_feishu_message() runs HERE     │
  │   └─ chat() → reply_message()           │
```

**HTTP Webhook (`webhook.py`)**：
- URL verification challenge 直接返回
- 调用 handler.py 共享函数处理消息

### 输出路由
- `task_config.output` 字段驱动，不新建表
- 支持单个或列表格式的 output_config
- 按 type 字段分发，目前支持 `feishu`
- 结果记录到 execution.output_status JSONB

### send_feishu 内部工具
- 仅 `FEISHU_ENABLED=true` 时注册到 LLM 工具列表
- 支持指定 target 或使用默认 FEISHU_WEBHOOK_URL
- target 以 http 开头 → webhook 模式，否则 → bot API 模式
