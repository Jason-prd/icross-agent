"""Planner node — structured plan generation for LangGraph agent.

Produces a `Plan` object from user messages, enabling step-by-step
execution tracking and human-in-the-loop confirmation.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel


class Step(BaseModel):
    """A single step in an execution plan."""

    step: int = 0
    description: str = ""
    tools: list[str] = []
    risky: bool = False


class Plan(BaseModel):
    """Structured execution plan produced by the planner node."""

    steps: list[Step] = []

    def current(self, step_idx: int) -> Step | None:
        if 0 <= step_idx < len(self.steps):
            return self.steps[step_idx]
        return None

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    @property
    def is_done(self, step_idx: int) -> bool:
        return step_idx >= len(self.steps)

    def next_step_tools(self, step_idx: int) -> list[str]:
        step = self.current(step_idx)
        return step.tools if step else []

    def needs_confirm(self, step_idx: int) -> bool:
        step = self.current(step_idx)
        return step.risky if step else False


# ── Risky tool names that always trigger human_confirm ──
# These are matched against plan step tools. If ANY tool in a step
# matches, the step is marked risky and the graph pauses for confirmation.
RISKY_TOOLS: set[str] = {
    "ozon_fbs_ship_orders",      # Confirm packing & shipping
    "ozon_fbs_awaiting_delivery", # Mark awaiting delivery
    "ozon_fbs_create_act",       # Create acceptance report
    "ozon_update_price",         # Update product price
    "ozon_update_stock",         # Update product stock
    "ozon_product_create",       # Create new product
    "delete_file",               # Delete file from workspace
    "run_command",               # Execute CLI command
    "send_notification",         # Send notification
    "create_product_draft",      # Create product listing draft
    "generate_report",           # Generate report
}


def _extract_json(text: str) -> str | None:
    """Extract first JSON array from LLM output using balanced-brace matching."""
    start = text.find("[")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                candidate = text[start : i + 1]
                try:
                    json.loads(candidate)
                    return candidate
                except json.JSONDecodeError:
                    return None
    return None


PLANNER_PROMPT = """你是一个电商运营助手。分析用户请求，制定执行计划。

请输出 JSON 数组格式的计划，每个步骤包含：
- step: 步骤编号（从0开始）
- description: 步骤的中文描述
- tools: 该步骤需要使用的工具名列表
- risky: 布尔值，该步骤是否涉及危险操作（发货、改价、删除、创建草稿、执行命令等）

判断 risky=true 的标准（满足任一即可）：
- 调用涉及资金变更的操作（更新价格、发货）
- 调用涉及删除数据的操作
- 调用涉及创建正式数据的操作
- 调用涉及执行系统命令的操作

例1 — "查订单然后同步商品"：
[{{"step": 0, "description": "查看订单列表", "tools": ["ozon_order_list"], "risky": false}},
 {{"step": 1, "description": "同步商品信息", "tools": ["ozon_product_list", "ozon_product_info"], "risky": false}}]

例2 — "发货订单123"：
[{{"step": 0, "description": "确认打包发货", "tools": ["ozon_fbs_ship_orders"], "risky": true}}]

如果用户只是简单聊天、问候、或不需要任何工具即可回复，请输出空数组 []。
只返回 JSON 数组，不要其他文字。"""


def build_plan_from_tools(tool_names: list[str], description: str) -> Plan:
    """Create a single-step plan for direct tool execution (fallback)."""
    risky = any(t in RISKY_TOOLS for t in tool_names)
    return Plan(steps=[
        Step(step=0, description=description, tools=tool_names, risky=risky),
    ])


async def planner_node(state: dict[str, Any]) -> dict[str, Any]:
    """Analyze user messages and produce a structured Plan.

    Reads the last user message from state, calls LLM to create a plan,
    writes the Plan into state['plan'] and resets current_step to 0.
    """
    messages = state.get("messages", [])
    plan: Plan | None = state.get("plan")

    # If a plan already exists and we're mid-execution, skip re-planning
    if plan and not plan.is_done(state.get("current_step", 0)):
        return {}

    # Find the last human message
    last_user_msg = ""
    for msg in reversed(messages):
        if hasattr(msg, "type") and msg.type == "human":
            last_user_msg = msg.content
            break
        if isinstance(msg, dict) and msg.get("type") == "human":
            last_user_msg = msg.get("content", "")
            break

    if not last_user_msg:
        # No user message yet — don't plan
        return {}

    # For simple/quick messages that likely don't need tools,
    # skip LLM call and let the agent decide at runtime
    simple_patterns = [
        r"^(你好|嗨|hi|hello|早上好|下午好|晚上好|谢谢|感谢|再见|bye)\s*$",
        r"^[?？]$",
        r"^\s*$",
    ]
    for pat in simple_patterns:
        if re.match(pat, last_user_msg.strip(), re.IGNORECASE):
            return {
                "plan": Plan(),
                "current_step": 0,
                "active_tools": [],
            }

    try:
        from icross.api.ai_utils import get_ai_llm

        llm = get_ai_llm("agent.planner")

        # Include available tool names for reference
        from icross.agents.tools import registry
        all_tools = registry.get_tool_names()
        tool_list = "\n".join(f"  - {t} ({registry.get_toolset_for_tool(t) or 'default'})" for t in all_tools[:60])

        prompt = f"{PLANNER_PROMPT}\n\n可用工具:\n{tool_list}\n\n用户消息: {last_user_msg}"

        response = await llm.ainvoke([{"role": "user", "content": prompt}])
        raw = response.content
        if isinstance(raw, list):
            texts = [b.get("text", "") if isinstance(b, dict) else str(b) for b in raw]
            raw = "\n".join(texts)

        raw = raw.strip()
        # Strip markdown fences
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        json_str = _extract_json(raw)
        if json_str:
            steps_data = json.loads(json_str)
            steps = [Step(**s) for s in steps_data]
            new_plan = Plan(steps=steps)
        else:
            new_plan = Plan()

        # Determine active_tools for the first step
        active_tools = new_plan.next_step_tools(0)

        return {
            "plan": new_plan,
            "current_step": 0,
            "active_tools": active_tools,
        }
    except Exception:
        # Fallback: empty plan, let agent handle with full tool list
        return {
            "plan": Plan(),
            "current_step": 0,
            "active_tools": [],
        }
