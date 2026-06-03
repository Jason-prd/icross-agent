"""Agent task lifecycle management with persistence.

Wraps the agent execution in a persistent task record so that:
- Running tasks survive WebSocket disconnects (already does)
- Interrupted tasks are detectable after server restart
- Frontend can poll for status via REST API
- Agent runs in ThreadPoolExecutor via @register_task, surviving session switches
"""

import asyncio
import json
import logging
import queue as _tqueue
import threading
from typing import Any

from icross.core.storage.agent_task import AgentTaskStorage, SessionEventStore
from icross.services.task_queue import register_task, create_and_run_task

_logger = logging.getLogger(__name__)

# ── Thread-safe event queues for real-time WS streaming ──
# The agent (in thread pool) writes events here; the WS forwarder (in main loop) reads them.
_raw_queues: dict[str, _tqueue.Queue] = {}
_raw_queue_lock = threading.Lock()

# ── Thread-safe cancellation events ──
_cancel_events: dict[str, threading.Event] = {}
_cancel_lock = threading.Lock()


def _get_raw_queue(session_id: str) -> _tqueue.Queue:
    with _raw_queue_lock:
        if session_id not in _raw_queues:
            _raw_queues[session_id] = _tqueue.Queue()
        return _raw_queues[session_id]


def _cleanup_raw_queue(session_id: str) -> None:
    with _raw_queue_lock:
        _raw_queues.pop(session_id, None)


def _get_cancel_event(session_id: str) -> threading.Event:
    with _cancel_lock:
        if session_id not in _cancel_events:
            _cancel_events[session_id] = threading.Event()
        return _cancel_events[session_id]


def _cleanup_cancel(session_id: str) -> None:
    with _cancel_lock:
        _cancel_events.pop(session_id, None)


class AgentTaskManager:
    """Manages agent task lifecycle with persistent state tracking."""

    def __init__(self):
        self.task_store = AgentTaskStorage()
        self.event_store = SessionEventStore()
        # In-memory tracking of running asyncio tasks (same as chat.py's _session_tasks)
        self._running_tasks: dict[str, asyncio.Task] = {}

    async def start_agent(self, session_id: str, coro) -> asyncio.Task:
        """Create persistent task record and launch agent coroutine."""
        await self.task_store.create_task(session_id)
        task = asyncio.create_task(coro, name=f"agent-{session_id}")
        self._running_tasks[session_id] = task
        task.add_done_callback(lambda _: self._running_tasks.pop(session_id, None))
        return task

    async def update_progress(
        self, session_id: str,
        current_tool: str | None = None,
        current_step: int | None = None,
    ) -> None:
        updates: dict[str, Any] = {}
        if current_tool is not None:
            updates["current_tool"] = current_tool
        if current_step is not None:
            updates["current_step"] = current_step
        if updates:
            await self.task_store.update_task(session_id, **updates)

    async def complete_task(self, session_id: str, final_output: str | None = None) -> None:
        await self.task_store.mark_completed(session_id, final_output)

    async def fail_task(self, session_id: str, error: str) -> None:
        await self.task_store.mark_failed(session_id, error)

    async def recover_from_restart(self) -> list[dict[str, Any]]:
        """Mark all running tasks as interrupted. Returns interrupted tasks."""
        return await self.task_store.recover_running_tasks()

    def is_running(self, session_id: str) -> bool:
        return session_id in self._running_tasks or session_id in _cancel_events

    def cancel_task(self, session_id: str) -> bool:
        # Try asyncio task (legacy mode)
        task = self._running_tasks.get(session_id)
        if task and not task.done():
            task.cancel()
            return True
        # Try thread-pool task (new mode)
        cancel_ev = _cancel_events.get(session_id)
        if cancel_ev:
            cancel_ev.set()
            return True
        return False

    async def start_agent_task(self, session_id: str, user_message: str, full_message: str, config: dict) -> dict[str, Any]:
        """Launch agent in ThreadPoolExecutor via @register_task.

        Returns the TaskStorage record immediately; agent runs asynchronously.
        """
        # Create persistent task record
        await self.task_store.create_task(session_id)
        # Create cancel event + raw queue for this session
        _get_cancel_event(session_id)
        _get_raw_queue(session_id)
        # Launch in thread pool
        task_record = await create_and_run_task(
            "agent_exec",
            params={
                "session_id": session_id,
                "user_message": user_message,
                "full_message": full_message,
                "config": config,
            },
        )
        return task_record

    async def get_status(self, session_id: str) -> dict[str, Any]:
        """Get task status with in-memory refresh for running tasks."""
        task_record = await self.task_store.get_task(session_id)
        if not task_record:
            return {"session_id": session_id, "status": "idle", "has_active_task": False}

        is_running = self.is_running(session_id)
        status = task_record.get("status", "unknown")

        # If in-memory says running but storage says otherwise, trust memory
        if is_running and status != "running":
            await self.task_store.update_task(session_id, status="running")
            status = "running"

        return {
            "session_id": session_id,
            "status": status,
            "has_active_task": is_running,
            "started_at": task_record.get("started_at"),
            "completed_at": task_record.get("completed_at"),
            "error": task_record.get("error"),
            "current_tool": task_record.get("current_tool"),
            "current_step": task_record.get("current_step"),
            "final_output": task_record.get("final_output"),
        }

    async def persist_event(self, session_id: str, event: dict[str, Any]) -> None:
        """Persist a single agent event for frontend replay."""
        try:
            await self.event_store.append_event(session_id, event)
        except Exception as e:
            _logger.debug(f"Failed to persist event: {e}")


# Global singleton
agent_task_manager = AgentTaskManager()


# ── Agent Exec Task Handler (runs in ThreadPoolExecutor) ──

@register_task("agent_exec")
async def agent_exec_handler(
    session_id: str,
    user_message: str,
    full_message: str,
    config: dict,
    **kwargs,
) -> dict[str, Any]:
    """Run agent in thread pool, persisting events and streaming via raw queue.

    This is triggered by create_and_run_task("agent_exec", params=...).
    It runs in a dedicated event loop inside a ThreadPoolExecutor thread,
    so it cannot use asyncio.Queue for WS streaming. Instead, it writes
    events to a thread-safe queue.Queue that the WS forwarder reads.
    """
    from icross.api.routers.chat import _run_agent

    cancel_ev = _get_cancel_event(session_id)
    raw_queue = _get_raw_queue(session_id)

    # Thread-safe emit: push JSON string to queue.Queue (works across threads)
    async def thread_emit(payload: str):
        raw_queue.put(payload)

    try:
        await _run_agent(
            session_id, user_message, full_message, config,
            _emit_fn=thread_emit,
            _cancel_event=cancel_ev,
        )
    except Exception as e:
        _logger.exception(f"agent_exec_handler failed for {session_id}: {e}")
        raw_queue.put(json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False))
    finally:
        # Signal WS forwarder that this agent execution is done.
        # The raw queue stays alive for subsequent agent executions in the same session.
        raw_queue.put(None)
        _cleanup_cancel(session_id)

    return {"session_id": session_id, "status": "completed", "error": None}
