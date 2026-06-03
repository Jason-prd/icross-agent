"""Anthropic-compatible transport — creates ChatAnthropic instances.

Handles providers that use the Anthropic Messages API format (e.g. MiniMax).
"""

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel

from icross.agents.llm.base import ProviderTransport
from icross.agents.llm.registry import register_transport


class AnthropicTransport(ProviderTransport):
    """Transport for 'anthropic' type providers.

    Creates ChatAnthropic instances with provider-specific configuration.
    """

    @property
    def transport_type(self) -> str:
        return "anthropic"

    def create_chat_model(
        self,
        model: str,
        api_key: str,
        base_url: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs,
    ) -> BaseChatModel:
        return ChatAnthropic(
            anthropic_api_key=api_key,
            model=model,
            base_url=base_url or None,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )


# Auto-register on import
register_transport("anthropic", AnthropicTransport)
