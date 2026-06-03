"""Custom LangGraph StateGraph for agent execution with planning, routing, and human-in-the-loop.

Replaces the prebuilt ``create_react_agent`` with a custom graph that adds:
- **planner**: structured Plan generation from user messages
- **human_confirm**: ``interrupt()``-based pause for dangerous operations
- **router**: per-step tool subset selection
- **output**: final response formatting
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage, RemoveMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.types import Command, interrupt
from typing_extensions import Annotated, Sequence, TypedDict

from icross.agents.context import ContextEngine, get_context_engine_for_provider
from icross.agents.tools import registry, discover_builtin_tools

# Load .env
_env_file = Path(__file__).parent.parent.parent.parent.parent / ".env"
if _env_file.exists():
    load_dotenv(_env_file)

# Auto-discover all tool modules
discover_builtin_tools()
ALL_TOOLS = registry.get_tools()


# ── State Schema ───────────────────────────────────────────────────

class AgentState(TypedDict):
    """Extended agent state with planning and routing support."""

    messages: Annotated[Sequence[BaseMessage], add_messages]
    plan: dict | None  # serialized Plan dict
    current_step: int  # index into plan.steps
    active_tools: list[str]  # tool names for current step
    pending_confirm: str | None  # tool name awaiting human approval


# ── System Prompt ─────────────────────────────────────────────────

SYSTEM_PROMPT = """你是一个电商运营助手，帮助管理 Ozon (俄罗斯电商平台) 店铺。

当收到任务请求时，如果需要使用工具，请直接调用合适的工具完成任务。
对于涉及发货、改价、删除等危险操作，系统会自动暂停请求你的确认。

注意：对于简单的问候或无需工具的回复，直接回复即可，不要调用工具。"""


# ── Node Functions ─────────────────────────────────────────────────

async def pre_model_hook_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Context compression before each LLM call (runs before planner and agent)."""
    from icross.agents.context import get_context_engine_for_provider

    # Build context engine on demand from config
    engine: ContextEngine | None = config.get("configurable", {}).get("context_engine")
    if engine is None:
        return {}

    messages = state.get("messages", [])
    if not await engine.should_compress(messages):
        return {}

    updates = await engine.compress(messages)
    if updates:
        return {"messages": updates}
    return {}


async def planner_node(state: AgentState) -> dict[str, Any]:
    """Analyze user messages and produce a structured plan.

    Only runs when no plan exists or the current plan is finished.
    Writes plan + current_step + active_tools into state.
    """
    from .planner import Plan, planner_node as planner_impl

    plan: dict | None = state.get("plan")
    current_step = state.get("current_step", 0)

    # If a plan already exists and we're mid-execution, skip
    if plan and current_step < len(plan.get("steps", [])):
        return {}

    result = await planner_impl(state)
    if result.get("plan"):
        result["plan"] = result["plan"].model_dump() if hasattr(result["plan"], "model_dump") else result["plan"]
    return result


def router_node(state: AgentState) -> dict[str, Any]:
    """Select tools for the current plan step.

    Sets active_tools to the plan step's tool list (or empty for all tools).
    """
    plan: dict | None = state.get("plan")
    current_step = state.get("current_step", 0)

    if plan:
        steps = plan.get("steps", [])
        if 0 <= current_step < len(steps):
            step = steps[current_step]
            tools = step.get("tools", [])
            # Only use tools that actually exist in registry
            valid_tools = [t for t in tools if registry.get_tool(t) is not None]
            if valid_tools:
                return {"active_tools": valid_tools}

    # Fallback: empty active_tools means use all tools
    return {"active_tools": []}


