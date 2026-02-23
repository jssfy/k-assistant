# Phase 3 补充：聊天式定时任务管理

日期：2026-02-23

## 核心结论

- 采用 **Internal Tool Injection** 方案，将 `manage_tasks` 作为 LLM 可调用的内部工具注入
- 零改动聊天流程核心逻辑，仅扩展 tool 注入和路由
- 不需要 intent classification，LLM 通过 `tool_choice=auto` 自主决策何时调用

## 方案对比

| 方式 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| Internal Tool Injection | 零改动 chat.py 核心流程，复用 tool calling 机制 | 依赖 LLM 理解 tool description | **采用** |
| Intent Classification | 显式路由，可控性强 | 多一次 LLM 调用，增加路由复杂度 | 不采用 |
| 前端 UI | 可视化管理 | 需开发前端页面 | Phase 5 |

## 实现架构

```
用户聊天 → LLM (with manage_tasks tool) → tool_choice=auto
  → LLM 自主决定是否调用 manage_tasks
  → internal_tools.execute() → 直接操作 DB + scheduler
  → 返回结果 → LLM 生成自然语言回复
```

### 关键设计决策

1. **1 个聚合 tool vs 4 个独立 tool**：选择聚合 `manage_tasks(action=create|list|delete|toggle)`，减少 LLM 上下文 token 占用
2. **直接操作 DB**：内部工具直接操作 SQLAlchemy models + scheduler_engine，不走 HTTP API，避免额外开销
3. **user_id + db 传递**：通过修改 `_execute_tool_calls()` 签名传入，保持向后兼容（默认 None）

## 修改文件

| 文件 | 变更 |
|------|------|
| `app/core/internal_tools.py` | 新建 — manage_tasks tool 定义 + 执行逻辑 |
| `app/core/tools.py` | 新增 `get_all_tools_schema()` 和 `has_any_tools` |
| `app/core/chat.py` | `_execute_tool_calls()` 支持 internal tool 路由，`_get_tools()` 使用 `get_all_tools_schema()` |
| `README.md` | 全面更新，包含 Phase 1-3 全部功能文档 |
