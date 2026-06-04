"""WebSocket chat endpoint for agent interaction with background task support."""

import asyncio
import json
import logging
import queue as _tqueue
import re
import threading
from contextlib import suppress
from typing import Any

from langgraph.types import Command

_logger = logging.getLogger(__name__)

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from icross.agents.master.agent import default_agent
from icross.core.storage.ozon_data import SessionStorage, ShopStorage, SellerInfoStorage
from icross.services.agent_task_manager import agent_task_manager, _get_raw_queue

router = APIRouter()
session_storage = SessionStorage()
shop_storage = ShopStorage()
seller_info_storage = SellerInfoStorage()

# ── Constants ──
_MAX_WS_FRAME_SIZE = 30 * 1024
_TYPING_INTERVAL = 0.025
_TOKEN_CHUNK_SIZE = 30

# ── Tool description mapping for workflow steps ──
TOOL_DESCRIPTIONS: dict[str, str] = {
    # Ozon 店铺信息
    "ozon_seller_info": "获取店铺基本信息",
    "ozon_product_list": "获取商品列表",
    "ozon_product_info": "获取商品详细信息",
    "ozon_rating_summary": "分析店铺评分数据",
    "ozon_get_warehouses": "获取仓库列表",
    # 商品管理
    "ozon_update_price": "更新商品价格",
    "ozon_update_stock": "更新商品库存",
    "ozon_analytics_stocks": "分析库存数据",
    # 订单管理
    "ozon_order_list": "获取订单列表",
    "ozon_fbs_order_list": "获取FBS订单列表",
    "ozon_fbs_order_info": "查看FBS订单详情",
    "ozon_fbs_ship_orders": "确认打包发货",
    # 财务
    "ozon_finance_transactions": "获取交易流水",
    "ozon_finance_realization": "获取入账明细",
    "ozon_transaction_totals": "汇总交易金额",
    # 广告
    "ozon_ad_campaigns_list": "获取广告活动列表",
    "ozon_ad_campaign_info": "查看广告活动详情",
    "ozon_ad_campaign_stats": "分析广告数据",
    # 客服
    "ozon_chat_history": "获取买家聊天记录",
    "ozon_chat_send": "发送买家消息",
    "ozon_returns_list": "获取退货列表",
    # 营销
    "ozon_actions_list": "获取营销活动列表",
    # Listing
    "generate_listing": "生成商品Listing",
    "translate_text": "翻译文本",
    # 图片
    "generate_product_image": "生成商品图片",
    "remove_background": "去除图片背景",
    # 系统工具
    "get_current_time": "获取当前时间",
    "read_file": "读取文件",
    "write_file": "写入文件",
    "edit_file": "编辑文件",
    "run_command": "执行命令",
    "read_document": "解析文档",
    # 定价
    "calculate_cost": "计算成本利润",
    "apply_pricing_rule": "应用定价规则",
    # 知识库
    "search_ozon_rules": "查询Ozon平台规则",
    # 报表
    "generate_report": "生成报表",
    # 通知
    "send_notification": "发送通知",
    # 工作流 & 调度器
    "remove_scheduled_job": "删除定时任务",
    "list_workflows": "查看工作流列表",
    "start_workflow": "启动工作流",
    "get_workflow_status": "查询工作流状态",
    "run_auto_pipeline": "执行自动化选品上架流水线",
    # 复合任务
    "list_compound_tasks": "列出可用的复合任务模板",
    "run_compound_task": "执行复合任务（多步骤跨域自动编排）",
    "get_compound_task_status": "查询复合任务执行状态",
}


def _describe_tools(tool_names: list[str]) -> str:
    """Generate a human-readable description for a group of tools being called."""
    if not tool_names:
        return "处理中"
    if len(tool_names) == 1:
        return TOOL_DESCRIPTIONS.get(tool_names[0], f"执行{tool_names[0]}")
    names = [TOOL_DESCRIPTIONS.get(t, t) for t in tool_names]
    return "、".join(names)

# ── Per-session background task state (survives WebSocket reconnection) ──
_known_threads: set[str] = set()
_session_tasks: dict[str, asyncio.Task] = {}  # Kept for backward compat; new code uses agent_task_manager
_session_queues: dict[str, asyncio.Queue] = {}
_queued_messages: dict[str, list[dict]] = {}
_session_data: dict[str, dict] = {}

