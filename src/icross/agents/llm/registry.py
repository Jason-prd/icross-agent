"""Transport registry — dictionary-based, matches Hermes registry pattern.

Usage:
    from icross.agents.llm.registry import register_transport, get_transport

    register_transport("anthropic", AnthropicTransport)
    transport = get_transport("anthropic")
    model = transport.create_chat_model(...)
"""

from typing import Any

_REGISTRY: dict[str, type] = {}


def register_transport(transport_type: str, transport_cls: type) -> None:
    """Register a transport class for a transport type string."""
    _REGISTRY[transport_type] = transport_cls


def get_transport(transport_type: str) -> Any | None:
    """Get a transport instance for the given transport type.

    Returns None if no transport is registered.
    """
    cls = _REGISTRY.get(transport_type)
    if cls is None:
        _discover_transports()
        cls = _REGISTRY.get(transport_type)
    if cls is None:
        return None
    return cls()


def list_transports() -> list[str]:
    """List all registered transport types."""
    _discover_transports()
    return list(_REGISTRY.keys())


def _discover_transports() -> None:
    """Import all transport modules to trigger auto-registration."""
    try:
        import icross.agents.llm.transports.anthropic  # noqa: F401
    except ImportError:
        pass
    try:
        import icross.agents.llm.transports.openai  # noqa: F401
    except ImportError:
        pass
