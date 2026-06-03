"""ProviderTransport ABC — adapted from Hermes Agent.

Each transport knows how to create a LangChain chat model for a specific
provider type (anthropic-compatible, OpenAI-compatible, etc).
"""

from abc import ABC, abstractmethod
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel


class ProviderTransport(ABC):
    """Base class for provider-specific LangChain model creation."""

    @property
    @abstractmethod
    def transport_type(self) -> str:
        """Transport identifier (e.g. 'anthropic', 'openai')."""
        ...

    @abstractmethod
    def create_chat_model(
        self,
        model: str,
        api_key: str,
        base_url: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs: Any,
    ) -> BaseChatModel:
        """Create a LangChain BaseChatModel for this provider.

        Args:
            model: Model name (provider-specific).
            api_key: API key for the provider.
            base_url: Base URL for the API endpoint.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.
            **kwargs: Additional provider-specific arguments.

        Returns:
            A configured BaseChatModel instance.
        """
        ...
