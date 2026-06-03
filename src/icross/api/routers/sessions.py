"""REST API endpoints for session management."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from icross.core.storage.ozon_data import SessionStorage
from icross.services.agent_task_manager import agent_task_manager

router = APIRouter()
session_storage = SessionStorage()


class SessionTitleUpdate(BaseModel):
    title: str


@router.get("/sessions")
async def list_sessions():
    """List all sessions."""
    return {"sessions": await session_storage.list_sessions()}


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str):
    """Get all messages for a session."""
    return {"session_id": session_id, "messages": await session_storage.get_messages(session_id)}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session and all its messages."""
    await session_storage.delete_session(session_id)
    return {"success": True, "session_id": session_id}


@router.get("/sessions/search")
async def search_messages(keyword: str = ""):
    """Search messages containing the keyword."""
    if not keyword:
        return {"results": []}
    return {"keyword": keyword, "results": await session_storage.search_messages(keyword)}


@router.patch("/sessions/{session_id}/title")
async def update_session_title(session_id: str, body: SessionTitleUpdate):
    """Update session title."""
    await session_storage.update_session_title(session_id, body.title)
    return {"success": True, "session_id": session_id, "title": body.title}


# ── Agent status & events ──

@router.get("/sessions/{session_id}/agent-status")
async def get_agent_status(session_id: str):
    """Get persistent agent execution status for a session."""
    status = await agent_task_manager.get_status(session_id)
    return status


@router.get("/sessions/{session_id}/agent-events")
async def get_agent_events(session_id: str, since: int = 0):
    """Get persisted agent events for frontend replay.

    Args:
        since: Event index to start from (0 = all events)
    """
    events = await agent_task_manager.event_store.get_events(session_id, since_index=since)
    total = await agent_task_manager.event_store.count_events(session_id)
    return {"session_id": session_id, "events": events, "total": total, "since": since}


@router.post("/sessions/{session_id}/retry")
async def retry_agent(session_id: str):
    """Mark an interrupted/failed agent task as retryable.

    Returns False if there is already a running task.
    """
    status = await agent_task_manager.get_status(session_id)
    if status.get("has_active_task"):
        return {"success": False, "reason": "Task already running"}
    if status.get("status") in ("interrupted", "failed", "completed"):
        await agent_task_manager.task_store.update_task(
            session_id, status="pending", error=None, completed_at=None, final_output=None,
        )
        return {"success": True}
    return {"success": False, "reason": f"Task status is '{status.get('status')}', cannot retry"}