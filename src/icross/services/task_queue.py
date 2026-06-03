"""Lightweight task queue using thread pool + APScheduler.

Replaces Celery+Redis for environments without Redis.
Tasks are stored in JSON files and executed by a thread pool executor
to avoid blocking the asyncio event loop.
"""

import asyncio
import logging
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Callable, Coroutine

from icross.core.storage.ozon_data import TaskStorage

_logger = logging.getLogger(__name__)

# Thread pool for running blocking task handlers
_executor = ThreadPoolExecutor(max_workers=4)

# Registered task handlers
_task_handlers: dict[str, Callable[..., Coroutine[Any, Any, dict[str, Any]]]] = {}


def register_task(task_type: str):
    """Decorator to register a task handler."""
    def decorator(func: Callable[..., Coroutine[Any, Any, dict[str, Any]]]):
        _task_handlers[task_type] = func
        return func
    return decorator


async def execute_task(task_id: str) -> dict[str, Any]:
    """Execute a single task by ID in a thread pool to avoid blocking the event loop."""
    store = TaskStorage()
    task = await store.get_task(task_id)
    if not task:
        raise ValueError(f"Task {task_id} not found")
    if task["status"] not in ("pending", "failed"):
        return task

    handler = _task_handlers.get(task["task_type"])
    if not handler:
        await store.update_task(task_id, status="failed", error=f"No handler for {task['task_type']}")
        return await store.get_task(task_id)

    await store.update_task(task_id, status="running", started_at=datetime.now().isoformat())

    loop = asyncio.get_running_loop()

    def _run_handler():
        """Run the handler in a dedicated event loop in the thread pool."""
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        try:
            return new_loop.run_until_complete(handler(**task.get("params", {})))
        finally:
            new_loop.close()

    try:
        result = await loop.run_in_executor(_executor, _run_handler)
        await store.update_task(
            task_id,
            status="completed",
            result=result,
            progress=100,
            completed_at=datetime.now().isoformat(),
        )
    except Exception as e:
        _logger.exception(f"Task {task_id} failed: {e}")
        await store.update_task(task_id, status="failed", error=f"{e}\n{traceback.format_exc()}")

    return await store.get_task(task_id)


def create_task_sync(
    task_type: str,
    params: dict[str, Any] | None = None,
    priority: int = 0,
) -> dict[str, Any]:
    """Synchronously create a task (for use in non-async contexts)."""
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        store = TaskStorage()
        task = loop.run_until_complete(store.create_task(
            task_type=task_type,
            params=params or {},
            priority=priority,
        ))
        return task
    finally:
        loop.close()


async def create_and_run_task(
    task_type: str,
    params: dict[str, Any] | None = None,
    priority: int = 0,
) -> dict[str, Any]:
    """Create a task and execute it immediately in a thread pool."""
    store = TaskStorage()
    task = await store.create_task(
        task_type=task_type,
        params=params or {},
        priority=priority,
    )
    # Fire and forget in thread pool
    asyncio.ensure_future(execute_task(task["id"]))
    return task
