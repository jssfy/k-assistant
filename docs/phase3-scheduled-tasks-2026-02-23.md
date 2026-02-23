# Phase 3: Scheduled Tasks - Implementation Report

> Date: 2026-02-23

## Core Conclusions

1. **Phase 3 fully implemented**: APScheduler + PostgreSQL persistence + task CRUD API + task runner + NL parser
2. **All non-LLM endpoints pass self-test**: Create/Read/Update/Delete tasks, activation/deactivation, execution logging, cron validation, restart persistence
3. **NL parsing and task execution depend on LLM availability**: minimaxi proxy had connection issues during testing, but error handling works correctly (failures are recorded in execution logs)
4. **Scheduler syncs on restart**: APScheduler's SQLAlchemy jobstore + our DB sync ensures tasks survive process restarts

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Phase 3: Scheduled Tasks                   │
│                                                               │
│  ┌──────────────┐    ┌───────────────┐    ┌──────────────┐  │
│  │ API Router   │───>│ NL Parser     │───>│ LLM          │  │
│  │ /api/tasks/* │    │ (function     │    │ (via LiteLLM)│  │
│  │              │    │  calling)     │    └──────────────┘  │
│  └──────┬───────┘    └───────────────┘                      │
│         │                                                    │
│         ▼                                                    │
│  ┌──────────────┐    ┌───────────────┐                      │
│  │ Scheduler    │───>│ Task Runner   │                      │
│  │ Engine       │    │               │                      │
│  │ (APScheduler)│    │ 1. Load config│                      │
│  │              │    │ 2. Get memory │                      │
│  │ + SQLAlchemy │    │ 3. Call LLM   │                      │
│  │   JobStore   │    │ 4. Tool loop  │                      │
│  └──────────────┘    │ 5. Log result │                      │
│         │            └───────┬───────┘                      │
│         ▼                    ▼                               │
│  ┌─────────────────────────────────────────────┐            │
│  │           PostgreSQL                          │            │
│  │  scheduled_tasks | task_executions            │            │
│  │  apscheduler_jobs (jobstore)                  │            │
│  └─────────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────────┘
```

## New Files

| File | Purpose |
|------|---------|
| `app/models/scheduled_task.py` | ScheduledTask ORM model |
| `app/models/task_execution.py` | TaskExecution ORM model |
| `app/schemas/task.py` | Pydantic schemas (TaskCreate, TaskUpdate, TaskOut, TaskExecutionOut) |
| `app/scheduler/__init__.py` | Scheduler package |
| `app/scheduler/engine.py` | APScheduler wrapper with PostgreSQL jobstore |
| `app/scheduler/nl_parser.py` | NL-to-cron LLM function calling parser |
| `app/scheduler/task_runner.py` | Task execution (LLM + tools + logging) |
| `app/api/tasks.py` | Tasks CRUD API router |

## Modified Files

| File | Change |
|------|--------|
| `app/config.py` | Added `SCHEDULER_ENABLED` setting |
| `app/main.py` | Scheduler lifecycle (start/shutdown/sync), tasks router |
| `app/models/__init__.py` | Export ScheduledTask, TaskExecution |
| `alembic/env.py` | Import new models for autogenerate |
| `pyproject.toml` | Added `apscheduler>=3.10.0,<4.0.0` |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/tasks` | Create task (NL or explicit cron) |
| GET | `/api/tasks` | List all tasks |
| GET | `/api/tasks/{id}` | Get task details |
| PUT | `/api/tasks/{id}` | Update task |
| DELETE | `/api/tasks/{id}` | Delete task |
| POST | `/api/tasks/{id}/run` | Manual trigger |
| GET | `/api/tasks/{id}/executions` | Execution history |

## Self-Test Results

| Test | Result |
|------|--------|
| List tasks (empty) | OK — `[]` |
| Create with explicit cron | OK — task created, next_run_at correct (UTC conversion) |
| Create with NL description | FAIL — upstream LLM proxy connection error (infrastructure) |
| List tasks | OK — returns created tasks |
| Get task by ID | OK — full task details |
| Update name + cron | OK — scheduler rescheduled, next_run_at updated |
| Deactivate task | OK — is_active=false, next_run_at=null, removed from scheduler |
| Reactivate task | OK — re-added to scheduler |
| Manual trigger | OK — execution recorded (status=failed due to LLM connection) |
| List executions | OK — execution history with error details |
| Get non-existent task | OK — 404 |
| Invalid cron expression | OK — 422 with "Wrong number of fields" |
| Delete task | OK — 204, removed from scheduler |
| Persistence on restart | OK — scheduler.started job_count=1, scheduler.synced_tasks count=1 |

## Key Design Decisions

1. **APScheduler 3.x (not 4.x)**: v4 is alpha, v3 is battle-tested with AsyncIOScheduler
2. **Cron in local timezone**: The cron expression is in the user's timezone, APScheduler handles UTC conversion
3. **SQLAlchemy jobstore**: APScheduler jobs persist independently in `apscheduler_jobs` table, our `scheduled_tasks` table stores the task config/metadata
4. **Dual sync on restart**: APScheduler restores jobs from its jobstore, we also iterate our DB to ensure consistency
5. **Task runner uses standalone session**: Since APScheduler triggers outside HTTP context, task_runner creates its own DB session
6. **Graceful LLM failures**: Task execution records `status=failed` + error message, doesn't crash the scheduler

## Dependencies Added

- `apscheduler>=3.10.0,<4.0.0` (+ transitive: `tzlocal`)
