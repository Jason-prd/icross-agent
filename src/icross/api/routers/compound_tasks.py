"""Compound task REST API — list/execute/status for reusable multi-step tasks."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from icross.services.compound_task import compound_task_registry, compound_task_engine

router = APIRouter(prefix="/compound-tasks", tags=["compound-tasks"])


class ExecuteTaskRequest(BaseModel):
    task_type: str
    params: dict = {}


@router.get("/")
async def list_compound_tasks():
    """List all registered compound task templates."""
    return {"tasks": compound_task_registry.list_tasks()}


@router.post("/execute")
async def execute_compound_task(body: ExecuteTaskRequest):
    """Execute a compound task."""
    task_def = compound_task_registry.get(body.task_type)
    if not task_def:
        raise HTTPException(status_code=404, detail=f"Task type '{body.task_type}' not found")

    execution = await compound_task_engine.execute(body.task_type, params=body.params)
    return {
        "success": execution.status in ("completed", "partial"),
        "execution_id": execution.id,
        "task_type": body.task_type,
        "status": execution.status,
        "error": execution.error,
    }


@router.get("/executions")
async def list_executions(limit: int = 20):
    """List recent compound task executions."""
    return {"executions": compound_task_registry.list_executions(limit=limit)}


@router.get("/executions/{execution_id}")
async def get_execution(execution_id: str):
    """Get compound task execution details."""
    execution = compound_task_registry.get_execution(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    return {
        "id": execution.id,
        "task_type": execution.task_type,
        "status": execution.status,
        "current_step": execution.current_step,
        "error": execution.error,
        "step_results": execution.step_results,
        "shared_state": {k: v for k, v in execution.shared_state.items() if not k.startswith("_")},
        "created_at": execution.created_at,
        "completed_at": execution.completed_at,
    }
