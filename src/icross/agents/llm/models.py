"""Provider data model + configuration loading.

Adapted from Hermes Agent's ProviderDef + HERMES_OVERLAYS pattern,
simplified for iCross's use case.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

_logger = logging.getLogger(__name__)

# Default path for provider definitions
_PROVIDERS_PATH = Path(__file__).parent.parent.parent.parent.parent / "data" / "providers.json"


@dataclass
class ProviderDef:
    """Provider definition — model-agnostic, transport-driven.

    Matches Hermes ProviderDef pattern but simplified for iCross.
    """

    id: str
    name: str
    transport: str  # "anthropic" | "openai"
    api_key_env: str  # primary env var for API key
    base_url: str = ""
    base_url_env: str = ""  # env var to override base_url
    default_model: str = ""
    api_key: str = ""  # user-saved API key (stored in providers.json)
    doc: str = ""
    context_length: int = 200000  # max context tokens for the model

    def resolve_api_key(self) -> str:
        """Resolve API key: saved key > env var > empty."""
        if self.api_key:
            return self.api_key
        return os.getenv(self.api_key_env, "")

    def resolve_base_url(self) -> str:
        """Resolve base URL, with env override support."""
        if self.base_url_env:
            env_url = os.getenv(self.base_url_env)
            if env_url:
                return env_url
        return self.base_url

    def to_api_dict(self, show_key: bool = False) -> Dict[str, Any]:
        """Convert to dict for API response, optionally masking the API key."""
        return {
            "id": self.id,
            "name": self.name,
            "transport": self.transport,
            "api_key_env": self.api_key_env,
            "base_url": self.base_url,
            "base_url_env": self.base_url_env,
            "default_model": self.default_model,
            "api_key": self.api_key if show_key else (
                self.api_key[:8] + "..." if len(self.api_key) > 12 else ""
            ),
            "has_api_key": bool(self.api_key or os.getenv(self.api_key_env)),
            "context_length": self.context_length,
            "doc": self.doc,
        }


# Map of known aliases (user-friendly short names → provider IDs)
ALIASES: Dict[str, str] = {
    "minimax": "minimax",
    "anthropic": "anthropic",
    "claude": "anthropic",
    "deepseek": "deepseek",
    "openai": "openai",
    "gpt": "openai",
    "yi": "yi",
    "moonshot": "moonshot",
    "kimi": "moonshot",
    "gemini": "gemini",
    "qwen": "qwen",
}

# Built-in defaults (used if providers.json doesn't exist)
_DEFAULT_PROVIDERS: Dict[str, Dict[str, Any]] = {
    "minimax": {
        "name": "MiniMax",
        "transport": "anthropic",
        "api_key_env": "MINIMAX_API_KEY",
        "base_url": "https://api.minimaxi.com/anthropic",
        "base_url_env": "MINIMAX_BASE_URL",
        "default_model": "MiniMax-M2.7",
        "doc": "MiniMax (Anthropic-compatible API)",
        "context_length": 200000,
    },
    "anthropic": {
        "name": "Anthropic",
        "transport": "anthropic",
        "api_key_env": "ANTHROPIC_API_KEY",
        "base_url": "https://api.anthropic.com",
        "base_url_env": "ANTHROPIC_BASE_URL",
        "default_model": "claude-sonnet-4-20250514",
        "doc": "Anthropic Claude",
        "context_length": 200000,
    },
    "deepseek": {
        "name": "DeepSeek",
        "transport": "openai",
        "api_key_env": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com/v1",
        "base_url_env": "DEEPSEEK_BASE_URL",
        "default_model": "deepseek-v4-flash",
        "doc": "DeepSeek (OpenAI-compatible API)",
        "context_length": 65536,
    },
    "openai": {
        "name": "OpenAI",
        "transport": "openai",
        "api_key_env": "OPENAI_API_KEY",
        "base_url": "https://api.openai.com/v1",
        "base_url_env": "OPENAI_BASE_URL",
        "default_model": "gpt-4o",
        "doc": "OpenAI GPT-4 / GPT-3.5",
        "context_length": 128000,
    },
}


def _ensure_providers_file() -> None:
    """Create default providers.json if it doesn't exist."""
    if _PROVIDERS_PATH.exists():
        return
    try:
        _PROVIDERS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_PROVIDERS_PATH, "w", encoding="utf-8") as f:
            json.dump(_DEFAULT_PROVIDERS, f, ensure_ascii=False, indent=2)
        _logger.info("Created default providers.json at %s", _PROVIDERS_PATH)
    except OSError as e:
        _logger.warning("Failed to create providers.json: %s", e)


def load_providers() -> Dict[str, ProviderDef]:
    """Load provider definitions from providers.json, merged with built-in defaults.

    Users can add/override providers in data/providers.json.
    """
    _ensure_providers_file()

    raw: Dict[str, Dict[str, Any]] = {}
    if _PROVIDERS_PATH.exists():
        try:
            with open(_PROVIDERS_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            _logger.warning("Failed to load providers.json: %s; using defaults", e)

    # Merge: built-in defaults overridden by user config
    merged = dict(_DEFAULT_PROVIDERS)
    merged.update(raw)

    providers: Dict[str, ProviderDef] = {}
    for pid, cfg in merged.items():
        providers[pid] = ProviderDef(
            id=pid,
            name=cfg.get("name", pid),
            transport=cfg.get("transport", "openai"),
            api_key_env=cfg.get("api_key_env", f"{pid.upper()}_API_KEY"),
            base_url=cfg.get("base_url", ""),
            base_url_env=cfg.get("base_url_env", ""),
            default_model=cfg.get("default_model", ""),
            api_key=cfg.get("api_key", ""),
            doc=cfg.get("doc", ""),
            context_length=cfg.get("context_length", 200000),
        )

    return providers


def get_provider(provider_id: str) -> Optional[ProviderDef]:
    """Resolve a provider by ID or alias, returning the ProviderDef or None."""
    providers = load_providers()

    # Direct match
    if provider_id in providers:
        return providers[provider_id]

    # Alias resolution
    resolved = ALIASES.get(provider_id.lower())
    if resolved and resolved in providers:
        return providers[resolved]

    return None


def save_providers(providers: Dict[str, Dict[str, Any]]) -> bool:
    """Save provider definitions to providers.json."""
    try:
        _PROVIDERS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_PROVIDERS_PATH, "w", encoding="utf-8") as f:
            json.dump(providers, f, ensure_ascii=False, indent=2)
        return True
    except OSError as e:
        _logger.error("Failed to save providers.json: %s", e)
        return False
