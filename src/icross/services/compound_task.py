"""Compound task system — reusable multi-step cross-domain task orchestration.

Each ``CompoundTask`` defines a sequence of steps that chain tools across
domains, with shared state flowing between steps.

Built on top of the existing workflow engine and scheduler service.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

_logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
_TASKS_PATH = _DATA_DIR / "compound_tasks.json"


# ── Data Model ────────────────────────────────────────────────────


@dataclass
class CompoundTaskStep:
    """A single step within a compound task."""

    name: str  # Unique step name within the task
    description: str  # Human-readable description
    tool: str  # Tool name to invoke
    params_template: dict[str, Any]  # Template for tool params, supports {state.key}
    retry_on_failure: bool = False
    timeout_seconds: int = 120
    depends_on: list[str] = field(default_factory=list)  # Steps that must complete first


@dataclass
class CompoundTaskDef:
    """Definition of a reusable compound task template."""

    task_type: str  # Unique identifier (e.g. "return_restock_notify")
    name: str  # Human-readable name
    description: str
    steps: list[CompoundTaskStep]
    default_params: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompoundTaskExecution:
    """Runtime state of a compound task execution."""

    id: str
    task_type: str
    status: str  # pending | running | completed | failed | partial
    shared_state: dict[str, Any]
    step_results: dict[str, Any]
    current_step: int = 0
    error: str | None = None
    created_at: str = ""
    completed_at: str | None = None


# ── Registry ──────────────────────────────────────────────────────


class CompoundTaskRegistry:
    """Registry of reusable compound task templates."""

    def __init__(self):
        self._tasks: dict[str, CompoundTaskDef] = {}
        self._executions: dict[str, CompoundTaskExecution] = {}
        self._build_defaults()

    def _build_defaults(self) -> None:
        """Register built-in compound tasks."""
        self.register(CompoundTaskDef(
            task_type="return_restock_notify",
            name="退货处理 → 补货 → 通知运营",
            description="处理退货列表，根据退货原因决定补货数量，最后通知运营结果",
            steps=[
                CompoundTaskStep(
                    name="list_returns",
                    description="查看待处理退货列表",
                    tool="ozon_returns_list",
                    params_template={"status": "awaiting_approval"},
                ),
                CompoundTaskStep(
                    name="restock",
                    description="根据退货商品计算补货数量",
                    tool="calculate_product_price",
                    params_template={"shop_id": "{state.shop_id}"},
                    depends_on=["list_returns"],
                ),
                CompoundTaskStep(
                    name="notify_ops",
                    description="发送运营通知",
                    tool="send_notification",
                    params_template={
                        "target": "{state.notify_target}",
                        "message": "退货处理完成，共处理 {state.return_count} 件退货",
                    },
                    depends_on=["list_returns", "restock"],
                ),
            ],
            default_params={"shop_id": "", "notify_target": ""},
        ))

        self.register(CompoundTaskDef(
            task_type="daily_operations_review",
            name="每日运营检查",
            description="检查订单、库存、销售数据，汇总报告",
            steps=[
                CompoundTaskStep(
                    name="check_orders",
                    description="检查待处理订单",
                    tool="ozon_order_list",
                    params_template={"status": "awaiting_packaging"},
                ),
                CompoundTaskStep(
                    name="check_stock",
                    description="检查库存预警",
                    tool="ozon_analytics_stocks",
                    params_template={"shop_id": "{state.shop_id}"},
                ),
                CompoundTaskStep(
                    name="send_report",
                    description="发送运营日报",
                    tool="send_notification",
                    params_template={
                        "target": "{state.notify_target}",
                        "message": "每日运营检查完成",
                    },
                    depends_on=["check_orders", "check_stock"],
                ),
            ],
            default_params={"shop_id": "", "notify_target": ""},
        ))

    def register(self, task_def: CompoundTaskDef) -> None:
        """Register a compound task definition."""
        self._tasks[task_def.task_type] = task_def
        _logger.debug("Registered compound task: %s (%s)", task_def.task_type, task_def.name)

    def get(self, task_type: str) -> CompoundTaskDef | None:
        """Get a task definition by type."""
        return self._tasks.get(task_type)

    def list_tasks(self) -> list[dict]:
        """List all registered task templates."""
        return [
            {"task_type": t.task_type, "name": t.name, "description": t.description,
             "step_count": len(t.steps)}
            for t in self._tasks.values()
        ]

    def get_execution(self, exec_id: str) -> CompoundTaskExecution | None:
        """Get an execution by ID."""
        return self._executions.get(exec_id)

    def list_executions(self, limit: int = 20) -> list[dict]:
        """List recent executions."""
        sorted_ex = sorted(
            self._executions.values(),
            key=lambda x: x.created_at,
            reverse=True,
        )
        return [
            {"id": e.id, "task_type": e.task_type, "status": e.status,
             "current_step": e.current_step, "error": e.error,
             "created_at": e.created_at, "completed_at": e.completed_at}
            for e in sorted_ex[:limit]
        ]


# Global singleton
compound_task_registry = CompoundTaskRegistry()


# ── Execution Engine ────────────────────────────────────────────────


def _render_template(template: str, state: dict[str, Any]) -> str:
    """Render a template string with state values.

    Supports ``{state.key}`` and ``{state.key.subkey}`` patterns.
    Falls back to the literal template if resolution fails.
    """
    import re

    def _replace(match: re.Match) -> str:
        path = match.group(1).strip()
        parts = path.split(".")
        if parts[0] == "state":
            parts = parts[1:]
        val = state
        for p in parts:
            if isinstance(val, dict):
                val = val.get(p, match.group(0))
            else:
                return match.group(0)
        return str(val) if not isinstance(val, (dict, list)) else json.dumps(val, ensure_ascii=False)

    return re.sub(r"\{(\S+?)\}", _replace, template)


def _render_params(template: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """Render all string values in a params dict with state."""
    result = {}
    for k, v in template.items():
        if isinstance(v, str):
            result[k] = _render_template(v, state)
        elif isinstance(v, dict):
            result[k] = _render_params(v, state)
        else:
            result[k] = v
    return result


class CompoundTaskEngine:
    """Orchestrates execution of compound tasks with step chaining."""

    async def execute(
        self,
        task_type: str,
        *,
        params: dict[str, Any] | None = None,
        exec_id: str | None = None,
    ) -> CompoundTaskExecution:
        """Execute a compound task from definition, chaining steps sequentially."""
        task_def = compound_task_registry.get(task_type)
        if task_def is None:
            raise ValueError(f"Unknown compound task: {task_type}")

        execution = CompoundTaskExecution(
            id=exec_id or uuid.uuid4().hex[:12],
            task_type=task_type,
            status="running",
            shared_state=dict(task_def.default_params),
            step_results={},
            current_step=0,
            created_at=datetime.now().isoformat(),
        )
        if params:
            execution.shared_state.update(params)

        compound_task_registry._executions[execution.id] = execution
        _logger.info("Starting compound task: %s (exec=%s)", task_type, execution.id)

        steps = task_def.steps
        completed_steps: set[str] = set()

        try:
            for step_idx, step in enumerate(steps):
                execution.current_step = step_idx
                _logger.info("  Step %d/%d: %s (%s)", step_idx + 1, len(steps), step.name, step.tool)

                # Check dependencies
                if step.depends_on:
                    missing = [d for d in step.depends_on if d not in completed_steps]
                    if missing:
                        raise RuntimeError(
                            f"Step '{step.name}' dependencies not met: {missing}"
                        )

                # Render params from shared state
                rendered_params = _render_params(step.params_template, execution.shared_state)

                # Execute the tool
                try:
                    result = await self._execute_tool(step.tool, rendered_params)
                    execution.step_results[step.name] = result
                    completed_steps.add(step.name)

                    # Merge result into shared state (flat merge of top-level keys)
                    if isinstance(result, dict):
                        for k, v in result.items():
                            if not k.startswith("_"):
                                execution.shared_state[k] = v

                except Exception as e:
                    _logger.error("Step %s failed: %s", step.name, e)
                    execution.step_results[step.name] = {"error": str(e)}
                    if step.retry_on_failure:
                        # Simple retry once
                        try:
                            _logger.info("Retrying step %s...", step.name)
                            result = await self._execute_tool(step.tool, rendered_params)
                            execution.step_results[step.name] = result
                            completed_steps.add(step.name)
                            if isinstance(result, dict):
                                for k, v in result.items():
                                    if not k.startswith("_"):
                                        execution.shared_state[k] = v
                        except Exception as retry_err:
                            _logger.error("Retry of step %s also failed: %s", step.name, retry_err)
                            execution.step_results[step.name] = {"error": str(retry_err)}
                            execution.status = "partial"
                            execution.error = f"Step '{step.name}' failed after retry: {retry_err}"
                            execution.completed_at = datetime.now().isoformat()
                            return execution
                    else:
                        execution.status = "partial"
                        execution.error = f"Step '{step.name}' failed: {e}"
                        execution.completed_at = datetime.now().isoformat()
                        return execution

            execution.status = "completed"
            execution.completed_at = datetime.now().isoformat()
            _logger.info("Compound task completed: %s (exec=%s)", task_type, execution.id)

        except Exception as e:
            _logger.exception("Compound task %s failed: %s", execution.id, e)
            execution.status = "failed"
            execution.error = str(e)
            execution.completed_at = datetime.now().isoformat()

        return execution

    async def _execute_tool(self, tool_name: str, params: dict[str, Any]) -> Any:
        """Execute a single tool by name via the registry."""
        from icross.agents.tools import registry as tool_registry

        tool_fn = tool_registry.get_tool(tool_name)
        if tool_fn is None:
            raise ValueError(f"Tool not found: {tool_name}")

        # Tools are sync, run in executor
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: tool_fn.invoke(params))


# Global singleton
compound_task_engine = CompoundTaskEngine()
