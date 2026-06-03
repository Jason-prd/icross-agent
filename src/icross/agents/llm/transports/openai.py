"""OpenAI-compatible transport — creates ChatOpenAI instances.

Handles providers that use the OpenAI Chat Completions API format
(e.g. DeepSeek, OpenAI, Yi, Qwen, Moonshot, etc.).
"""

from typing import Any, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI

from icross.agents.llm.base import ProviderTransport
from icross.agents.llm.registry import register_transport


class DeepseekChatModel(ChatOpenAI):
    """ChatOpenAI subclass that preserves DeepSeek's ``reasoning_content`` field.

    DeepSeek's "thinking mode" returns a ``reasoning_content`` field on each
    assistant message.  Standard ``ChatOpenAI`` drops it during response parsing,
    causing ``400 The reasoning_content in the thinking mode must be passed back``
    on subsequent turns.

    This subclass:
    1. Captures ``reasoning_content`` from API responses and stores it in
       ``additional_kwargs`` of the ``AIMessage``.
    2. Injects ``reasoning_content`` back into the request payload when the
       stored message is sent in a follow-up conversation turn.
    """

    def _create_chat_result(
        self,
        response: dict | Any,
        generation_info: Optional[dict] = None,
    ):
        """Capture reasoning_content from each choice's message dict."""
        result = super()._create_chat_result(response, generation_info)

        response_dict = (
            response if isinstance(response, dict) else response.model_dump()
        )
        choices = response_dict.get("choices", [])

        for i, gen in enumerate(result.generations):
            if i < len(choices):
                msg_dict = choices[i].get("message", {})
                reasoning = msg_dict.get("reasoning_content")
                if reasoning and hasattr(gen.message, "additional_kwargs"):
                    gen.message.additional_kwargs["reasoning_content"] = reasoning

        return result

    def _get_request_payload(
        self,
        input_: Any,
        *,
        stop: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> dict:
        """Reinject reasoning_content into assistant message dicts."""
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)

        # _convert_message_to_dict drops reasoning_content from additional_kwargs.
        # Walk the original messages and their converted payload dicts in parallel
        # to reinject it.
        messages = self._convert_input(input_).to_messages()
        payload_msgs = payload.get("messages", [])

        pi = 0
        for msg in messages:
            if pi >= len(payload_msgs):
                break
            if isinstance(msg, AIMessage):
                # Advance to next assistant message in payload
                while pi < len(payload_msgs) and payload_msgs[pi].get("role") != "assistant":
                    pi += 1
                if pi < len(payload_msgs):
                    rc = msg.additional_kwargs.get("reasoning_content")
                    if rc:
                        payload_msgs[pi]["reasoning_content"] = rc
                    pi += 1

        return payload


class OpenAITransport(ProviderTransport):
    """Transport for 'openai' type providers.

    Creates ChatOpenAI (or DeepseekChatModel for DeepSeek) instances.
    """

    @property
    def transport_type(self) -> str:
        return "openai"

    def create_chat_model(
        self,
        model: str,
        api_key: str,
        base_url: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs,
    ) -> BaseChatModel:
        # Use DeepseekChatModel for deepseek provider to handle reasoning_content
        is_deepseek = "deepseek" in model.lower()
        return (DeepseekChatModel if is_deepseek else ChatOpenAI)(
            model=model,
            api_key=api_key,
            base_url=base_url or None,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )


# Auto-register on import
register_transport("openai", OpenAITransport)
