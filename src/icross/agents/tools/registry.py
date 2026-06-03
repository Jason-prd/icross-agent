"""Tool Registry — centralized tool management inspired by Hermes Agent.

Each tool file imports `registry` and calls ``registry.register(tool_fn, toolset="...")``
at module level. ``discover_builtin_tools()`` uses AST scanning to find and import
all tool modules that contain register calls, enabling auto-discovery without
manual import lists.
"""

from __future__ import annotations

import ast
import importlib
import logging
import threading
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)


def _module_has_register_calls(module_path: Path) -> bool:
    """Return True if the module contains top-level ``registry.register(...)`` calls.

    Only inspects top-level statements so that helper modules which happen
    to call ``registry.register()`` inside a function are not picked up.
    """
    try:
        source = module_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(module_path))
    except (OSError, SyntaxError):
        return False

    for node in tree.body:
        if not isinstance(node, ast.Expr):
            continue
        call = node.value
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        # Match registry.register(...)
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "register"
            and isinstance(func.value, ast.Name)
            and func.value.id == "registry"
        ):
            return True
    return False


def discover_builtin_tools(scan_dir: Path | None = None) -> list[str]:
    """Auto-discover tool modules by scanning *scan_dir* for ``registry.register()`` calls.

    Each matching module is imported, which triggers its module-level
    ``registry.register()`` calls.

    Default *scan_dir* resolves to ``<this_package>/../master/`` (i.e. the
    ``agents/master/`` directory containing all tool files).
    """
    if scan_dir is None:
        scan_dir = Path(__file__).resolve().parent.parent / "master"

    if not scan_dir.is_dir():
        _logger.warning("Tool scan directory not found: %s", scan_dir)
        return []

    # Compute the package prefix for importlib
    # e.g. /home/project/src/icross/agents/master/ → icross.agents.master
    # Find the "icross" segment in the path
    try:
        src_index = scan_dir.resolve().parts.index("icross")
        package_prefix = ".".join(scan_dir.resolve().parts[src_index:])
    except ValueError:
        _logger.warning("Cannot determine package prefix from %s", scan_dir)
        return []

    module_names: list[str] = []
    for path in sorted(scan_dir.glob("*.py")):
        if path.name in {"__init__.py"}:
            continue
        if _module_has_register_calls(path):
            stem = path.stem
            mod_name = f"{package_prefix}.{stem}"
            module_names.append(mod_name)

    imported: list[str] = []
    for mod_name in module_names:
        try:
            importlib.import_module(mod_name)
            imported.append(mod_name)
            _logger.debug("Auto-discovered tool module: %s", mod_name)
        except Exception as e:
            _logger.warning("Failed to import tool module %s: %s", mod_name, e)

    return imported


