"""Automation Workflow Pipeline API endpoints (Phase 4)."""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from icross.core.storage.ozon_data import WorkflowStorage, TaskStorage
from icross.services.workflow import (
    execute_workflow_step,
    complete_workflow_step,
    start_workflow,
    run_full_pipeline,
    get_default_pipeline,
)
from icross.services.task_queue import execute_task

router = APIRouter(prefix="/workflows", tags=["workflows"])
_logger = logging.getLogger(__name__)


class CreateWorkflowRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    shop_id: str = Field(..., min_length=1)
    steps: list[dict] | None = None
    product_data: dict = Field(default_factory=dict)


class RunPipelineRequest(BaseModel):
    shop_id: str = Field(..., min_length=1)
    product_name_cn: str = Field(..., min_length=1)
    product_description_cn: str = ""
    category: str = ""
    purchase_price_cny: float = 0
    weight_kg: float = 0
    target_margin: float = 20.0


@router.get("")
async def list_workflows(
    shop_id: str = "",
    status: str = "",
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
):
    """List workflows."""
    store = WorkflowStorage()
    result = await store.list_workflows(
        shop_id=shop_id or None,
        status=status or None,
        limit=limit,
        offset=offset,
    )
    return result


@router.post("")
async def create_workflow(req: CreateWorkflowRequest):
    """Create a new workflow pipeline."""
    store = WorkflowStorage()
    steps = req.steps or get_default_pipeline(req.shop_id, req.product_data.get("product_name_cn", ""))
    wf = await store.create_workflow(
        name=req.name,
        shop_id=req.shop_id,
        steps=steps,
        product_data=req.product_data,
    )
    return {"success": True, "workflow": wf}


@router.post("/run-pipeline")
async def create_and_run_pipeline(req: RunPipelineRequest):
    """Create and start a full automation pipeline. One-click entry point."""
    wf = await run_full_pipeline(
        shop_id=req.shop_id,
        product_name_cn=req.product_name_cn,
        product_description_cn=req.product_description_cn,
        category=req.category,
        purchase_price_cny=req.purchase_price_cny,
        weight_kg=req.weight_kg,
        target_margin=req.target_margin,
    )
    return {"success": True, "workflow": wf}


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: str):
    """Get workflow details."""
    store = WorkflowStorage()
    wf = await store.get_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf


@router.post("/{workflow_id}/start")
async def trigger_workflow(workflow_id: str):
    """Start/resume a workflow."""
    wf = await start_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {"success": True, "workflow": wf}


@router.post("/{workflow_id}/advance")
async def advance_workflow(workflow_id: str):
    """Advance to the next step (call after current step task completes)."""
    wf = await execute_workflow_step(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {"success": True, "workflow": wf}


@router.post("/{workflow_id}/step/{step_index}/complete")
async def complete_step(workflow_id: str, step_index: int):
    """Mark a step as completed and propagate its result."""
    store = WorkflowStorage()
    wf = await store.get_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    steps = wf.get("steps", [])
    if step_index < 0 or step_index >= len(steps):
        raise HTTPException(status_code=400, detail="Invalid step index")

    step = steps[step_index]
    # Check if step has a task and get its result
    task_id = step.get("task_id")
    if task_id:
        task_store = TaskStorage()
        task = await task_store.get_task(task_id)
        if task and task["status"] == "completed":
            await complete_workflow_step(workflow_id, task.get("result", {}))
            wf = await store.get_workflow(workflow_id)
            return {"success": True, "workflow": wf, "task": task}
        elif task and task["status"] == "failed":
            return {"success": False, "workflow": wf, "task": task, "error": "Task failed"}
        else:
            return {"success": False, "workflow": wf, "task": task, "error": "Task not yet completed"}

    # No task, just advance
    await complete_workflow_step(workflow_id, {})
    wf = await store.get_workflow(workflow_id)
    return {"success": True, "workflow": wf}


@router.delete("/{workflow_id}")
async def delete_workflow(workflow_id: str):
    """Delete a workflow."""
    store = WorkflowStorage()
    if await store.delete_workflow(workflow_id):
        return {"success": True}
    raise HTTPException(status_code=404, detail="Workflow not found")
