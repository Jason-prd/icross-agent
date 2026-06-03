"""Scheduled job management REST API.

Endpoints for managing cron-based scheduled jobs.
Supports listing, creating, removing, and toggling jobs.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from icross.services.scheduler import scheduler_service

_logger = logging.getLogger(__name__)
router = APIRouter(prefix="/scheduler", tags=["scheduler"])


@router.get("/status")
async def get_scheduler_status():
    """Get the scheduler's current running status."""
    return scheduler_service.get_status()


@router.get("/jobs")
async def list_scheduled_jobs():
    """List all scheduled jobs."""
    jobs = await scheduler_service.list_jobs()
    return {"jobs": jobs, "total": len(jobs)}


@router.post("/jobs")
async def create_scheduled_job(body: dict[str, Any]):
    """Create a new scheduled job.

    Required fields:
        name: Human-readable name.
        job_type: Type identifier (e.g. "daily_sales_report", "notification").
        cron_expr: Cron expression (e.g. "0 9 * * *" for daily at 9am).

    Optional fields:
        params: Dict of parameters passed to the handler.
        timezone: Timezone string (default "Asia/Shanghai").
        enabled: Whether the job starts active (default True).
    """
    if not body.get("name"):
        raise HTTPException(status_code=400, detail="Field 'name' is required")
    if not body.get("job_type"):
        raise HTTPException(status_code=400, detail="Field 'job_type' is required")
    if not body.get("cron_expr"):
        raise HTTPException(status_code=400, detail="Field 'cron_expr' is required")

    # Validate cron expression
    parts = body["cron_expr"].strip().split()
    if len(parts) != 5:
        raise HTTPException(
            status_code=400,
            detail="Invalid cron expression; must have exactly 5 fields (min hour day month day_of_week)",
        )

    job_id = await scheduler_service.add_job(body)
    job = await scheduler_service.get_job(job_id)
    return {"success": True, "job": job}


@router.delete("/jobs/{job_id}")
async def delete_scheduled_job(job_id: str):
    """Delete a scheduled job."""
    removed = await scheduler_service.remove_job(job_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return {"success": True, "job_id": job_id}


@router.put("/jobs/{job_id}/toggle")
async def toggle_scheduled_job(job_id: str, body: dict[str, Any]):
    """Enable or disable a scheduled job."""
    enabled = body.get("enabled", True)
    updated = await scheduler_service.toggle_job(job_id, enabled=enabled)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    job = await scheduler_service.get_job(job_id)
    return {"success": True, "enabled": enabled, "job": job}


@router.get("/jobs/{job_id}")
async def get_scheduled_job(job_id: str):
    """Get a single scheduled job by ID."""
    job = await scheduler_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return {"job": job}


@router.get("/logs")
async def get_scheduler_logs(job_id: str | None = None, limit: int = 20):
    """Get scheduler execution logs."""
    logs = scheduler_service.get_logs(job_id=job_id, limit=limit)
    return {"logs": logs}


@router.get("/logs/{job_id}")
async def get_job_logs(job_id: str, limit: int = 20):
    """Get execution logs for a specific job."""
    logs = scheduler_service.get_logs(job_id=job_id, limit=limit)
    return {"logs": logs.get(job_id, [])}
