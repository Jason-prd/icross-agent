"""Agent tools for workflow and scheduler management (Phase 9)."""

from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.tools import tool

from icross.agents.tools import registry


def _run_async(coro):
    """Run async code synchronously in tool context."""
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()
    except RuntimeError:
        pass
    return asyncio.run(coro)


@tool
def remove_scheduled_job(job_id: str) -> dict:
    """删除一个定时任务。

    Args:
        job_id: 任务 ID（通过 list_scheduled_jobs 获取）。

    Returns:
        操作结果。
    """
    from icross.services.scheduler import scheduler_service

    success = _run_async(scheduler_service.remove_job(job_id))
    return {"success": success, "job_id": job_id}


@tool
def list_workflows(shop_id: str = "", limit: int = 20, offset: int = 0) -> dict:
    """获取工作流列表。

    Args:
        shop_id: 店铺 ID（可选，不传则返回所有店铺）。
        limit: 每页数量，默认 20，最大 200。
        offset: 偏移量。

    Returns:
        工作流列表和总数。
    """
    from icross.core.storage.ozon_data import WorkflowStorage

    store = WorkflowStorage()
    workflows = _run_async(store.list_workflows(
        shop_id=shop_id or None, limit=min(limit, 200), offset=offset,
    ))
    total = _run_async(store.count_workflows(shop_id=shop_id or None))
    return {
        "workflows": [
            {
                "id": w.get("id"),
                "name": w.get("name"),
                "status": w.get("status"),
                "pipeline_type": w.get("pipeline_type"),
                "current_step": w.get("current_step", 0),
                "total_steps": len(w.get("steps", [])),
                "created_at": w.get("created_at"),
            }
            for w in workflows
        ],
        "total": total,
    }


@tool
def start_workflow(workflow_id: str) -> dict:
    """启动一个工作流。

    工作流必须处于 pending 状态才能启动。

    Args:
        workflow_id: 工作流 ID。

    Returns:
        启动后的工作流信息。
    """
    from icross.services.workflow import start_workflow as _start_wf

    result = _run_async(_start_wf(workflow_id))
    if result is None:
        return {"success": False, "error": "工作流不存在"}
    return {
        "success": True,
        "workflow_id": workflow_id,
        "status": result.get("status"),
        "current_step": result.get("current_step", 0),
        "total_steps": len(result.get("steps", [])),
    }


@tool
def get_workflow_status(workflow_id: str) -> dict:
    """查询工作流状态和进度。

    Args:
        workflow_id: 工作流 ID。

    Returns:
        工作流详细信息，包括各步骤状态。
    """
    from icross.core.storage.ozon_data import WorkflowStorage

    store = WorkflowStorage()
    wf = _run_async(store.get_workflow(workflow_id))
    if not wf:
        return {"success": False, "error": "工作流不存在"}

    steps = wf.get("steps", [])
    return {
        "success": True,
        "workflow_id": workflow_id,
        "name": wf.get("name"),
        "status": wf.get("status"),
        "current_step": wf.get("current_step", 0),
        "total_steps": len(steps),
        "steps": [
            {
                "step_type": s.get("step_type"),
                "name": s.get("name", ""),
                "status": s.get("status", "pending"),
                "error": s.get("error"),
                "started_at": s.get("started_at"),
                "completed_at": s.get("completed_at"),
            }
            for s in steps
        ],
        "created_at": wf.get("created_at"),
    }


@tool
def run_auto_pipeline(
    shop_id: str,
    product_name_cn: str,
    product_description_cn: str = "",
    category: str = "",
    purchase_price_cny: float = 0,
    weight_kg: float = 0,
    target_margin: float = 20.0,
) -> dict:
    """执行完整自动化选品上架流水线。

    按顺序执行：搜索产品 → 类目匹配 → 生成 Listing → 生成图片 → 计算定价 → 创建草稿。

    Args:
        shop_id: 店铺 ID。
        product_name_cn: 中文产品名称。
        product_description_cn: 中文产品描述（可选）。
        category: Ozon 类目名称（可选）。
        purchase_price_cny: 采购成本（人民币）。
        weight_kg: 商品重量（公斤）。
        target_margin: 目标利润率（%），默认 20。

    Returns:
        工作流信息，包含 ID 和当前状态。
    """
    from icross.services.workflow import run_full_pipeline

    result = _run_async(run_full_pipeline(
        shop_id=shop_id,
        product_name_cn=product_name_cn,
        product_description_cn=product_description_cn,
        category=category,
        purchase_price_cny=purchase_price_cny,
        weight_kg=weight_kg,
        target_margin=target_margin,
    ))
    return {
        "success": True,
        "workflow_id": result.get("id"),
        "name": result.get("name"),
        "status": result.get("status"),
        "total_steps": len(result.get("steps", [])),
    }


@tool
def list_compound_tasks() -> dict:
    """列出所有可用的复合任务模板。

    复合任务是预定义的多步骤跨域任务，例如"退货处理→补货→通知运营"。

    Returns:
        可用的复合任务列表。
    """
    from icross.services.compound_task import compound_task_registry

    tasks = compound_task_registry.list_tasks()
    return {"tasks": tasks, "total": len(tasks)}


@tool
def run_compound_task(task_type: str, params: dict[str, str] = {}) -> dict:
    """执行一个复合任务。

    复合任务是预定义的多步骤跨域任务，自动按顺序执行各步骤并传递中间结果。
    可用任务类型通过 list_compound_tasks 获取。

    Args:
        task_type: 任务类型标识（例如 "return_restock_notify", "daily_operations_review"）。
        params: 任务参数，如 {"shop_id": "shop-1", "notify_target": "feishu:chat_xxx"}。

    Returns:
        任务执行结果，包含执行 ID 和各步骤结果。
    """
    from icross.services.compound_task import compound_task_engine

    execution = _run_async(compound_task_engine.execute(task_type, params=params))
    return {
        "success": execution.status in ("completed", "partial"),
        "execution_id": execution.id,
        "task_type": task_type,
        "status": execution.status,
        "error": execution.error,
        "step_results": {
            name: (r.get("error") if isinstance(r, dict) and "error" in r else "ok")
            for name, r in execution.step_results.items()
        },
    }


@tool
def get_compound_task_status(execution_id: str) -> dict:
    """查询复合任务的执行状态和结果。

    Args:
        execution_id: 执行 ID（由 run_compound_task 返回）。

    Returns:
        执行状态和各步骤结果。
    """
    from icross.services.compound_task import compound_task_registry

    execution = compound_task_registry.get_execution(execution_id)
    if not execution:
        return {"success": False, "error": "执行记录不存在"}

    return {
        "success": execution.status in ("completed", "partial"),
        "execution_id": execution.id,
        "task_type": execution.task_type,
        "status": execution.status,
        "current_step": execution.current_step,
        "error": execution.error,
        "created_at": execution.created_at,
        "completed_at": execution.completed_at,
        "step_results": {
            name: (r.get("error") if isinstance(r, dict) and "error" in r else "ok")
            for name, r in execution.step_results.items()
        },
    }


# ── Auto-registration ──
registry.register(remove_scheduled_job, toolset="ozon")
registry.register(list_workflows, toolset="ozon")
registry.register(start_workflow, toolset="ozon")
registry.register(get_workflow_status, toolset="ozon")
registry.register(run_auto_pipeline, toolset="ozon")
registry.register(list_compound_tasks, toolset="ozon")
registry.register(run_compound_task, toolset="ozon")
registry.register(get_compound_task_status, toolset="ozon")
