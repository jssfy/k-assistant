"""
Scheduler engine: APScheduler with PostgreSQL persistence.

Uses AsyncIOScheduler with SQLAlchemyJobStore for crash-resilient scheduling.
Jobs survive process restarts because they're persisted in the DB.
"""

import uuid
from datetime import datetime, timezone

import structlog
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings

logger = structlog.get_logger()


def _sync_db_url() -> str:
    """Convert async DB URL to sync for APScheduler's jobstore."""
    return settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg://")


class SchedulerEngine:
    def __init__(self):
        self._scheduler: AsyncIOScheduler | None = None

    def start(self):
        """Initialize and start the scheduler."""
        jobstores = {
            "default": SQLAlchemyJobStore(url=_sync_db_url())
        }
        self._scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            job_defaults={
                "coalesce": True,  # Combine missed runs into one
                "max_instances": 1,  # Prevent overlapping executions
                "misfire_grace_time": 3600,  # 1h grace for misfired jobs
            },
        )
        self._scheduler.add_listener(self._on_job_event, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
        self._scheduler.start()
        logger.info("scheduler.started", job_count=len(self._scheduler.get_jobs()))

    def shutdown(self):
        """Gracefully shutdown the scheduler."""
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            logger.info("scheduler.shutdown")

    def add_task(self, task_id: uuid.UUID, cron_expression: str, timezone_str: str = "Asia/Shanghai"):
        """Register a scheduled task as a cron job."""
        if not self._scheduler:
            logger.warning("scheduler.not_started")
            return

        trigger = CronTrigger.from_crontab(cron_expression, timezone=timezone_str)
        # Import here to avoid circular imports
        from app.scheduler.task_runner import run_task

        self._scheduler.add_job(
            run_task,
            trigger=trigger,
            args=[str(task_id)],
            id=str(task_id),
            replace_existing=True,
            name=f"task-{task_id}",
        )
        logger.info("scheduler.task_added", task_id=str(task_id), cron=cron_expression)

    def remove_task(self, task_id: uuid.UUID):
        """Remove a scheduled task."""
        if not self._scheduler:
            return
        job_id = str(task_id)
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)
            logger.info("scheduler.task_removed", task_id=job_id)

    def update_task(self, task_id: uuid.UUID, cron_expression: str, timezone_str: str = "Asia/Shanghai"):
        """Update schedule for an existing task."""
        if not self._scheduler:
            return
        job_id = str(task_id)
        job = self._scheduler.get_job(job_id)
        if job:
            trigger = CronTrigger.from_crontab(cron_expression, timezone=timezone_str)
            self._scheduler.reschedule_job(job_id, trigger=trigger)
            logger.info("scheduler.task_updated", task_id=job_id, cron=cron_expression)
        else:
            # Job not in scheduler (e.g. after restart), re-add it
            self.add_task(task_id, cron_expression, timezone_str)

    def get_next_run_time(self, task_id: uuid.UUID) -> datetime | None:
        """Get the next scheduled run time for a task."""
        if not self._scheduler:
            return None
        job = self._scheduler.get_job(str(task_id))
        return job.next_run_time if job else None

    def _on_job_event(self, event):
        """Log job execution results."""
        if event.exception:
            logger.error("scheduler.job_failed", job_id=event.job_id, error=str(event.exception))
        else:
            logger.info("scheduler.job_executed", job_id=event.job_id)


scheduler_engine = SchedulerEngine()
