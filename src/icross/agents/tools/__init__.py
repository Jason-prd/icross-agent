"""Tool registry — centralized tool management replacing manual TOOLS lists."""
from .registry import ToolRegistry, discover_builtin_tools

registry = ToolRegistry()

__all__ = ["registry", "ToolRegistry", "discover_builtin_tools"]
