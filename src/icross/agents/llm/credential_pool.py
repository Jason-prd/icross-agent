"""Credential pool — unified API key management.

Adapted from Hermes Agent's credential_pool.py pattern,
simplified for iCross: resolves API keys from environment variables,
.env file, and credential files.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


def resolve_api_key(env_vars: tuple[str, ...] | str) -> str:
    """Resolve an API key from environment variables.

    Checks each env var in order, returns the first non-empty value.

    Args:
        env_vars: One or more environment variable names to check.

    Returns:
        The resolved API key, or empty string if none found.
    """
    if isinstance(env_vars, str):
        env_vars = (env_vars,)
    for var in env_vars:
        val = os.getenv(var, "").strip()
        if val:
            return val
    return ""


def has_api_key(provider_id: str) -> bool:
    """Check if any API key is available for a given provider.

    Args:
        provider_id: Provider identifier (e.g. 'minimax', 'anthropic').

    Returns:
        True if at least one API key is configured.
    """
    from icross.agents.llm.models import get_provider

    provider = get_provider(provider_id)
    if provider is None:
        return False
    return bool(resolve_api_key(provider.api_key_env))