# ── Cross-thread confirm/reject state ──
# _pending_confirms[session_id] = threading.Event() — agent thread waits on this
# _confirm_decisions[session_id] = True/False — set by WS handler, read by agent thread
_pending_confirms: dict[str, threading.Event] = {}
_confirm_decisions: dict[str, bool] = {}
_confirm_lock = threading.Lock()


def _set_confirm_decision(session_id: str, decision: bool) -> bool:
    """Store a confirm/reject decision and signal the waiting agent thread.

    Returns True if there was a pending confirm to resolve.
    """
    with _confirm_lock:
        ev = _pending_confirms.get(session_id)
        if ev is None:
            return False
        _confirm_decisions[session_id] = decision
        ev.set()
        return True


def _sdata(session_id: str) -> dict:
    """Get or create mutable per-session data dict."""
    if session_id not in _session_data:
        _session_data[session_id] = {
            "shop_id": "",
            "multi_shop_ids": [],
            "is_first_message": True,
        }
    return _session_data[session_id]


def _squeue(session_id: str) -> asyncio.Queue:
    """Get or create per-session event queue."""
    if session_id not in _session_queues:
        _session_queues[session_id] = asyncio.Queue()
    return _session_queues[session_id]


# ── Event helpers (generic so they work with both WebSocket and Queue) ──

async def _send_json_safe(send_fn, data: dict[str, Any]):
    """Send JSON, chunking if payload exceeds max frame size."""
    payload = json.dumps(data, ensure_ascii=False, default=str)
    if len(payload) <= _MAX_WS_FRAME_SIZE:
        await send_fn(payload)
        return
    total_chunks = (len(payload) + _MAX_WS_FRAME_SIZE - 1) // _MAX_WS_FRAME_SIZE
    for i in range(total_chunks):
        chunk = payload[i * _MAX_WS_FRAME_SIZE:(i + 1) * _MAX_WS_FRAME_SIZE]
        chunk_msg = json.dumps({
            "type": "_chunk", "chunk_index": i,
            "total_chunks": total_chunks, "data": chunk,
        }, ensure_ascii=False)
        await send_fn(chunk_msg)


async def _stream_text(send_fn, text: str, event_type: str = "token"):
    """Send text content progressively in small chunks (typewriter effect)."""
    if not text:
        return
    for i in range(0, len(text), _TOKEN_CHUNK_SIZE):
        chunk = text[i:i + _TOKEN_CHUNK_SIZE]
        await send_fn({"type": event_type, "content": chunk})
        await asyncio.sleep(_TYPING_INTERVAL)


# ── Helpers ──

async def _get_shop_context(shop_id: str) -> str:
    if not shop_id:
        return ""
    shop = await shop_storage.get_shop(shop_id)
    if not shop:
        return ""
    seller_info = await seller_info_storage.get_seller_info(shop_id)
    context_parts = [f"当前店铺: {shop.get('name', shop_id)} (shop_id: {shop_id})"]
    if seller_info:
        if seller_info.get("company"):
            context_parts.append(f"公司: {seller_info['company']}")
        if seller_info.get("ratings"):
            ratings = seller_info["ratings"]
            rating_info = ", ".join([
                f"{r.get('name', 'N/A')}: {r.get('current_value', 'N/A')}"
                for r in ratings[:3] if r.get('current_value')
            ])
            if rating_info:
                context_parts.append(f"评分: {rating_info}")
    return " | ".join(context_parts)


async def _generate_session_title(session_id: str, first_message: str) -> str:
    from icross.api.ai_utils import get_ai_llm
    llm = get_ai_llm("session.title.summarize")
    prompt = (
        f"根据以下用户的第一条消息，生成一个简短的中文会话标题（最多10个字）：\n"
        f"\"{first_message[:100]}\"\n"
        f"只返回标题，不要任何解释。"
    )
    try:
        response = await llm.ainvoke([{"role": "user", "content": prompt}])
        raw_content = response.content
        if isinstance(raw_content, list):
            texts = []
            for block in raw_content:
                if isinstance(block, dict) and block.get("type") == "text":
                    texts.append(block.get("text", ""))
            raw_content = "\n".join(texts)
        title = raw_content.strip().strip('"').strip("：").strip(":").strip()
        if title and len(title) <= 20:
            return title
    except Exception:
        pass
    return first_message[:8] if first_message else "新会话"


