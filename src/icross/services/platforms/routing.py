"""Delivery routing — ``"platform:chat_id"`` addressing.

Usage:
    target = DeliveryTarget.parse("feishu:oc_xxx")
    await notification_service.send(content, chat_id=target.chat_id, platform=target.platform)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Self

from icross.services.platforms import Platform

# Regex for validating delivery target strings
_TARGET_RE = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_-]*):(.+)$")


@dataclass
class DeliveryTarget:
    """A parsed delivery target: platform + chat_id.

    Attributes:
        platform: Platform name string (e.g. "feishu", "telegram").
        chat_id: Target chat/channel/group ID.
    """

    platform: str
    chat_id: str

    @classmethod
    def parse(cls, target: str) -> Self | None:
        """Parse a ``"platform:chat_id"`` string into a DeliveryTarget.

        Returns None if the string is not a valid delivery target.
        """
        m = _TARGET_RE.match(target.strip())
        if not m:
            return None
        return cls(platform=m.group(1), chat_id=m.group(2))

    @classmethod
    def make(cls, platform: str, chat_id: str) -> str:
        """Build a ``"platform:chat_id"`` string from parts."""
        return f"{platform}:{chat_id}"

    def is_valid(self) -> bool:
        """Check if the platform is known and chat_id is non-empty."""
        if not self.chat_id:
            return False
        try:
            Platform(self.platform)
            return True
        except ValueError:
            return False

    def resolve_to(self) -> tuple[str, str]:
        """Return ``(platform, chat_id)`` tuple for use with NotificationService."""
        return self.platform, self.chat_id

    def __str__(self) -> str:
        return f"{self.platform}:{self.chat_id}"
