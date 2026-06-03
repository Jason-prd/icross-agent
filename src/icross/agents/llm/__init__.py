"""LLM Factory — public API for iCross multi-model system.

Replaces the old icross.agents.master.llm module while maintaining
backward compatibility.

Usage:
    from icross.agents.llm import get_llm, list_providers

    # New API
    model = get_llm("minimax", model="claude-sonnet-4-20250514")
    model = get_llm("deepseek")

    # List available providers
    providers = list_providers()

    # Old API (backward compatible)
    from icross.agents.llm import create_llm, LLMType
    model = create_llm(LLMType.MINIMAX)
"""

from __future__ import annotations

from typing import Any, Optional

from icross.agents.llm.credential_pool import resolve_api_key
from icross.agents.llm.models import ProviderDef, get_provider, load_providers
from icross.agents.llm.registry import get_transport


def get_llm(
    provider_id: str,
    *,
    model: str | None = None,
    api_key: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    **kwargs: Any,
):
    """Create a LangChain chat model for the given provider.

    This is the primary entry point for the new multi-model system.

    Args:
        provider_id: Provider ID or alias (e.g. 'minimax', 'anthropic', 'deepseek').
        model: Model name. Defaults to provider's default_model if not set.
        api_key: API key. Auto-resolved from env if not set.
        temperature: Sampling temperature.
        max_tokens: Maximum tokens to generate.
        **kwargs: Additional provider-specific arguments.

    Returns:
        A configured BaseChatModel instance.

    Raises:
        ValueError: If provider is unknown or transport is not available.
    """
    provider = get_provider(provider_id)
    if provider is None:
        raise ValueError(
            f"Unknown provider: {provider_id}. "
            f"Available: {', '.join(list_providers().keys())}"
        )

    transport = get_transport(provider.transport)
    if transport is None:
        raise ValueError(
            f"No transport registered for provider '{provider_id}' "
            f"(transport type: {provider.transport})"
        )

    resolved_key = api_key or provider.resolve_api_key()
    if not resolved_key:
        raise ValueError(
            f"No API key found for provider '{provider_id}'. "
            f"Set the {provider.api_key_env} environment variable."
        )

    resolved_model = model or provider.default_model
    if not resolved_model:
        raise ValueError(
            f"No model specified for provider '{provider_id}' "
            f"and no default_model configured"
        )

    resolved_base_url = provider.resolve_base_url()

    return transport.create_chat_model(
        model=resolved_model,
        api_key=resolved_key,
        base_url=resolved_base_url,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs,
    )


def list_providers() -> dict[str, ProviderDef]:
    """List all available providers with their definitions."""
    return load_providers()


# ============================================================
# Backward-compatible API (delegates to new system)
# ============================================================

from enum import Enum


class LLMType(Enum):
    """Supported LLM types (legacy enum, kept for backward compat)."""
    MINIMAX = "minimax"
    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"


_LLMTYPE_TO_PROVIDER = {
    LLMType.MINIMAX: "minimax",
    LLMType.ANTHROPIC: "anthropic",
    LLMType.DEEPSEEK: "deepseek",
}


def create_llm(
    llm_type: LLMType,
    *,
    api_key: str | None = None,
    group_id: str | None = None,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    **kwargs: Any,
):
    """Legacy create_llm — delegates to new get_llm().

    Args:
        llm_type: LLMType enum value.
        api_key: API key (auto-resolved from env if not set).
        group_id: Ignored, kept for backward compatibility.
        model: Model name.
        temperature: Sampling temperature.
        max_tokens: Maximum tokens to generate.
        **kwargs: Additional provider-specific arguments.

    Returns:
        A configured BaseChatModel instance.
    """
    provider_id = _LLMTYPE_TO_PROVIDER.get(llm_type)
    if provider_id is None:
        raise ValueError(f"Unknown LLMType: {llm_type}")

    return get_llm(
        provider_id,
        model=model,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs,
    )


def create_minimax(api_key: str | None = None, **kwargs: Any):
    """Convenience: create MiniMax model."""
    return get_llm("minimax", api_key=api_key, **kwargs)


def create_anthropic(api_key: str | None = None, **kwargs: Any):
    """Convenience: create Anthropic model."""
    return get_llm("anthropic", api_key=api_key, **kwargs)


def create_deepseek(api_key: str | None = None, **kwargs: Any):
    """Convenience: create DeepSeek model."""
    return get_llm("deepseek", api_key=api_key, **kwargs)