def _parse_minimax_content(content: Any) -> tuple[str, str]:
    if isinstance(content, list):
        thinking = ""
        text = ""
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "thinking":
                    thinking = block.get("thinking", "") or ""
                elif block.get("type") == "text":
                    text = block.get("text", "") or ""
        return thinking, text
    if isinstance(content, str):
        if "[思考]" in content:
            parts = content.split("[思考]", 1)
            return parts[0].strip(), parts[1].strip() if len(parts) > 1 else ""
        return "", content
    return "", str(content) if content else ""


def _message_to_dict(msg: Any) -> dict:
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
    if isinstance(msg, HumanMessage):
        return {"type": "human", "content": msg.content}
    elif isinstance(msg, AIMessage):
        result = {"type": "ai", "content": msg.content}
        if msg.tool_calls:
            result["tool_calls"] = msg.tool_calls
        return result
    elif isinstance(msg, ToolMessage):
        return {
            "type": "tool_result",
            "tool_call_id": msg.tool_call_id,
            "name": msg.name,
            "content": msg.content,
        }
    else:
        return {"type": "unknown", "content": str(msg)}


# ── Background Agent Task ──

async def _run_agent(
    session_id: str,
    user_message: str,
    full_message: str,
    config: dict,
    *,
    # Optional custom emit function (for thread-pool mode).
    # When provided, events go here instead of asyncio.Queue.
    _emit_fn=None,
    # Optional cancellation event for thread-pool mode.
    _cancel_event=None,
):
    """Run agent in background, streaming events to the per-session queue.

    Supports multi-round execution with interrupt/resume for human-in-the-loop
    confirmation of dangerous operations (发货/改价/删除等).

    Args:
        _emit_fn: Optional async callable(json_str). If None, uses asyncio.Queue.
        _cancel_event: Optional threading.Event checked between iterations.
    """
    sd = _sdata(session_id)

    # Choose emit mechanism
    if _emit_fn is not None:
        emit = _emit_fn
    else:
        queue = _squeue(session_id)
        async def emit(payload: str):
            await queue.put(payload)

    async def emit_dict(data: dict):
        await _send_json_safe(emit, data)

    # Helper to persist events for frontend replay
    async def persist_ev(event: dict):
        await agent_task_manager.persist_event(session_id, event)

    # ── Track plan steps for UI workflow_step events ──
    plan_steps: list[dict] | None = None
    completed_step_indices: set[int] = set()

    try:
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

        # Load stored messages if checkpointer was reset
        if session_id not in _known_threads:
            _known_threads.add(session_id)
            stored = await session_storage.get_messages(session_id)

            # First pass: collect all tool_call_ids that have results
            tool_result_ids: set[str] = set()
            for m in stored:
                mt = m.get("message_type") or m.get("type", "")
                if mt == "tool_result" and m.get("tool_call_id"):
                    tool_result_ids.add(str(m["tool_call_id"]))

            # Second pass: build history, filtering orphaned tool_calls
            history = []
            for m in stored:
                mt = m.get("message_type") or m.get("type", "")
                ct = m.get("content", "")
                if mt == "human":
                    history.append(HumanMessage(content=ct))
                elif mt == "ai":
                    tc = m.get("tool_calls")
                    if tc:
                        # Only keep tool_calls that have matching ToolMessages
                        valid_tc = [t for t in tc if t.get("id") in tool_result_ids]
                        if valid_tc:
                            history.append(AIMessage(content=ct or "", tool_calls=valid_tc))
                        elif ct:
                            # Orphaned tool_calls — strip them, keep content (thinking)
                            history.append(AIMessage(content=ct))
                        else:
                            # Nothing useful — skip entirely
                            pass
                    elif ct:
                        history.append(AIMessage(content=ct))
                elif mt == "tool_result":
                    history.append(ToolMessage(
                        content=ct or "",
                        tool_call_id=m.get("tool_call_id") or "",
                        name=m.get("name") or m.get("tool_name") or "tool",
                    ))
            all_messages = [*history, HumanMessage(content=full_message)]
        else:
            all_messages = [HumanMessage(content=full_message)]

        # ── Multi-round agent execution (interrupt/resume loop) ──
        workflow_step_index = 0
        active_tool_names: list[str] = []
        final_text = ""
        stream_input = {"messages": all_messages}

        while True:
            interrupted = False
            confirm_info: dict | None = None

            async for event in default_agent.astream(stream_input, config, stream_mode="updates"):
                if not event:
                    continue

                # Check cancellation (thread-pool mode)
                if _cancel_event and _cancel_event.is_set():
                    await emit_dict({"type": "stopped"})
                    await persist_ev({"type": "stopped"})
                    return

                if not isinstance(event, dict):
                    continue

                # ── Detect interrupt (human_confirm node) ──
                if "__interrupt__" in event:
                    interrupted = True
                    interrupts = event["__interrupt__"]
                    for i in interrupts:
                        val = i.value if hasattr(i, 'value') else None
                        if isinstance(val, dict) and val.get("type") == "confirm_action":
                            confirm_info = val
                    break  # Exit inner loop to handle resume

                # ── Planner node: structured plan → workflow_step events ──
                if "planner" in event:
                    planner_out = event["planner"]
                    if isinstance(planner_out, dict) and planner_out.get("plan"):
                        pd = planner_out["plan"]
                        steps = pd.get("steps", [])
                        if steps:
                            plan_steps = steps
                            for ps in steps:
                                step_ev = {
                                    "type": "workflow_step", "step": ps["step"],
                                    "tools": ps.get("tools", []),
                                    "status": "pending",
                                    "description": ps.get("description",
                                        _describe_tools(ps.get("tools", []))),
                                }
                                await emit_dict(step_ev)
                                await persist_ev(step_ev)
                    continue

                # ── Human confirm (after resume from interrupt) ──
                if "human_confirm" in event:
                    # After resume, the node returns {pending_confirm: None}
                    # or includes a rejection SystemMessage.
                    confirm_out = event["human_confirm"]
                    if isinstance(confirm_out, dict) and confirm_out.get("messages"):
                        for m in confirm_out["messages"]:
                            if isinstance(m, SystemMessage):
                                await emit_dict({"type": "token", "content": m.content or ""})
                    continue

                # ── Advance step: step tracking ──
                if "advance_step" in event:
                    adv_out = event["advance_step"]
                    if isinstance(adv_out, dict) and "current_step" in adv_out:
                        old_step = adv_out["current_step"] - 1
                        if old_step >= 0 and plan_steps and old_step < len(plan_steps):
                            completed_step_indices.add(old_step)
                            step_ev = {
                                "type": "workflow_step", "step": old_step,
                                "status": "completed",
                                "description": plan_steps[old_step].get("description", ""),
                            }
                            await emit_dict(step_ev)
                            await persist_ev(step_ev)
                    continue

                # ── Agent node ──
                if "agent" in event:
                    agent_output = event["agent"]
                    if isinstance(agent_output, dict) and "messages" in agent_output:
                        for msg in agent_output["messages"]:
                            if isinstance(msg, AIMessage):
                                if msg.tool_calls:
                                    if workflow_step_index > 0:
                                        await emit_dict({"type": "round_end"})

                                    thinking, _ = _parse_minimax_content(msg.content)

                                    # Stream thinking
                                    if thinking:
                                        await _stream_text(emit_dict, thinking, "thinking_token")

                                    # Emit current tool calls as running
                                    tool_names = [tc["name"] for tc in msg.tool_calls]
                                    active_tool_names = tool_names
                                    await agent_task_manager.update_progress(
                                        session_id,
                                        current_tool=tool_names[0] if tool_names else None,
                                        current_step=workflow_step_index,
                                    )
                                    step_description = _describe_tools(tool_names)
                                    if plan_steps and workflow_step_index < len(plan_steps):
                                        step_description = plan_steps[workflow_step_index].get("description", step_description)
                                    step_ev = {
                                        "type": "workflow_step", "step": workflow_step_index,
                                        "tools": tool_names, "status": "running",
                                        "description": step_description,
                                    }
                                    await emit_dict(step_ev)
                                    await persist_ev(step_ev)
                                    for tc in msg.tool_calls:
                                        tc_ev = {"type": "tool_call", "name": tc["name"], "status": "running"}
                                        await emit_dict(tc_ev)
                                        await persist_ev(tc_ev)
                                    msg_dict = _message_to_dict(msg)
                                    await session_storage.save_message(
                                        session_id=session_id,
                                        message_type=msg_dict.get("type", "unknown"),
                                        content=msg_dict.get("content", ""),
                                        tool_name=msg_dict.get("name"),
                                        tool_call_id=msg_dict.get("tool_call_id"),
                                        tool_calls=msg_dict.get("tool_calls"),
                                    )
                                else:
                                    if workflow_step_index > 0:
                                        await emit_dict({"type": "round_end"})
                                    msg_dict = _message_to_dict(msg)
                                    await session_storage.save_message(
                                        session_id=session_id,
                                        message_type=msg_dict.get("type", "unknown"),
                                        content=msg_dict.get("content", ""),
                                        tool_name=msg_dict.get("name"),
                                        tool_call_id=msg_dict.get("tool_call_id"),
                                        tool_calls=msg_dict.get("tool_calls"),
                                    )
                                    thinking, text = _parse_minimax_content(msg.content)
                                    if thinking:
                                        await _stream_text(emit_dict, thinking, "thinking_token")
                                    if text:
                                        await _stream_text(emit_dict, text, "token")
                                        final_text += text

                # ── Tools node ──
                if "tools" in event:
                    tools_output = event["tools"]
                    if isinstance(tools_output, dict) and "messages" in tools_output:
                        for msg in tools_output["messages"]:
                            if isinstance(msg, ToolMessage):
                                tool_name = msg.name or "unknown"
                                tc_ev = {"type": "tool_call", "name": tool_name, "status": "completed"}
                                await emit_dict(tc_ev)
                                await persist_ev(tc_ev)
                                if active_tool_names:
                                    active_tool_names = [t for t in active_tool_names if t != tool_name]
                                    if not active_tool_names:
                                        step_description = ""
                                        if plan_steps and workflow_step_index < len(plan_steps):
                                            step_description = plan_steps[workflow_step_index].get("description", "")
                                        step_ev = {
                                            "type": "workflow_step", "step": workflow_step_index,
                                            "status": "completed", "description": step_description,
                                        }
                                        await emit_dict(step_ev)
                                        await persist_ev(step_ev)
                                        completed_step_indices.add(workflow_step_index)
                                        workflow_step_index += 1
                                        await agent_task_manager.update_progress(session_id, current_step=workflow_step_index)
                                msg_dict = _message_to_dict(msg)
                                await session_storage.save_message(
                                    session_id=session_id,
                                    message_type=msg_dict.get("type", "unknown"),
                                    content=msg_dict.get("content", ""),
                                    tool_name=msg_dict.get("name"),
                                    tool_call_id=msg_dict.get("tool_call_id"),
                                    tool_calls=msg_dict.get("tool_calls"),
                                )

            # ── Handle interrupt: wait for user decision ──
            if not interrupted:
                break

            if confirm_info:
                await emit_dict({
                    "type": "confirm_required",
                    "tool": confirm_info.get("tool", ""),
                    "description": confirm_info.get("description", ""),
                    "question": confirm_info.get("question", ""),
                })
                await persist_ev({
                    "type": "confirm_required",
                    "tool": confirm_info.get("tool", ""),
                    "description": confirm_info.get("description", ""),
                })

            # Wait for user decision (cross-thread: WS handler sets the event)
            with _confirm_lock:
                _pending_confirms[session_id] = threading.Event()
                _confirm_decisions.pop(session_id, None)
            confirm_ev = _pending_confirms[session_id]

            while not confirm_ev.is_set():
                if _cancel_event and _cancel_event.is_set():
                    with _confirm_lock:
                        _pending_confirms.pop(session_id, None)
                        _confirm_decisions.pop(session_id, None)
                    await emit_dict({"type": "stopped"})
                    await persist_ev({"type": "stopped"})
                    return
                await asyncio.sleep(0.1)

            decision = _confirm_decisions.pop(session_id, None)
            with _confirm_lock:
                _pending_confirms.pop(session_id, None)

            # Resume the graph with Command(resume=...)
            stream_input = Command(resume=decision is not False)

        # ── Finalization ──
        # Mark any remaining plan steps as completed
        if plan_steps:
            for ps in plan_steps:
                idx = ps["step"]
                if idx not in completed_step_indices:
                    completed_step_indices.add(idx)
                    step_ev = {
                        "type": "workflow_step", "step": idx,
                        "status": "completed",
                        "description": ps.get("description", ""),
                    }
                    await emit_dict(step_ev)

        # Only set completion if we weren't cancelled
        if _cancel_event and _cancel_event.is_set():
            pass  # already sent "stopped" above
        else:
            await emit_dict({"type": "message_end"})
            await persist_ev({"type": "message_end"})
            await agent_task_manager.complete_task(session_id, final_output=final_text or None)

        # Auto-generate session title
        if sd.get("is_first_message"):
            title = await _generate_session_title(session_id, user_message)
            await session_storage.update_session_title(session_id, title)
            sd["is_first_message"] = False
            await emit_dict({
                "type": "session_title", "session_id": session_id, "title": title,
            })

    except asyncio.CancelledError:
        await emit_dict({"type": "stopped"})
        await persist_ev({"type": "stopped"})
    except Exception as e:
        _logger.exception(f"Agent task failed for session {session_id}: {e}")
        await emit_dict({"type": "error", "message": str(e)})
        await persist_ev({"type": "error", "message": str(e)})
        await agent_task_manager.fail_task(session_id, error=str(e))
    finally:
        _session_tasks.pop(session_id, None)
        # In asyncio mode, drain queue after agent finishes.
        # In thread mode, sentinel is handled by agent_exec_handler.
        if _emit_fn is None:
            await queue.put(None)  # sentinel


