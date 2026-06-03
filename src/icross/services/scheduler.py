"""Cron-based task scheduling service.

Wraps APScheduler ``AsyncIOScheduler`` with persistent job storage
in ``data/scheduled_jobs.json``. Supports file locking to prevent
overlapping executions across processes.

Usage:
    from icross.services.scheduler import scheduler_service

    await scheduler_service.start()
    job_id = await scheduler_service.add_job({
        "name": "每日销售报告",
        "job_type": "daily_sales_report",
        "cron_expr": "0 9 * * *",
        "params": {"chat_id": "oc_xxx"},
    })
    await scheduler_service.stop()
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

_logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
_JOBS_PATH = _DATA_DIR / "scheduled_jobs.json"
_LOCK_PATH = _DATA_DIR / "scheduler.lock"
_LOGS_PATH = _DATA_DIR / "scheduler_logs.json"

# Maximum execution logs kept per job
_MAX_LOG_ENTRIES = 50

# Job type → handler mapping
_JOB_HANDLERS: dict[str, str] = {}


def register_job_handler(job_type: str, handler_path: str) -> None:
    """Register a handler for a job type.

    Args:
        job_type: Job type identifier (e.g. "daily_sales_report").
        handler_path: Fully qualified async function path
                     (e.g. "icross.services.report_service.generate_and_send_report").
    """
    _JOB_HANDLERS[job_type] = handler_path
    _logger.debug("Registered job handler: %s -> %s", job_type, handler_path)


async def _resolve_handler(job_type: str) -> Any:
    """Dynamically import and return the handler function for a job type."""
    handler_path = _JOB_HANDLERS.get(job_type)
    if not handler_path:
        raise ValueError(f"No handler registered for job type: {job_type}")

    mod_path, _, fn_name = handler_path.rpartition(".")
    import importlib
    module = importlib.import_module(mod_path)
    return getattr(module, fn_name)


class SchedulerService:
    """Cron-based task scheduler with persistent job storage.

    Attributes:
        running: Whether the scheduler is currently running.
    """

    def __init__(self) -> None:
        self._scheduler: AsyncIOScheduler | None = None
        self.running = False
        self._lock_handle: int | None = None
        self._running_jobs: set[str] = set()  # overlap prevention

    # ---------------------------------------------------------------
    # Lifecycle
    # ---------------------------------------------------------------

    async def start(self) -> None:
        """Start the scheduler and restore persisted jobs."""
        if self.running:
            _logger.warning("Scheduler already running")
            return

        # Acquire file lock
        self._acquire_lock()

        self._scheduler = AsyncIOScheduler()
        self._scheduler.start()
        self.running = True
        _logger.info("Scheduler started")

        # Restore persisted jobs
        jobs = self._load_jobs()
        restored = 0
        for job in jobs:
            if job.get("enabled", True):
                try:
                    self._schedule_job(job)
                    restored += 1
                except Exception as e:
                    _logger.warning("Failed to restore job %s: %s", job.get("id"), e)

        _logger.info("Restored %d/%d scheduled jobs", restored, len(jobs))

    async def stop(self) -> None:
        """Stop the scheduler."""
        if self._scheduler and self.running:
            self._scheduler.shutdown(wait=False)
            self.running = False
            self._release_lock()
            _logger.info("Scheduler stopped")

    def _acquire_lock(self) -> None:
        """Acquire a PID-based file lock with stale-lock detection."""
        try:
            _DATA_DIR.mkdir(parents=True, exist_ok=True)

            # Stale lock detection: if lock file exists, check if PID is alive
            if _LOCK_PATH.exists():
                try:
                    old_pid = int(_LOCK_PATH.read_text().strip())
                    if self._is_pid_alive(old_pid):
                        _logger.warning("Scheduler lock held by alive PID %d — another instance may be running", old_pid)
                    else:
                        _logger.info("Removed stale scheduler lock from PID %d", old_pid)
                except (ValueError, OSError):
                    pass

            with open(_LOCK_PATH, "w") as f:
                f.write(str(os.getpid()))
            self._lock_handle = os.getpid()
            _logger.debug("Scheduler lock acquired (PID: %d)", os.getpid())
        except OSError as e:
            _logger.warning("Failed to create scheduler lock: %s", e)

    @staticmethod
    def _is_pid_alive(pid: int) -> bool:
        """Check if a PID is currently alive (cross-platform)."""
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False

    def _release_lock(self) -> None:
        """Release the file lock."""
        try:
            if _LOCK_PATH.exists():
                _LOCK_PATH.unlink()
            self._lock_handle = None
            _logger.debug("Scheduler lock released")
        except OSError as e:
            _logger.warning("Failed to release scheduler lock: %s", e)

    # ---------------------------------------------------------------
    # Job management
    # ---------------------------------------------------------------

    async def add_job(self, job_def: dict) -> str:
        """Add a new scheduled job.

        Args:
            job_def: Job definition dict with keys:
                - name: Human-readable name.
                - job_type: Type identifier (must have a registered handler).
                - cron_expr: Cron expression (e.g. "0 9 * * *").
                - params: Dict of parameters passed to the handler.
                - timezone: Timezone string (default "Asia/Shanghai").
                - enabled: Whether the job is active (default True).

        Returns:
            The new job ID.
        """
        job_id = str(uuid.uuid4())[:8]

        entry: dict[str, Any] = {
            "id": job_id,
            "name": job_def.get("name", ""),
            "job_type": job_def["job_type"],
            "cron_expr": job_def.get("cron_expr", "0 9 * * *"),
            "params": job_def.get("params", {}),
            "timezone": job_def.get("timezone", "Asia/Shanghai"),
            "enabled": job_def.get("enabled", True),
            "last_run": None,
            "next_run": None,
            "created_at": datetime.now().isoformat(),
        }

        jobs = self._load_jobs()
        jobs.append(entry)
        self._save_jobs(jobs)

        if entry["enabled"] and self.running:
            self._schedule_job(entry)

        _logger.info("Scheduled job added: %s (%s)", entry["name"], job_id)
        return job_id

    async def remove_job(self, job_id: str) -> bool:
        """Remove a scheduled job by ID.

        Returns True if the job was found and removed.
        """
        jobs = self._load_jobs()
        new_jobs = [j for j in jobs if j.get("id") != job_id]

        if len(new_jobs) == len(jobs):
            return False

        self._save_jobs(new_jobs)

        # Remove from APScheduler if running
        if self._scheduler and self.running:
            aps_id = f"job_{job_id}"
            try:
                self._scheduler.remove_job(aps_id)
            except Exception:
                pass

        _logger.info("Scheduled job removed: %s", job_id)
        return True

    async def toggle_job(self, job_id: str, enabled: bool) -> bool:
        """Enable or disable a job.

        Returns True if the job was found and updated.
        """
        jobs = self._load_jobs()
        for job in jobs:
            if job.get("id") == job_id:
                job["enabled"] = enabled
                self._save_jobs(jobs)

                aps_id = f"job_{job_id}"
                if self._scheduler and self.running:
                    try:
                        self._scheduler.remove_job(aps_id)
                    except Exception:
                        pass
                    if enabled:
                        self._schedule_job(job)

                _logger.info("Job %s %s", job_id, "enabled" if enabled else "disabled")
                return True
        return False

    async def list_jobs(self) -> list[dict]:
        """List all scheduled jobs with next run time."""
        jobs = self._load_jobs()
        if self._scheduler and self.running:
            for job in jobs:
                aps_id = f"job_{job.get('id')}"
                try:
                    aps_job = self._scheduler.get_job(aps_id)
                    if aps_job and aps_job.next_run_time:
                        job["next_run"] = aps_job.next_run_time.isoformat()
                except Exception:
                    pass
        return jobs

    async def get_job(self, job_id: str) -> dict | None:
        """Get a single job by ID."""
        for job in await self.list_jobs():
            if job.get("id") == job_id:
                return job
        return None

    def get_status(self) -> dict:
        """Get scheduler status."""
        jobs = self._load_jobs()
        return {
            "running": self.running,
            "total_jobs": len(jobs),
            "enabled_jobs": sum(1 for j in jobs if j.get("enabled", True)),
            "lock_held": self._lock_handle is not None,
            "active_executions": list(self._running_jobs),
        }

    # ---------------------------------------------------------------
    # Execution logs
    # ---------------------------------------------------------------

    def _update_job_meta(self, job_id: str, updates: dict) -> None:
        """Update metadata fields on a persisted job entry."""
        jobs = self._load_jobs()
        for job in jobs:
            if job.get("id") == job_id:
                job.update(updates)
                break
        self._save_jobs(jobs)

    def _append_log(self, job_id: str, entry: dict) -> None:
        """Append an execution log entry, trimming to max count."""
        logs = self._load_logs()
        logs.setdefault(job_id, []).append(entry)
        if len(logs[job_id]) > _MAX_LOG_ENTRIES:
            logs[job_id] = logs[job_id][-_MAX_LOG_ENTRIES:]
        self._save_logs(logs)

    def get_logs(self, job_id: str | None = None, limit: int = 20) -> dict:
        """Get execution logs, optionally filtered by job_id."""
        logs = self._load_logs()
        if job_id:
            return {job_id: (logs.get(job_id, [])[-limit:])}
        return {jid: entries[-limit:] for jid, entries in logs.items()}

    def _load_logs(self) -> dict:
        """Load execution logs from JSON file."""
        if not _LOGS_PATH.exists():
            return {}
        try:
            with open(_LOGS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_logs(self, logs: dict) -> None:
        """Save execution logs to JSON file."""
        try:
            _DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(_LOGS_PATH, "w", encoding="utf-8") as f:
                json.dump(logs, f, ensure_ascii=False, indent=2)
        except OSError as e:
            _logger.error("Failed to save scheduler logs: %s", e)

    # ---------------------------------------------------------------
    # Internal
    # ---------------------------------------------------------------

    def _schedule_job(self, entry: dict) -> None:
        """Add a job to the APScheduler."""
        if not self._scheduler:
            return

        job_id = entry["id"]
        cron_expr = entry.get("cron_expr", "0 9 * * *")
        timezone = entry.get("timezone", "Asia/Shanghai")

        # Parse cron expression: "min hour day month day_of_week"
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            _logger.warning("Invalid cron expression for job %s: %s", job_id, cron_expr)
            return

        trigger = CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4],
            timezone=timezone,
        )

        self._scheduler.add_job(
            self._execute_job,
            trigger=trigger,
            args=[entry],
            id=f"job_{job_id}",
            name=entry.get("name", job_id),
            replace_existing=True,
        )

    async def _execute_job(self, entry: dict) -> None:
        """Execute a scheduled job with overlap prevention."""
        job_id = entry["id"]
        job_type = entry.get("job_type", "")
        params = entry.get("params", {})

        # Overlap prevention: skip if already running
        if job_id in self._running_jobs:
            _logger.warning("Job %s (%s) is still running from previous trigger — skipping", entry.get("name"), job_id)
            self._append_log(job_id, {
                "status": "skipped",
                "reason": "Previous execution still running",
                "timestamp": datetime.now().isoformat(),
            })
            return

        self._running_jobs.add(job_id)
        start_time = time.monotonic()
        _logger.info("Executing scheduled job: %s (%s)", entry.get("name"), job_id)

        try:
            handler = await _resolve_handler(job_type)
            result = await handler(**params)

            duration = time.monotonic() - start_time
            self._update_job_meta(job_id, {
                "last_run": datetime.now().isoformat(),
                "last_duration": round(duration, 2),
                "last_success": True,
                "last_error": None,
            })
            self._append_log(job_id, {
                "status": "completed",
                "duration": round(duration, 2),
                "timestamp": datetime.now().isoformat(),
            })

            _logger.info("Job %s completed in %.2fs: %s", job_id, duration, result)
        except Exception as e:
            duration = time.monotonic() - start_time
            self._update_job_meta(job_id, {
                "last_run": datetime.now().isoformat(),
                "last_duration": round(duration, 2),
                "last_success": False,
                "last_error": str(e),
            })
            self._append_log(job_id, {
                "status": "failed",
                "duration": round(duration, 2),
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            })
            _logger.exception("Job %s failed after %.2fs: %s", job_id, duration, e)
        finally:
            self._running_jobs.discard(job_id)

    def _load_jobs(self) -> list[dict]:
        """Load scheduled jobs from JSON file."""
        if not _JOBS_PATH.exists():
            return []
        try:
            with open(_JOBS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            _logger.warning("Failed to load scheduled jobs")
            return []

    def _save_jobs(self, jobs: list[dict]) -> None:
        """Save scheduled jobs to JSON file."""
        try:
            _DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(_JOBS_PATH, "w", encoding="utf-8") as f:
                json.dump(jobs, f, ensure_ascii=False, indent=2)
        except OSError as e:
            _logger.error("Failed to save scheduled jobs: %s", e)


# Module-level singleton
scheduler_service = SchedulerService()