def confirm_node(state: AgentState) -> dict[str, Any]:
    """Pause graph execution for human approval of risky operations.

    Uses LangGraph's ``interrupt()`` to pause. The frontend sends
    approve/reject via WebSocket, which resumes with ``Command(resume=...)``.
    """
    plan: dict | None = state.get("plan")
    current_step = state.get("current_step", 0)
    pending = state.get("pending_confirm")

    if pending:
        # Already confirmed via resume — proceed
        return {"pending_confirm": None}

    # Determine what needs confirmation
    tool_name = ""
    description = ""
    if plan:
        steps = plan.get("steps", [])
        if 0 <= current_step < len(steps):
            step = steps[current_step]
            tool_name = step.get("tools", [""])[0] if step.get("tools") else ""
            description = step.get("description", "")

    if not tool_name:
        return {"pending_confirm": None}

    # Pause and wait for human decision
    decision = interrupt({
        "type": "confirm_action",
        "tool": tool_name,
        "description": description,
        "question": f"确认执行: {description}？",
    })

    if decision is False or decision == "reject":
        # User rejected — skip this step
        return {
            "pending_confirm": None,
            "messages": [SystemMessage(content=f"用户取消了操作: {description}")],
        }

    # User approved — proceed
    return {"pending_confirm": None}


async def agent_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """LLM call with tool selection.

    Binds only active_tools (if specified) to reduce context usage.
    Falls back to ALL_TOOLS when active_tools is empty.
    """
    from langchain_core.messages import HumanMessage
    from icross.api.ai_utils import get_ai_llm

    messages = list(state.get("messages", []))
    active_tools = state.get("active_tools", [])

    # Select tool subset
    if active_tools:
        tool_objects = registry.get_tools_by_names(active_tools)
    else:
        tool_objects = ALL_TOOLS

    # Create LLM with tools bound
    model = get_ai_llm("agent.main", temperature=0.7, max_tokens=4096)
    model_with_tools = model.bind_tools(tool_objects)

    # Prepend system prompt if not already present
    has_system = any(
        isinstance(m, SystemMessage) and m.content == SYSTEM_PROMPT
        for m in messages
    )
    if not has_system:
        messages = [SystemMessage(content=SYSTEM_PROMPT), *messages]

    try:
        response = await model_with_tools.ainvoke(messages, config)
    except Exception as e:
        return {"messages": [AIMessage(content=f"LLM调用失败: {e}")]}

    return {"messages": [response]}


def output_node(state: AgentState) -> dict[str, Any]:
    """Final formatting after all plan steps complete."""
    messages = state.get("messages", [])
    # Ensure the last message is an AIMessage (not a tool result)
    if messages and isinstance(messages[-1], AIMessage):
        return {}  # already good
    return {}


def advance_step_node(state: AgentState) -> dict[str, Any]:
    """Increment current_step after a plan step completes."""
    current_step = state.get("current_step", 0)
    return {"current_step": current_step + 1}


# ── Routing Logic ──────────────────────────────────────────────────

def should_continue(state: AgentState) -> str:
    """Determine next step after agent node.

    - tool_calls → tools
    - more plan steps → router
    - done → output / end
    """
    messages = state.get("messages", [])
    if messages and isinstance(messages[-1], AIMessage) and messages[-1].tool_calls:
        return "tools"

    plan: dict | None = state.get("plan")
    current_step = state.get("current_step", 0)

    if plan:
        steps = plan.get("steps", [])
        next_step = current_step + 1
        if next_step < len(steps):
            return "router"

    return "output"


def plan_router(state: AgentState) -> str:
    """Route from planner to the next node.

    - plan has risky steps → human_confirm
    - plan has steps → router
    - empty plan (no tools needed) → agent (direct reply)
    """
    plan: dict | None = state.get("plan")
    if not plan:
        return "agent"

    steps = plan.get("steps", [])
    if not steps:
        return "agent"

    # Check if first step is risky
    from .planner import RISKY_TOOLS
    first_step = steps[0]
    step_tools = first_step.get("tools", [])
    if any(t in RISKY_TOOLS for t in step_tools):
        return "confirm"

    return "execute"


def post_agent_router(state: AgentState) -> str:
    """Route after tools complete — check for more plan steps."""
    plan: dict | None = state.get("plan")
    current_step = state.get("current_step", 0)

    if not plan:
        return END

    steps = plan.get("steps", [])
    next_step = current_step + 1

    if next_step >= len(steps):
        return END

    return "next"


