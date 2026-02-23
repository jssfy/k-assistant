# AI Assistant Memory Systems & Multi-Model Switching: Technical Research

## Core Conclusions

1. **Memory architecture consensus**: The field has converged on a tiered memory pattern: in-context working memory (small, always present) + external storage (large, retrieved on demand). MemGPT/Letta, LangMem, and Mem0 all implement variations of this.

2. **Three memory types are universal**: Semantic memory (facts/knowledge), episodic memory (past interactions), and procedural memory (behavioral rules) appear across all major frameworks.

3. **Dual retrieval is best practice**: Combine vector similarity search with either graph traversal or structured metadata filtering. Mem0's hybrid vector+graph approach achieves 26% better results than vector-only.

4. **For multi-model switching**: LiteLLM proxy is the most mature abstraction layer -- OpenAI-compatible API gateway supporting 100+ providers with 8ms P95 latency. Open WebUI and LobeChat both use proxy architectures to normalize requests across providers.

5. **Single-server recommendation**: PostgreSQL + pgvector for unified relational+vector storage, or SQLite for metadata + Qdrant for vectors. Avoid ChromaDB for production (HNSW index must fit entirely in RAM). Total overhead for memory+vector+chat services: 4-8GB RAM without local models, 16-64GB with local models.

---

## 1. Memory Systems in AI Assistants

### 1.1 MemGPT / Letta: OS-Inspired Tiered Memory

MemGPT treats the LLM context window as a constrained memory resource, implementing a hierarchy analogous to an operating system's virtual memory system (RAM vs disk).

**Memory Tiers:**

| Tier | Analogy | Storage | Size | Access |
|------|---------|---------|------|--------|
| **Core Memory** (in-context blocks) | RAM | Context window | Limited by token budget | Always present, directly editable by agent |
| **Recall Memory** | Filesystem | Database (searchable) | Unlimited | Semantic search retrieval |
| **Archival Memory** | External storage | Vector DB / Graph DB | Unlimited | Query-based retrieval |
| **Message Buffer** | CPU cache | Recent messages | Rolling window | Automatic, most recent |

**Key mechanisms:**

- **Self-editing memory**: The agent has tools (`core_memory_append`, `core_memory_replace`) to modify its own in-context memory blocks. Each block has a label, description, value, and character limit.
- **Message eviction & summarization**: When context capacity is reached, older messages are recursively summarized. Older messages have progressively less influence on summaries.
- **Sleep-time compute**: Asynchronous memory management agents refine memory during idle periods, not just during active conversation.

**Storage backends**: Letta supports PostgreSQL for metadata/recall and configurable vector stores (Chroma, Qdrant, pgvector) for archival memory.

### 1.2 LangChain / LangGraph: Checkpointing + LangMem

LangGraph implements a two-layer memory system:

**Short-term memory (Checkpointing):**
- `InMemorySaver` for ephemeral state
- `SqliteSaver` or `PostgresSaver` for persistent checkpoints
- Stores full graph execution state, messages, and metadata per thread
- Supports time-travel (rewind to any checkpoint)

**Long-term memory (Cross-thread Store):**
- JSON documents organized in hierarchical namespaces (org -> user -> context)
- `BaseStore` interface with pluggable backends (InMemory, MongoDB, PostgreSQL)
- Three retrieval methods: key-based, semantic similarity search, metadata filtering

**LangMem SDK (dedicated memory library):**

Three memory types with specific implementations:

| Type | Purpose | Implementation |
|------|---------|---------------|
| **Semantic** | Facts & knowledge | Collections (unbounded docs) or Profiles (structured schemas) |
| **Episodic** | Past experiences | Observation + reasoning + action + outcome tuples |
| **Procedural** | Behavioral rules | System prompt evolution through feedback |

**Memory formation modes:**
- **Active (conscious)**: During conversation, immediate but adds latency
- **Background (subconscious)**: After conversation, no latency impact, better for pattern analysis

