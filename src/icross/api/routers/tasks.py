"""Task Queue API endpoints (Phase 4)."""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from icross.core.storage.ozon_data import TaskStorage
from icross.services.task_queue import execute_task, create_and_run_task

router = APIRouter(prefix="/tasks", tags=["tasks"])
_logger = logging.getLogger(__name__)


class CreateTaskRequest(BaseModel):
    task_type: str = Field(..., min_length=1)
    params: dict = Field(default_factory=dict)
    priority: int = 0
    run_now: bool = True


@router.get("")
async def list_tasks(
    task_type: str = "",
    status: str = "",
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
):
    """List tasks with optional filtering."""
    store = TaskStorage()
    result = await store.list_tasks(
        task_type=task_type or None,
        status=status or None,
        limit=limit,
        offset=offset,
    )
    return result


@router.post("")
async def create_task(req: CreateTaskRequest):
    """Create a new task (and optionally run it immediately)."""
    if req.run_now:
        task = await create_and_run_task(
            task_type=req.task_type,
            params=req.params,
            priority=req.priority,
        )
    else:
        store = TaskStorage()
        task = await store.create_task(
            task_type=req.task_type,
            params=req.params,
            priority=req.priority,
        )
    return {"success": True, "task": task}


@router.get("/{task_id}")
async def get_task(task_id: str):
    """Get task details and status."""
    store = TaskStorage()
    task = await store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/{task_id}/retry")
async def retry_task(task_id: str):
    """Retry a failed task."""
    store = TaskStorage()
    task = await store.retry_failed(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    asyncio.ensure_future(execute_task(task_id))
    return {"success": True, "task": task}


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str):
    """Cancel a pending or running task."""
    store = TaskStorage()
    task = await store.cancel_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True, "task": task}


@router.delete("/{task_id}")
async def delete_task(task_id: str):
    """Delete a task."""
    store = TaskStorage()
    if await store.delete_task(task_id):
        return {"success": True}
    raise HTTPException(status_code=404, detail="Task not found")


@router.get("/stats/summary")
async def task_stats():
    """Get task queue summary statistics."""
    store = TaskStorage()
    tasks = (await store.list_tasks(limit=1000))["items"]
    return {
        "total": len(tasks),
        "pending": sum(1 for t in tasks if t["status"] == "pending"),
        "running": sum(1 for t in tasks if t["status"] == "running"),
        "completed": sum(1 for t in tasks if t["status"] == "completed"),
        "failed": sum(1 for t in tasks if t["status"] == "failed"),
        "cancelled": sum(1 for t in tasks if t["status"] == "cancelled"),
    }