class ToolRegistry:
    """Singleton registry for tool functions with toolset grouping.

    Usage:
        from icross.agents.tools import registry

        @tool
        def my_tool(...):
            ...
        registry.register(my_tool, toolset="default")
    """

    def __init__(self):
        self._tools: dict[str, dict[str, Any]] = {}
        self._composites: dict[str, list[str]] = {
            # Role-based composites (defined at init, can be extended)
            "operations": ["ozon", "product", "rules"],
            "finance": [
                "ozon_finance_transactions", "ozon_finance_daily_sales",
                "ozon_finance_realization", "update_product_cost_price",
                "calculate_product_price", "calculate_profit_at_price",
                "ozon_transaction_totals",
            ],
            "customer_service": [
                "ozon_chat_history", "ozon_chat_send", "ozon_chat_send_file",
                "ozon_chat_unread_list", "ozon_questions_list",
                "ozon_answer_question", "ozon_reviews_list", "ozon_reply_review",
            ],
            "marketing": [
                "ozon_actions_list", "ozon_register_action_products",
                "ozon_ad_campaigns_list", "ozon_ad_campaign_info",
                "ozon_ad_campaign_create", "ozon_ad_campaign_update",
                "ozon_ad_campaign_stats", "ozon_ad_campaign_products",
            ],
            "full_stack": ["default", "system", "ozon", "product", "rules"],
        }
        self._lock = threading.RLock()

    # ---------------------------------------------------------------
    # Registration
    # ---------------------------------------------------------------

    def register(self, fn, *, toolset: str = "default"):
        """Register a ``@tool``-decorated function.

        Can be used as a post-definition call or as a decorator::

            # Post-definition (preferred):
            @tool
            def my_tool(...):
                ...
            registry.register(my_tool, toolset="ozon")

            # As decorator (must be ABOVE @tool):
            @registry.register(toolset="ozon")
            @tool
            def my_tool(...):
                ...
        """
        name = fn.name if hasattr(fn, "name") else fn.__name__
        with self._lock:
            self._tools[name] = {"tool": fn, "toolset": toolset}
        _logger.debug("Registered tool: %s (toolset=%s)", name, toolset)
        return fn

    def define_composite_toolset(self, name: str, *members: str) -> None:
        """Define a composite toolset that groups multiple toolsets/tools.

        Members can be toolset names, individual tool names, or other
        composite names (resolved recursively).

        Usage::

            registry.define_composite_toolset("my_group", "ozon", "system")
        """
        with self._lock:
            self._composites[name] = list(members)

    def resolve_toolset(self, name: str) -> list:
        """Resolve a toolset name (composite or atomic) to a flat tool list.

        Composites are expanded recursively. Atomic toolsets return
        their tools directly. Unknown names return an empty list.
        """
        with self._lock:
            # Check if it's a composite
            if name in self._composites:
                result = []
                seen = set()
                for member in self._composites[name]:
                    for tool in self._resolve_member(member, seen):
                        result.append(tool)
                return result
            # Atomic toolset
            return [
                e["tool"]
                for e in self._tools.values()
                if e["toolset"] == name
            ]

    def _resolve_member(self, name: str, seen: set) -> list:
        """Recursively resolve a single composite member."""
        if name in seen:
            return []
        seen.add(name)

        # Check if it's a composite
        if name in self._composites:
            result = []
            for member in self._composites[name]:
                result.extend(self._resolve_member(member, seen))
            return result

        # Check if it's a toolset name
        toolset_tools = [
            e["tool"] for e in self._tools.values()
            if e["toolset"] == name
        ]
        if toolset_tools:
            return toolset_tools

        # Check if it's an individual tool name
        entry = self._tools.get(name)
        if entry:
            return [entry["tool"]]

        return []

    def get_tools(self, toolset: str | None = None) -> list:
        """Return a flat list of LangChain BaseTool objects.

        Args:
            toolset: If set, only return tools in this toolset or composite.
                     If None (default), return all tools.
        """
        with self._lock:
            if toolset is None:
                return [e["tool"] for e in self._tools.values()]
            # Check composites first
            if toolset in self._composites:
                seen = set()
                result = []
                for member in self._composites[toolset]:
                    result.extend(self._resolve_member(member, seen))
                return result
            # Atomic toolset
            return [
                e["tool"]
                for e in self._tools.values()
                if e["toolset"] == toolset
            ]

    def get_tool_names(self, toolset: str | None = None) -> list[str]:
        """Return sorted tool names, optionally filtered by toolset."""
        with self._lock:
            return sorted(
                name for name, e in self._tools.items()
                if toolset is None or e["toolset"] == toolset
            )

    def get_tool(self, name: str):
        """Get a single tool by name, or None."""
        with self._lock:
            entry = self._tools.get(name)
            return entry["tool"] if entry else None

    def get_toolsets(self) -> list[str]:
        """Return sorted list of unique toolset names."""
        with self._lock:
            return sorted({e["toolset"] for e in self._tools.values()})

    def get_toolset_for_tool(self, name: str) -> str | None:
        """Return the toolset a tool belongs to, or None."""
        with self._lock:
            entry = self._tools.get(name)
            return entry["toolset"] if entry else None

    def get_tools_by_names(self, names: list[str]) -> list:
        """Return tool objects for a list of tool names (unknown names skipped)."""
        with self._lock:
            return [self._tools[name]["tool"] for name in names if name in self._tools]

    def get_tool_names_by_toolset(self, toolset: str) -> list[str]:
        """Return sorted tool names belonging to a specific atomic toolset."""
        with self._lock:
            return sorted(
                name for name, e in self._tools.items()
                if e["toolset"] == toolset
            )

    def tool_count(self) -> int:
        """Return the total number of registered tools."""
        with self._lock:
            return len(self._tools)