# ── Graph Builder ──────────────────────────────────────────────────

def create_agent(
    llm_type=None,
    *,
    api_key: str | None = None,
    group_id: str | None = None,
    tools: list | None = None,
    checkpointer=None,
    context_engine: ContextEngine | None = None,
    **llm_kwargs,
):
    """Create a custom LangGraph StateGraph agent with planning and human-in-the-loop.

    Args:
        llm_type: LLM provider type (kept for API compat, defaults to MINIMAX).
        api_key: Optional API key override.
        group_id: Optional group ID (MiniMax specific).
        tools: Tool list (ignored — uses global registry).
        checkpointer: LangGraph checkpointer. Defaults to InMemorySaver.
        context_engine: Optional ContextEngine for long conversation management.
        **llm_kwargs: Additional LLM arguments.
    """
    checkpointer = checkpointer or InMemorySaver()

    workflow = StateGraph(AgentState)

    # ── Add nodes ──
    if context_engine is not None:
        async def _pre_model_hook(state: AgentState) -> dict[str, Any]:
            messages = state.get("messages", [])
            if not await context_engine.should_compress(messages):
                return {}
            updates = await context_engine.compress(messages)
            if updates:
                return {"messages": updates}
            return {}

        workflow.add_node("pre_model_hook", _pre_model_hook)

    workflow.add_node("planner", planner_node)
    workflow.add_node("human_confirm", confirm_node)
    workflow.add_node("router", router_node)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", ToolNode(ALL_TOOLS))
    workflow.add_node("advance_step", advance_step_node)
    workflow.add_node("output", output_node)

    # ── Build edges ──
    if context_engine is not None:
        workflow.set_entry_point("pre_model_hook")
        workflow.add_edge("pre_model_hook", "planner")
    else:
        workflow.set_entry_point("planner")

    # Planner → conditional routing
    workflow.add_conditional_edges(
        "planner",
        plan_router,
        {
            "confirm": "human_confirm",
            "execute": "router",
            "agent": "agent",
        },
    )

    # human_confirm → router (always, after resume)
    workflow.add_edge("human_confirm", "router")

    # router → agent
    workflow.add_edge("router", "agent")

    # agent → conditional
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "router": "advance_step",
            "output": "output",
        },
    )

    # tools → agent (ReAct loop)
    workflow.add_edge("tools", "agent")

    # advance_step → router (next plan step)
    workflow.add_edge("advance_step", "router")

    # output → END
    workflow.add_edge("output", END)

    return workflow.compile(checkpointer=checkpointer)


# ── LazyAgent Wrapper ──────────────────────────────────────────────

class LazyAgent:
    """Lazy-loading agent wrapper that defers creation until first use."""

    def __init__(self, factory):
        self._factory = factory
        self._agent = None

    @property
    def agent(self):
        if self._agent is None:
            self._agent = self._factory()
        return self._agent

    def invoke(self, *args, **kwargs):
        return self.agent.invoke(*args, **kwargs)

    def ainvoke(self, *args, **kwargs):
        return self.agent.ainvoke(*args, **kwargs)

    def stream(self, *args, **kwargs):
        return self.agent.stream(*args, **kwargs)

    def astream(self, *args, **kwargs):
        return self.agent.astream(*args, **kwargs)

    def get_state(self, *args, **kwargs):
        return self.agent.get_state(*args, **kwargs)

    def get_config(self, *args, **kwargs):
        return self.agent.get_config(*args, **kwargs)


def _create_default_agent():
    """Factory function to create the default agent."""
    from icross.api.ai_utils import get_ai_llm

    summary_llm = get_ai_llm("session.title.summarize", temperature=0, max_tokens=1024)
    engine = get_context_engine_for_provider(
        "minimax",
        summary_llm=summary_llm,
        protect_first_n=3,
        protect_last_n=10,
    )
    return create_agent(checkpointer=InMemorySaver(), context_engine=engine)


# Global lazy agent instance
default_agent = LazyAgent(_create_default_agent)
