"""Task Plan Storage — JSON file persistence for agent task plans.

Data stored in ``data/task_plans.json``.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
_PLANS_PATH = _DATA_DIR / "task_plans.json"


def _load_plans() -> list[dict]:
    if not _PLANS_PATH.exists():
        return []
    try:
        with open(_PLANS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_plans(plans: list[dict]) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(_PLANS_PATH, "w", encoding="utf-8") as f:
        json.dump(plans, f, ensure_ascii=False, indent=2)


def create_plan(name: str, steps: list[dict], shop_id: str = "") -> dict:
    """Create a new task plan and return it."""
    plan = {
        "id": str(uuid.uuid4())[:8],
        "name": name,
        "shop_id": shop_id,
        "status": "pending",
        "current_step": 0,
        "steps": [
            {
                "step_type": s.get("step_type", "custom"),
                "description": s.get("description", ""),
                "params": s.get("params", {}),
                "status": "pending",
                "result": None,
            }
            for s in steps
        ],
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }
    plans = _load_plans()
    plans.append(plan)
    _save_plans(plans)
    return plan


def get_plan(plan_id: str) -> dict | None:
    """Get a single plan by ID."""
    for plan in _load_plans():
        if plan.get("id") == plan_id:
            return plan
    return None


def list_plans(shop_id: str = "") -> list[dict]:
    """List plans, optionally filtered by shop_id."""
    plans = _load_plans()
    if shop_id:
        return [p for p in plans if p.get("shop_id") == shop_id]
    return plans


def update_plan(plan_id: str, updates: dict) -> dict | None:
    """Update a plan's fields."""
    plans = _load_plans()
    for plan in plans:
        if plan.get("id") == plan_id:
            for k, v in updates.items():
                if k != "id":
                    plan[k] = v
            plan["updated_at"] = datetime.now().isoformat()
            _save_plans(plans)
            return plan
    return None


def update_step(plan_id: str, step_index: int, updates: dict) -> dict | None:
    """Update a specific step in a plan."""
    plans = _load_plans()
    for plan in plans:
        if plan.get("id") == plan_id:
            steps = plan.get("steps", [])
            if 0 <= step_index < len(steps):
                steps[step_index].update(updates)
                plan["updated_at"] = datetime.now().isoformat()
                _save_plans(plans)
                return plan
    return None
