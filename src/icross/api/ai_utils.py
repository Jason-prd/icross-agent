"""Shared AI utilities for cross-module AI feature routing.

Provides:
- get_ai_llm(feature_key, **overrides) — model routing by feature
- get_ai_llm_config() / update_ai_llm_config() — configuration management
- _extract_json() — JSON extraction from LLM responses
- _search_rules() — Ozon knowledge base RAG lookup
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "data" / "ai_model_config.json"

# ── Configuration management ─────────────────────────────────────


def _load_ai_model_config() -> dict[str, Any]:
    """Load AI model config from JSON file, returns default config on failure."""
    if not _CONFIG_PATH.exists():
        _logger.warning("ai_model_config.json not found, using defaults")
        return _default_config()

    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        _logger.warning("Failed to load ai_model_config.json: %s; using defaults", e)
        return _default_config()


def _default_config() -> dict[str, Any]:
    """Return hardcoded default configuration."""
    return {
        "tiers": {
            "fast": {"provider": "deepseek", "model": "deepseek-v4-flash", "temperature": 0.3, "max_tokens": 1024},
            "default": {"provider": "deepseek", "model": "deepseek-v4-flash", "temperature": 0.3, "max_tokens": 2048},
            "quality": {"provider": "deepseek", "model": "deepseek-v4-flash", "temperature": 0.3, "max_tokens": 4096},
            "embedding": {"provider": "minimax", "model": "embo-01", "temperature": 0, "max_tokens": 0},
        },
        "features": {},
    }


def save_ai_model_config(config: dict[str, Any]) -> bool:
    """Save AI model config to JSON file."""
    try:
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except OSError as e:
        _logger.error("Failed to save ai_model_config.json: %s", e)
        return False


def get_ai_llm_config() -> dict[str, Any]:
    """Public API: get full AI model configuration."""
    return _load_ai_model_config()


def update_ai_llm_config(config: dict[str, Any]) -> bool:
    """Public API: save full AI model configuration.

    The caller should send the complete config object (tiers + features).
    Partial updates are merged server-side if missing keys.
    """
    current = _load_ai_model_config()

    # Merge: keep existing keys not present in update
    if "tiers" in config:
        for tid, tval in config["tiers"].items():
            current.setdefault("tiers", {})[tid] = tval
    if "features" in config:
        for fid, fval in config["features"].items():
            current.setdefault("features", {})[fid] = fval

    return save_ai_model_config(current)


# ── Model routing ────────────────────────────────────────────────


def get_ai_llm(feature_key: str, **overrides: Any):
    """Resolve feature_key → tier → provider/model/temperature → get_llm().

    Args:
        feature_key: Dot-separated feature identifier (e.g. "product.title.optimize").
        **overrides: Per-call overrides for provider, model, temperature, max_tokens.

    Returns:
        A configured LangChain chat model (BaseChatModel).

    Resolution order:
        1. Look up feature_key in features config, get tier assignment.
        2. Look up tier in tiers config, get provider/model/temperature/max_tokens.
        3. Feature-level overrides (temperature, max_tokens) override tier defaults.
        4. Per-call **overrides have highest priority.
    """
    from icross.agents.llm import get_llm

    config = _load_ai_model_config()
    feature_cfg = config.get("features", {}).get(feature_key, {})
    tier_id = feature_cfg.get("tier") or "default"
    tier_cfg = config.get("tiers", {}).get(tier_id, config["tiers"]["default"])

    provider = overrides.pop("provider", None) or tier_cfg["provider"]
    model = overrides.pop("model", None) or tier_cfg.get("model")
    temperature = overrides.pop("temperature", None) or feature_cfg.get("temperature") or tier_cfg.get("temperature", 0.3)
    max_tokens = overrides.pop("max_tokens", None) or feature_cfg.get("max_tokens") or tier_cfg.get("max_tokens", 2048)

    return get_llm(
        provider,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        **overrides,
    )


# ── JSON extraction (from ai_product.py) ─────────────────────────


def _extract_json(text: str) -> tuple[str | None, str | None]:
    """Extract JSON object/array from LLM response (strip markdown).

    Returns:
        (json_str, raw_text) — json_str is the extracted JSON or None,
        raw_text is the cleaned text for fallback display.
    """
    raw = text.strip()

    # Strip markdown code blocks
    text = raw
    for marker in ("```json", "```"):
        if marker in text:
            text = text[text.find(marker) + len(marker):]
            if "```" in text:
                text = text[:text.rfind("```")]
            text = text.strip()
            break

    # Fast path: direct JSON parse
    try:
        json.loads(text)
        return text, raw
    except json.JSONDecodeError:
        pass

    # Brace-counting: find outermost { ... } or [ ... ]
    result = _extract_json_balanced(text)
    if result:
        return result, raw

    # Regex fallback: find any { ... } that parses as JSON
    for match in re.finditer(r"\{[^{}]*\}", text):
        candidate = match.group()
        try:
            json.loads(candidate)
            return candidate, raw
        except json.JSONDecodeError:
            continue

    return None, raw


def _extract_json_balanced(text: str) -> str | None:
    """Find outermost balanced JSON object or array."""
    for open_ch, close_ch in [("{", "}"), ("[", "]")]:
        start = text.find(open_ch)
        if start < 0:
            continue
        depth = 0
        in_str = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if ch == "\\":
                    i += 1  # skip escaped char
                    continue
                if ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
                continue
            if ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    candidate = text[start:i + 1]
                    try:
                        json.loads(candidate)
                        return candidate
                    except json.JSONDecodeError:
                        break
    return None


# ── Ozon rule search (from ai_product.py) ────────────────────────


def _search_rules(query: str, limit: int = 5) -> str:
    """Search Ozon rules knowledge base for relevant context.

    Args:
        query: Search query string.
        limit: Max number of results to include.

    Returns:
        Concatenated rule snippets, or empty string if KB unavailable.
    """
    try:
        from icross.services.ozon_rules import OzonRuleKB

        kb = OzonRuleKB()
        results = kb.search(query, limit=limit)
        if not results:
            return ""
        parts = []
        for r in results:
            title = r.get("title", "")
            content = r.get("content", "")[:800]
            parts.append(f"**{title}**\n{content}")
        return "\n\n---\n\n".join(parts)
    except Exception:
        _logger.warning("OzonRuleKB search failed", exc_info=True)
        return ""
