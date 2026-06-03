"""Session memory management for JSON file storage."""

import asyncio
from typing import Any

from icross.core.storage.ozon_data import SessionStorage


class SessionMemoryManager:
    """Manager for session message persistence in PostgreSQL.

    This handles our custom message history storage. LangGraph's checkpointer
    (AsyncPostgresSaver) is managed separately at the agent level.
    """

    def __init__(self, storage: SessionStorage | None = None):
        """Initialize the session memory manager.

        Args:
            storage: Storage for message persistence. If None, creates SessionStorage.
        """
        self.storage = storage or SessionStorage()
        self._pending_sessions: set[str] = set()

    async def ensure_session(self, session_id: str) -> None:
        """Ensure a session exists in storage."""
        await self.storage.ensure_session(session_id)

    def get_config(self, session_id: str, **kwargs: Any) -> dict[str, Any]:
        """Get the config dict for a session.

        Args:
            session_id: Unique session identifier.
            **kwargs: Additional config parameters.

        Returns:
            Config dict for use with agent.astream()/ainvoke().
        """
        config = {"configurable": {"thread_id": session_id, **kwargs}}
        return config

    async def save_message_async(self, session_id: str, msg_dict: dict) -> None:
        """Save a message to PostgreSQL storage (async version)."""
        await self.storage.ensure_session(session_id)
        await self.storage.save_message(
            session_id=session_id,
            message_type=msg_dict.get("type", "unknown"),
            content=msg_dict.get("content", ""),
            tool_name=msg_dict.get("name"),
            tool_call_id=msg_dict.get("tool_call_id"),
        )

    def save_message(self, session_id: str, msg_dict: dict) -> None:
        """Sync wrapper - prefer save_message_async when in async context."""
        try:
            loop = asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, self.save_message_async(session_id, msg_dict))
                return future.result()
        except RuntimeError:
            asyncio.get_event_loop().run_until_complete(self.save_message_async(session_id, msg_dict))

    async def get_messages_async(self, session_id: str) -> list[dict[str, Any]]:
        """Get all messages for a session (async version)."""
        return await self.storage.get_messages(session_id)

    def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        """Sync wrapper for get_messages."""
        try:
            loop = asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, self.get_messages_async(session_id))
                return future.result()
        except RuntimeError:
            return asyncio.get_event_loop().run_until_complete(self.get_messages_async(session_id))

    async def list_sessions_async(self) -> list[dict[str, Any]]:
        """List all sessions (async version)."""
        return await self.storage.list_sessions()

    def list_sessions(self) -> list[dict[str, Any]]:
        """Sync wrapper for list_sessions."""
        try:
            loop = asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, self.list_sessions_async())
                return future.result()
        except RuntimeError:
            return asyncio.get_event_loop().run_until_complete(self.list_sessions_async())

    async def delete_session_async(self, session_id: str) -> None:
        """Delete a session and all its messages."""
        await self.storage.delete_session(session_id)

    def delete_session(self, session_id: str) -> None:
        """Sync wrapper for delete_session."""
        try:
            loop = asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, self.delete_session_async(session_id))
                return future.result()
        except RuntimeError:
            asyncio.get_event_loop().run_until_complete(self.delete_session_async(session_id))

    async def search_messages_async(self, keyword: str) -> list[dict[str, Any]]:
        """Search messages containing the keyword."""
        return await self.storage.search_messages(keyword)

    def search_messages(self, keyword: str) -> list[dict[str, Any]]:
        """Sync wrapper for search_messages."""
        try:
            loop = asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, self.search_messages_async(keyword))
                return future.result()
        except RuntimeError:
            return asyncio.get_event_loop().run_until_complete(self.search_messages_async(keyword))

    async def update_session_title_async(self, session_id: str, title: str) -> None:
        """Update session title."""
        await self.storage.update_session_title(session_id, title)

    def update_session_title(self, session_id: str, title: str) -> None:
        """Sync wrapper for update_session_title."""
        try:
            loop = asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, self.update_session_title_async(session_id, title))
                return future.result()
        except RuntimeError:
            asyncio.get_event_loop().run_until_complete(self.update_session_title_async(session_id, title))

    def clear_session(self, session_id: str) -> None:
        """Clear a session's checkpoint history."""
        self.delete_session(session_id)