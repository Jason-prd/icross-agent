"""LLM Factory — re-exports from the new multi-model llm package.

Kept for backward compatibility. All code should eventually import from
icross.agents.llm directly.
"""

from icross.agents.llm import (  # noqa: F401
    LLMType,
    create_anthropic,
    create_deepseek,
    create_llm,
    create_minimax,
)
