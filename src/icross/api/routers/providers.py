"""LLM Provider configuration REST API.

CRUD endpoints for managing LLM provider definitions (stored in data/providers.json).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from icross.agents.llm.models import (
    ALIASES,
    _DEFAULT_PROVIDERS,
    load_providers,
    save_providers,
)

_logger = logging.getLogger(__name__)
router = APIRouter(prefix="/providers", tags=["providers"])

_PROVIDERS_PATH = Path(__file__).parent.parent.parent.parent.parent / "data" / "providers.json"


@router.get("")
async def list_providers():
    """List all LLM providers (merged defaults + user overrides).

    API keys are masked in the response.
    """
    providers = load_providers()
    return {
        "providers": {
            pid: p.to_api_dict(show_key=False)
            for pid, p in providers.items()
        },
        "builtin": list(_DEFAULT_PROVIDERS.keys()),
        "aliases": {
            alias: pid
            for alias, pid in ALIASES.items()
            if alias != pid
        },
    }


@router.get("/{provider_id}")
async def get_provider(provider_id: str):
    """Get a single provider definition."""
    from icross.agents.llm.models import get_provider as _get_provider

    provider = _get_provider(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' not found")
    return provider.to_api_dict(show_key=False)


@router.put("/{provider_id}")
async def update_provider(provider_id: str, body: dict[str, Any]):
    """Update a provider's editable fields.

    Editable fields: api_key, base_url, default_model, name, doc.
    Non-editable fields (id, transport, api_key_env, base_url_env) are ignored.
    Built-in providers can be overridden; new providers are created.
    """
    from icross.agents.llm.models import get_provider as _get_provider

    provider = _get_provider(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' not found")
    provider_id = provider.id  # use resolved ID

    raw: dict[str, Any] = {}
    if _PROVIDERS_PATH.exists():
        try:
            raw = json.loads(_PROVIDERS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            raw = {}

    # Get or create entry for this provider
    entry = raw.get(provider_id, {})
    orig_entry = dict(entry)

    # Update only allowed fields (skip api_key if empty)
    for key in ("base_url", "default_model", "name", "doc", "context_length"):
        if key in body:
            entry[key] = body[key]
    if body.get("api_key"):
        entry["api_key"] = body["api_key"]

    if entry == orig_entry and not any(
        k in body for k in ("api_key", "base_url", "default_model", "name", "doc", "context_length")
    ):
        raise HTTPException(status_code=400, detail="No editable fields provided")

    raw[provider_id] = entry

    if save_providers(raw):
        _logger.info("Provider '%s' updated", provider_id)
        # Reload and return updated view
        updated = load_providers().get(provider_id)
        return updated.to_api_dict(show_key=False) if updated else {"status": "saved"}
    else:
        raise HTTPException(status_code=500, detail="Failed to save providers")


@router.post("")
async def create_provider(body: dict[str, Any]):
    """Create a new custom provider.

    Required fields: id, name, transport.
    Optional fields: api_key_env, base_url, base_url_env, default_model, api_key, doc.
    """
    provider_id = body.get("id", "").strip()
    if not provider_id:
        raise HTTPException(status_code=400, detail="Provider 'id' is required")

    import re
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_-]*$', provider_id):
        raise HTTPException(
            status_code=400,
            detail="Provider 'id' must start with a letter and contain only letters, digits, hyphens, and underscores",
        )

    if not body.get("name", "").strip():
        raise HTTPException(status_code=400, detail="Provider 'name' is required")

    transport = body.get("transport", "").strip()
    if transport not in ("anthropic", "openai"):
        raise HTTPException(status_code=400, detail="transport must be 'anthropic' or 'openai'")

    # Check if already exists
    providers = load_providers()
    if provider_id in providers:
        raise HTTPException(
            status_code=409,
            detail=f"Provider '{provider_id}' already exists. Use PUT to update.",
        )

    raw = {}
    if _PROVIDERS_PATH.exists():
        try:
            raw = json.loads(_PROVIDERS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            raw = {}

    raw[provider_id] = {
        "name": body["name"],
        "transport": transport,
        "api_key_env": body.get("api_key_env", f"{provider_id.upper()}_API_KEY"),
        "base_url": body.get("base_url", ""),
        "base_url_env": body.get("base_url_env", ""),
        "default_model": body.get("default_model", ""),
        "api_key": body.get("api_key", ""),
        "doc": body.get("doc", ""),
        "context_length": body.get("context_length", 200000),
    }

    if save_providers(raw):
        _logger.info("Provider '%s' created", provider_id)
        updated = load_providers().get(provider_id)
        return updated.to_api_dict(show_key=False) if updated else {"status": "created"}
    else:
        raise HTTPException(status_code=500, detail="Failed to save providers")


@router.delete("/{provider_id}")
async def delete_provider(provider_id: str):
    """Delete a custom provider from providers.json.

    Built-in providers cannot be deleted (they'll reappear from defaults).
    """
    from icross.agents.llm.models import get_provider as _get_provider

    provider = _get_provider(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' not found")
    provider_id = provider.id

    if provider_id in _DEFAULT_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"'{provider_id}' is a built-in provider and cannot be deleted. "
            f"Reset its fields to empty instead.",
        )

    raw: dict[str, Any] = {}
    if _PROVIDERS_PATH.exists():
        try:
            raw = json.loads(_PROVIDERS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            raw = {}

    if provider_id not in raw:
        raise HTTPException(
            status_code=404,
            detail=f"Provider '{provider_id}' not found in saved config",
        )

    del raw[provider_id]
    if save_providers(raw):
        _logger.info("Provider '%s' deleted", provider_id)
        return {"status": "deleted", "provider_id": provider_id}
    else:
        raise HTTPException(status_code=500, detail="Failed to save providers")


@router.post("/{provider_id}/test")
async def test_provider(provider_id: str):
    """Test a provider connection by sending a simple prompt.

    Returns success/failure and response preview.
    """
    from icross.agents.llm import get_llm
    from icross.agents.llm.models import get_provider as _get_provider

    provider = _get_provider(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' not found")

    resolved_key = provider.resolve_api_key()
    if not resolved_key:
        raise HTTPException(
            status_code=400,
            detail=f"No API key for '{provider_id}'. "
            f"Set the {provider.api_key_env} environment variable or save an API key.",
        )

    resolved_model = provider.default_model
    if not resolved_model:
        raise HTTPException(
            status_code=400,
            detail=f"No default model configured for '{provider_id}'",
        )

    try:
        llm = get_llm(provider_id, model=resolved_model, temperature=0, max_tokens=50)
        result = llm.invoke("回复: ok")
        return {
            "success": True,
            "model": resolved_model,
            "response": result.content[:200] if result.content else "",
        }
    except Exception as e:
        _logger.warning("Provider test failed for '%s': %s", provider_id, e)
        return {
            "success": False,
            "model": resolved_model,
            "error": str(e),
        }