async def _start_agent_task(session_id: str, payload: dict, ws: WebSocket, sd: dict):
    """Extract message from payload, build context, and start background agent task."""
    user_message = payload.get("content", "").strip()
    if not user_message:
        return
    msg_shop_ids = payload.get("shop_ids", [])
    msg_shop_id = payload.get("shop_id", sd["shop_id"] if not msg_shop_ids else "")

    # Update shop context
    if msg_shop_ids:
        sd["multi_shop_ids"] = msg_shop_ids
    elif msg_shop_id and msg_shop_id != sd["shop_id"]:
        sd["shop_id"] = msg_shop_id
        sd["multi_shop_ids"] = []

    # Build config — include all shop IDs for multi-shop mode
    config: dict = {"configurable": {"thread_id": session_id, "shop_id": sd["shop_id"]}}
    if sd.get("multi_shop_ids"):
        config["configurable"]["shop_ids"] = sd["multi_shop_ids"]

    if msg_shop_ids:
        context_parts = []
        for sid in msg_shop_ids:
            shop = await shop_storage.get_shop(sid)
            if shop:
                context_parts.append(f"店铺 {shop.get('name', sid)} (shop_id: {sid})")
        full_message = f"[多店铺模式] {', '.join(context_parts)}\n\n用户请求: {user_message}\n\n请针对以上店铺执行相应操作。" if context_parts else user_message
    elif sd["shop_id"]:
        shop_context = await _get_shop_context(sd["shop_id"])
        full_message = f"{shop_context}\n\n用户: {user_message}" if shop_context else user_message
    else:
        full_message = user_message

    # Echo user message
    await _send_json_safe(
        lambda s: ws.send_text(s),
        {"type": "human", "content": user_message},
    )
    await session_storage.save_message(
        session_id=session_id, message_type="human",
        content=user_message,
    )

    # Start background agent task via thread-pool executor
    await agent_task_manager.start_agent_task(
        session_id, user_message, full_message, config,
    )