**Memory managers** handle extraction, update, and consolidation. Reconciliation processes merge new facts with existing memories (similar to Mem0's ADD/UPDATE/DELETE/NOOP operations).

### 1.3 Mem0: Universal Memory Layer

Mem0 operates as a middleware memory layer between application and LLM with a two-phase pipeline:

**Phase 1 - Extraction:**
1. Collect recent messages + summary of older context
2. Prompt LLM to distill atomic facts from conversation

**Phase 2 - Update:**
1. Embed each candidate fact
2. Retrieve top-K semantically similar existing memories from vector DB
3. LLM decides action: `ADD` (new fact), `UPDATE` (augment existing), `DELETE` (contradicts/obsolete), or `NOOP` (already known)

**Dual storage architecture:**

```
Conversation -> LLM Extraction -> Candidate Facts
                                       |
                    +------------------+------------------+
                    |                                     |
              Vector Store                          Graph Store
         (semantic similarity)                 (entity relationships)
              Qdrant/Chroma/                    Neo4j/Memgraph/
              PGVector/etc.                     Neptune/Kuzu
```

- **Vector store**: Embeddings + metadata filters. Default: Qdrant. Supports 25+ providers via `VectorStoreFactory`.
- **Graph store** (Mem0g variant): Extracts entities as nodes, relationships as edges. Directed labeled graphs. Enables multi-hop reasoning across connected facts.

**Retrieval**: Vector search and graph traversal run in parallel. Vector narrows candidates; graph adds relational context. Results merged and returned.

**Performance**: 26% improvement over OpenAI memory (LLM-as-Judge), 91% lower P95 latency, 90%+ token cost savings vs full-context approaches.

### 1.4 Common Patterns Summary

| Pattern | How It Works | Strengths | Weaknesses |
|---------|-------------|-----------|------------|
| **Vector store (RAG)** | Embed memories, retrieve by similarity | Simple, fast, semantic matching | No relationship reasoning, context fragmentation |
| **Knowledge graph** | Entities + relationships as nodes/edges | Multi-hop reasoning, explicit relations | Complex to maintain, extraction quality varies |
| **Structured summaries** | LLM-generated fact summaries | Token-efficient, readable | Lossy compression, hallucination risk |
| **Hybrid (vector + graph)** | Parallel retrieval, merged results | Best accuracy (Mem0 benchmarks) | Higher complexity, dual storage overhead |
| **Tiered (MemGPT style)** | In-context + external, OS-like management | Agent autonomy, self-editing | Relies on agent tool-use quality |

**Retrieval strategies observed across systems:**
- **Semantic search** (all systems): Embed query, find nearest neighbors
- **Recency-based** (MemGPT, LangGraph): Recent messages weighted higher, recursive summarization for older content
- **Metadata filtering** (LangMem, Mem0): Filter by user, time range, topic before vector search
- **Graph traversal** (Mem0g): Follow entity relationships for multi-hop queries

---

## 2. Multi-Model Switching

### 2.1 Open WebUI: Dual-Proxy Architecture

Open WebUI implements a backend proxy pattern where the frontend never directly contacts LLM servers.

**Architecture:**

```
Browser -> Open WebUI Backend -> Ollama (local models)
                              -> OpenAI-compatible APIs (cloud)
                              -> Custom endpoints
```

**Key design decisions:**
- **Proxy-based routing**: All requests go through the backend, which handles auth, CORS, payload transformation, and response streaming
- **Model catalog aggregation**: Models from multiple sources unified into a single list with two-tier caching (base models cache + TTL-based per-user cache)
- **Request routing by `owned_by`**: `"ollama"` -> Ollama adapter; `"openai"` -> OpenAI-compatible upstream; `"arena"` -> arena/ensemble selection
- **Format normalization**: Ollama native responses converted to OpenAI-compatible format (`convert_embedding_response_ollama_to_openai()`)
- **Load distribution**: `random.choice()` across multiple backend URLs (simple but functional)

**Tech stack**: Python/FastAPI backend, SvelteKit frontend, SQLite for settings/users.

### 2.2 LobeChat: Plugin-Based Provider System

LobeChat uses a monorepo architecture with a shared `model-runtime` package.

**Architecture:**
- Unified backend adapter supporting OpenAI/Claude/Gemini/Ollama/Qwen and local LLMs
- EdgeRuntime API for serverless deployment
- Plugin Gateway (`POST /api/v1/runner`) for extensibility
- MCP (Model Context Protocol) support for tool integration

**Provider configuration**: Environment variables per provider (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.) with runtime model selection in the UI.

### 2.3 LiteLLM: The Universal Proxy

LiteLLM is the most mature abstraction layer, providing an OpenAI-compatible API gateway.

**Architecture:**

```
Client (OpenAI SDK) -> LiteLLM Proxy (port 4000) -> 100+ LLM providers
                            |
                      PostgreSQL (logging, tracking)
```

**Key features:**
- **Unified API**: Single OpenAI-format endpoint for all providers
- **Provider translation**: Automatic request/response format conversion
- **Operational controls**: Rate limiting, budgets, retries, fallbacks, load balancing
- **Multi-tenant**: Organizations -> Teams -> Users hierarchy
- **Observability**: Cost tracking, logging, metrics
- **Performance**: 8ms P95 latency at 1,000 RPS

**Configuration example (yaml):**
```yaml
model_list:
  - model_name: gpt-4
    litellm_params:
      model: openai/gpt-4
      api_key: sk-xxx
  - model_name: claude-3
    litellm_params:
      model: anthropic/claude-3-opus
      api_key: sk-ant-xxx
  - model_name: local-llama
    litellm_params:
      model: ollama/llama3
      api_base: http://localhost:11434
```

### 2.4 OpenRouter: Cloud-Native Routing

OpenRouter provides a managed routing service with:
- Edge-based architecture adding ~25ms overhead
- Automatic failover across 50+ providers
- Real-time latency/throughput metrics (rolling 5-minute windows)
- Routing strategies: price-optimized, latency-optimized, or custom
- Same OpenAI-compatible API format

### 2.5 Multi-Model Architecture Recommendation

For a self-hosted single-server setup:

```
                    +---> Ollama (local models: Llama, Mistral, Qwen)
                    |
LiteLLM Proxy ------+---> OpenAI API (GPT-4, etc.)
(port 4000)         |
                    +---> Anthropic API (Claude, etc.)
                    |
                    +---> Any OpenAI-compatible endpoint
```

**Why LiteLLM over alternatives:**
- Open source, self-hosted (no data leaves your server for routing)
- Drop-in replacement for OpenAI SDK on the client side
- Built-in fallback chains (if provider A fails, try B)
- Cost tracking and budget enforcement
- Can run alongside Ollama on the same server

---

## 3. Single-Server Deployment Considerations

### 3.1 Storage: SQLite vs PostgreSQL vs Redis

| Aspect | SQLite | PostgreSQL | Redis |
|--------|--------|------------|-------|
| **Best for** | Embedded apps, low concurrency, prototypes | Multi-service, concurrent access, complex queries | Caching, sessions, real-time pub/sub |
| **Concurrency** | Single-writer | Full MVCC, many concurrent writers | Single-threaded (but fast), pipelining |
| **Vector support** | None native | pgvector extension (HNSW, IVFFlat) | Redis Vector Library (limited) |
| **Memory footprint** | ~0 (file-based) | 50-200MB base | 50-100MB base + data in RAM |
| **Ops complexity** | Zero | Moderate (tuning, vacuuming) | Low-moderate |
| **Data durability** | Excellent (WAL mode) | Excellent | Configurable (RDB/AOF, risk of loss) |
| **JSON support** | JSON1 extension, JSONB | Native JSONB, excellent | Native JSON type |

**Recommendation for single-server AI assistant:**

- **Primary database: PostgreSQL** -- Handles relational data (users, conversations, settings), vector search (pgvector), and JSON documents in one system. Eliminates the need for separate vector store.
- **Cache layer: Redis** -- Only if you need real-time features (pub/sub for streaming, session caching, rate limiting). Optional for simple setups.
- **Alternative: SQLite + Qdrant** -- Lighter footprint if PostgreSQL feels heavy. SQLite for metadata, Qdrant for vectors.

### 3.2 Vector Store Options

| Store | Memory (1M vectors, 1024d) | Deployment | Strengths | Weaknesses |
|-------|---------------------------|------------|-----------|------------|
| **pgvector** | Shared with PostgreSQL (~5-6GB for 1M) | PostgreSQL extension | No extra service, SQL joins with relational data | Slower than dedicated stores at scale, needs tuning |
| **Qdrant** | ~1.2GB in-memory; supports mmap for disk | Docker container or embedded | Fast, rich filtering, mmap for large datasets | Extra service to manage |
| **ChromaDB** | ~5GB for 1M (HNSW must fit in RAM) | Embedded Python or Docker | Simplest API, great for prototyping | HNSW index MUST fit in RAM -- unusable if it swaps to disk |

**Memory estimation formula:**
- pgvector/ChromaDB HNSW: `vectors * dimensions * 4 bytes * 1.5` (50% overhead for index)
- Qdrant: `vectors * dimensions * 4 bytes * 1.2` (20% overhead, more efficient)

**Recommendation:**
- **< 500K vectors**: pgvector (simplest, no extra services)
- **500K - 5M vectors**: Qdrant with mmap (keeps large datasets on disk, caches hot data)
- **Prototyping only**: ChromaDB (fastest path to working code, but limited scaling)

### 3.3 Resource Requirements Estimation

**Scenario: AI assistant with memory + scheduling + chat on one machine (no local LLM inference)**

| Component | RAM | CPU | Disk |
|-----------|-----|-----|------|
| PostgreSQL + pgvector | 1-2 GB | 1-2 cores | 10-50 GB |
| LiteLLM proxy | 200-500 MB | 0.5 core | Minimal |
| Application server (FastAPI/Node) | 500 MB - 1 GB | 1-2 cores | Minimal |
| Redis (optional, for caching) | 200-500 MB | 0.5 core | Minimal |
| Memory extraction (background LLM calls) | Negligible (API-based) | Burst | N/A |
| **Total (API-only)** | **~4-6 GB** | **4 cores** | **~50 GB** |

**With local model inference (Ollama):**

| Component | Additional RAM | Additional CPU/GPU |
|-----------|---------------|-------------------|
| 7B model (Llama 3, Mistral 7B) | 8 GB | 4+ cores or GPU with 8GB VRAM |
| 13B model | 16 GB | 8+ cores or GPU with 16GB VRAM |
| 70B model (quantized Q4) | 40+ GB | GPU with 48GB+ VRAM |
| Embedding model (e.g., nomic-embed) | 1-2 GB | 1-2 cores |

**Recommended minimum single-server specs:**

| Setup | RAM | CPU | GPU | Disk |
|-------|-----|-----|-----|------|
| API-only (cloud LLMs) | 8 GB | 4 cores | None | 100 GB SSD |
| With 7B local model | 16-32 GB | 8 cores | Optional (8GB VRAM) | 200 GB SSD |
| With 13B+ local model | 32-64 GB | 16 cores | Recommended (16GB+ VRAM) | 500 GB SSD |

### 3.4 Recommended Single-Server Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Single Server                         │
│                                                          │
│  ┌──────────────┐    ┌──────────────┐                   │
│  │  Chat Web UI │    │  API Clients │                   │
│  └──────┬───────┘    └──────┬───────┘                   │
│         │                   │                            │
│         v                   v                            │
│  ┌─────────────────────────────────┐                    │
│  │     Application Server           │                    │
│  │  (FastAPI / Next.js)             │                    │
│  │                                  │                    │
│  │  - Chat routing                  │                    │
│  │  - Memory extraction (Mem0-style)│                    │
│  │  - Scheduling / task management  │                    │
│  └──────────┬──────────────────────┘                    │
│             │                                            │
│     ┌───────┴────────┐                                  │
│     v                v                                   │
│  ┌──────────┐  ┌──────────────┐                         │
│  │ LiteLLM  │  │ PostgreSQL   │                         │
│  │ Proxy    │  │ + pgvector   │                         │
│  └──┬───────┘  │              │                         │
│     │          │ - Users      │                         │
│     ├──> Ollama│ - Conversations│                        │
│     ├──> OpenAI│ - Memory facts│                        │
│     ├──> Claude│ - Vector index│                        │
│     └──> ...   │ - Schedules  │                         │
│                └──────────────┘                          │
│                                                          │
│  ┌──────────────┐  (optional)                           │
│  │    Redis     │  - Session cache                      │
│  │              │  - Rate limiting                       │
│  │              │  - Pub/sub for streaming               │
│  └──────────────┘                                       │
└─────────────────────────────────────────────────────────┘
```

### 3.5 Technology Stack Recommendation

| Layer | Recommended | Alternative | Rationale |
|-------|-------------|-------------|-----------|
| **Primary DB** | PostgreSQL 16+ | SQLite (WAL mode) | Concurrent access, pgvector, JSONB |
| **Vector Store** | pgvector (in PostgreSQL) | Qdrant (if >500K vectors) | Single service, SQL joins with metadata |
| **LLM Gateway** | LiteLLM proxy | Direct API calls | Unified interface, fallbacks, cost tracking |
| **Local Models** | Ollama | vLLM (if GPU available) | Simple setup, model management |
| **Cache** | Redis (optional) | In-memory LRU | Only needed for real-time features |
| **Memory Pattern** | Mem0-style extract/update | MemGPT-style agent self-edit | Simpler, proven at scale |
| **Memory Retrieval** | Vector search + metadata filter | + Graph DB (if relational queries needed) | Graph adds complexity; start without it |
| **App Framework** | FastAPI (Python) | Next.js (TypeScript) | Python has best LLM ecosystem integration |

---

## Sources

### Memory Systems
- [MemGPT: Towards LLMs as Operating Systems (arXiv)](https://arxiv.org/abs/2310.08560)
- [Intro to Letta / MemGPT Docs](https://docs.letta.com/concepts/memgpt/)
- [Agent Memory: How to Build Agents that Learn and Remember (Letta Blog)](https://www.letta.com/blog/agent-memory)
- [Understanding Memory Management (Letta Docs)](https://docs.letta.com/advanced/memory-management/)
- [Long-term Memory (LangChain Docs)](https://docs.langchain.com/oss/python/deepagents/long-term-memory)
- [Launching Long-Term Memory Support in LangGraph](https://blog.langchain.com/launching-long-term-memory-support-in-langgraph/)
- [LangMem Conceptual Guide](https://langchain-ai.github.io/langmem/concepts/conceptual_guide/)
- [LangMem SDK Launch](https://blog.langchain.com/langmem-sdk-launch/)
- [Mem0 GitHub Repository](https://github.com/mem0ai/mem0)
- [Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory (arXiv)](https://arxiv.org/abs/2504.19413)
- [Demystifying the Architecture of Mem0 (Medium)](https://medium.com/@parthshr370/from-chat-history-to-ai-memory-a-better-way-to-build-intelligent-agents-f30116b0c124)
- [Mem0 & Mem0-Graph Breakdown](https://memo.d.foundation/breakdown/mem0)
- [Build Persistent Memory with Mem0 on AWS](https://aws.amazon.com/blogs/database/build-persistent-memory-for-agentic-ai-applications-with-mem0-open-source-amazon-elasticache-for-valkey-and-amazon-neptune-analytics/)

### Multi-Model Switching
- [Open WebUI GitHub](https://github.com/open-webui/open-webui)
- [Open WebUI LLM Provider Integration (DeepWiki)](https://deepwiki.com/open-webui/open-webui/13-llm-provider-integration)
- [LobeChat Architecture (GitHub Wiki)](https://github.com/lobehub/lobe-chat/wiki/Architecture)
- [Using Multiple Model Providers in LobeChat](https://lobehub.com/docs/usage/providers)
- [LiteLLM GitHub Repository](https://github.com/BerriAI/litellm)
- [LiteLLM Documentation](https://docs.litellm.ai/docs/)
- [OpenRouter Provider Routing](https://openrouter.ai/docs/guides/routing/provider-selection)
- [The LLM Abstraction Layer (ProxAI)](https://www.proxai.co/blog/archive/llm-abstraction-layer)

### Storage and Vector Databases
- [Best Vector Databases in 2025 (Firecrawl)](https://www.firecrawl.dev/blog/best-vector-databases)
- [Vector Stores for RAG Comparison](https://www.glukhov.org/post/2025/12/vector-stores-for-rag-comparison/)
- [Qdrant vs pgvector: Same Speed (Medium)](https://medium.com/@TheWake/qdrant-vs-pgvector-theyre-the-same-speed-5ac6b7361d9d)
- [Minimal RAM to Serve a Million Vectors (Qdrant)](https://qdrant.tech/articles/memory-consumption/)
- [Qdrant Capacity Planning](https://qdrant.tech/documentation/guides/capacity-planning/)
- [ChromaDB Resource Requirements (Cookbook)](https://cookbook.chromadb.dev/core/resources/)
- [Single-Node Chroma Performance and Limitations](https://docs.trychroma.com/deployment/performance)
- [pgvector GitHub Repository](https://github.com/pgvector/pgvector)
- [Rearchitecting: Redis to SQLite (Wafris)](https://wafris.org/blog/rearchitecting-for-sqlite)
