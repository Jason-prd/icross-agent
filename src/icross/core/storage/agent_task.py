"""Persistent storage for agent task state and events.

AgentTaskStorage — tracks per-session agent execution lifecycle in agent_tasks.json.
SessionEventStore — captures structured events (tokens, tool_calls, workflow steps)
                   per session for frontend replay on reconnect.
"""

from datetime import datetime
from typing import Any

from icross.core.storage.ozon_data import JsonStore


class AgentTaskStorage:
    """JSON file storage for agent task lifecycle state.

    One record per session (session_id is the primary key).
    """

    def __init__(self):
        self._storage = JsonStore("agent_tasks.json")

    async def create_task(self, session_id: str) -> dict[str, Any]:
        return self._storage._upsert("session_id", session_id, {
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "completed_at": None,
            "error": None,
            "final_output": None,
            "current_tool": None,
            "current_step": 0,
        })

    async def update_task(self, session_id: str, **kwargs) -> dict[str, Any] | None:
        return self._storage._upsert("session_id", session_id, kwargs)

    async def get_task(self, session_id: str) -> dict[str, Any] | None:
        return self._storage._find("session_id", session_id)

    async def list_tasks(self, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        items = self._storage._get_all()
        if status:
            items = [t for t in items if t.get("status") == status]
        items.sort(key=lambda t: t.get("started_at", ""), reverse=True)
        return items[:limit]

    async def mark_completed(self, session_id: str, final_output: str | None = None) -> dict[str, Any] | None:
        return self._storage._upsert("session_id", session_id, {
            "status": "completed",
            "completed_at": datetime.now().isoformat(),
            "final_output": final_output,
        })

    async def mark_failed(self, session_id: str, error: str) -> dict[str, Any] | None:
        return self._storage._upsert("session_id", session_id, {
            "status": "failed",
            "completed_at": datetime.now().isoformat(),
            "error": error,
        })

    async def mark_interrupted(self, session_id: str) -> dict[str, Any] | None:
        return self._storage._upsert("session_id", session_id, {
            "status": "interrupted",
            "completed_at": datetime.now().isoformat(),
            "error": "Server restart interrupted execution",
        })

    async def recover_running_tasks(self) -> list[dict[str, Any]]:
        """Mark all 'running' tasks as 'interrupted'. Returns interrupted tasks."""
        interrupted: list[dict[str, Any]] = []
        for item in self._storage._get_all():
            if item.get("status") == "running":
                await self.mark_interrupted(item["session_id"])
                interrupted.append(item)
        return interrupted


class SessionEventStore:
    """JSON file storage for per-session agent events.

    Events are appended as they happen, allowing the frontend to
    replay them after reconnect (even if the agent has finished).
    """

    def __init__(self):
        self._storage = JsonStore("session_events.json")

    async def append_event(self, session_id: str, event: dict[str, Any]) -> None:
        """Append a single event to the session's event list."""
        event["timestamp"] = event.get("timestamp", datetime.now().isoformat())
        # Find existing record
        record = self._storage._find("session_id", session_id)
        if record:
            record.setdefault("events", []).append(event)
            self._storage._upsert("session_id", session_id, {"events": record["events"]})
        else:
            self._storage._upsert("session_id", session_id, {"events": [event]})

    async def append_events(self, session_id: str, events: list[dict[str, Any]]) -> None:
        for ev in events:
            await self.append_event(session_id, ev)

    async def get_events(self, session_id: str, since_index: int = 0) -> list[dict[str, Any]]:
        record = self._storage._find("session_id", session_id)
        if not record:
            return []
        return record.get("events", [])[since_index:]

    async def clear_events(self, session_id: str) -> None:
        self._storage._upsert("session_id", session_id, {"events": []})

    async def count_events(self, session_id: str) -> int:
        record = self._storage._find("session_id", session_id)
        return len(record.get("events", [])) if record else 0