# ── WebSocket Endpoint ──

@router.websocket("/chat")
async def chat(ws: WebSocket, session_id: str = "default", shop_id: str = ""):
    """WebSocket endpoint for agent conversation with background task support.

    Messages with 'action':'stop' cancel the running task.
    Messages sent while a task is running are queued and auto-processed when the
    current task finishes.
    """
    await ws.accept()

    # ── Demo mode: return canned responses ──
    from icross.core.config import is_demo_mode
    if is_demo_mode():
        await _send_json_safe(
            lambda s: ws.send_text(s),
            {"type": "session_state", "has_active_task": False, "agent_status": None},
        )
        # Auto-send demo greeting
        await _send_json_safe(
            lambda s: ws.send_text(s),
            {"type": "ai", "content": "🎯 欢迎使用 iCross Agent 演示模式！\n\n当前为**演示模式**，数据为模拟数据。\n\n要体验完整功能，请在 `.env` 文件中配置：\n- **DEEPSEEK_API_KEY**（AI 对话）\n- **OZON_CLIENT_ID** + **OZON_API_KEY**（店铺运营）\n\n然后设置 `ICROSS_DEMO_MODE=false` 重新启动。\n\n---\n\n你可以点击左侧菜单浏览：\n- **运营工作台** — 查看看板、选品、商品管理等界面\n- **配置管理** — 查看 LLM 提供商、店铺等配置页面"},
        )
        await _send_json_safe(
            lambda s: ws.send_text(s),
            {"type": "message_end"},
        )
        # Keep connection alive until client disconnects
        try:
            while True:
                raw = await ws.receive_text()
                payload = json.loads(raw)
                action = payload.get("action", "")
                if action == "stop":
                    break
                # Echo user message, then reply with demo notice
                await _send_json_safe(
                    lambda s: ws.send_text(s),
                    {"type": "human", "content": payload.get("content", "")},
                )
                await _send_json_safe(
                    lambda s: ws.send_text(s),
                    {"type": "ai", "content": "当前为**演示模式**，AI Agent 功能不可用。请配置 API Key 后重启使用。"},
                )
                await _send_json_safe(
                    lambda s: ws.send_text(s),
                    {"type": "message_end"},
                )
        except WebSocketDisconnect:
            pass
        return
    await session_storage.ensure_session(session_id)
    sd = _sdata(session_id)
    if shop_id:
        sd["shop_id"] = shop_id

    # Send session state so frontend can re-attach to background tasks
    has_active_task = agent_task_manager.is_running(session_id)
    agent_status = await agent_task_manager.get_status(session_id)
    await _send_json_safe(
        lambda s: ws.send_text(s),
        {"type": "session_state", "has_active_task": has_active_task, "agent_status": agent_status},
    )

    # Forwarder: reads from thread-safe queue (agent runs in thread pool) → sends to WebSocket.
    # Does NOT exit on None sentinel (which signals one agent completing) —
    # instead keeps reading for subsequent agent executions in the same session.
    async def forward():
        try:
            raw_queue = _get_raw_queue(session_id)
            loop = asyncio.get_running_loop()
            while True:
                try:
                    payload = await loop.run_in_executor(
                        None, lambda: raw_queue.get(timeout=0.5),
                    )
                    if payload is None:
                        # One agent finished — wait for next one (or WS disconnect)
                        continue
                    await ws.send_text(payload)
                except _tqueue.Empty:
                    continue
                except WebSocketDisconnect:
                    break
        except WebSocketDisconnect:
            pass

    forwarder = asyncio.create_task(forward())

    try:
        while True:
            # ── Auto-process queued messages when no active task ──
            if not agent_task_manager.is_running(session_id):
                queued = _queued_messages.get(session_id, [])
                if queued:
                    await _start_agent_task(session_id, queued.pop(0), ws, sd)
                    continue

            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            try:
                payload = json.loads(raw)
                action = payload.get("action", "")
                user_message = payload.get("content", "")
            except json.JSONDecodeError:
                user_message = raw
                action = ""
                payload = {"content": raw}

            # ── Stop action ──
            if action == "stop":
                agent_task_manager.cancel_task(session_id)
                continue

            # ── Confirm/Reject action (human-in-the-loop) ──
            if action in ("confirm", "reject"):
                decision = action == "confirm"
                if _set_confirm_decision(session_id, decision):
                    await _send_json_safe(
                        lambda s: ws.send_text(s),
                        {"type": "confirm_result", "action": action},
                    )
                else:
                    await _send_json_safe(
                        lambda s: ws.send_text(s),
                        {"type": "error", "message": "没有待确认的操作"},
                    )
                continue

            if not user_message:
                continue

            # ── If a task is already running, queue this message ──
            if agent_task_manager.is_running(session_id):
                _queued_messages.setdefault(session_id, []).append(payload)
                await _send_json_safe(
                    lambda s: ws.send_text(s),
                    {"type": "queued"},
                )
                continue

            # ── Start new task ──
            await _start_agent_task(session_id, payload, ws, sd)

    except WebSocketDisconnect:
        # Cancel any running agent task when client disconnects
        agent_task_manager.cancel_task(session_id)
    except Exception as e:
        try:
            await _send_json_safe(
                lambda s: ws.send_text(s),
                {"type": "error", "message": str(e)},
            )
        except Exception:
            pass
    finally:
        forwarder.cancel()
        with suppress(asyncio.CancelledError):
            await forwarder
