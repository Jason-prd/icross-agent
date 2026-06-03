"""REST API endpoints for sourcing session persistence (Phase 1 UX Redesign)."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from icross.core.storage.ozon_data import SourcingSessionStorage

router = APIRouter(prefix="/sourcing", tags=["sourcing"])
session_store = SourcingSessionStorage()


class Materials(BaseModel):
    text: str = ""
    url: str = ""


class UpdateSessionRequest(BaseModel):
    shop_id: str
    status: str | None = None
    materials: Materials | None = None
    parse_result: dict | None = None
    listing_result: dict | None = None
    category_result: dict | None = None
    draft_id: str | None = None


@router.post("/sessions")
async def create_session(shop_id: str):
    """Create a new sourcing session."""
    session = await session_store.create_session(shop_id)
    return {"success": True, "session": session}


@router.get("/sessions")
async def list_sessions(shop_id: str, status: str | None = None):
    """List sourcing sessions for a shop, optionally filtered by status."""
    sessions = await session_store.list_sessions(shop_id, status)
    return {"sessions": sessions, "total": len(sessions)}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get a specific sourcing session."""
    session = await session_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.put("/sessions/{session_id}")
async def update_session(session_id: str, req: UpdateSessionRequest):
    """Update sourcing session progress."""
    existing = await session_store.get_session(session_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Session not found")

    updates = {}
    if req.status is not None:
        updates["status"] = req.status
    if req.materials is not None:
        updates["materials"] = req.materials.model_dump()
    if req.parse_result is not None:
        updates["parse_result"] = req.parse_result
    if req.listing_result is not None:
        updates["listing_result"] = req.listing_result
    if req.category_result is not None:
        updates["category_result"] = req.category_result
    if req.draft_id is not None:
        updates["draft_id"] = req.draft_id

    updated = await session_store.update_session(session_id, **updates)
    return {"success": True, "session": updated}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a sourcing session."""
    if await session_store.delete_session(session_id):
        return {"success": True}
    raise HTTPException(status_code=404, detail="Session not found")
