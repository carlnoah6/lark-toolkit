"""Shared types and exceptions for lark_toolkit."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class LarkAPIError(Exception):
    """Raised when a Lark API call fails."""

    def __init__(self, message: str, *, code: int | None = None, response: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.response = response or {}


@dataclass
class TokenInfo:
    """Cached token with expiry tracking."""

    access_token: str
    expires_at: float
    token_type: str = "tenant"

    @property
    def is_expired(self) -> bool:
        """Check if the token has expired (with 5-minute buffer)."""
        import time

        return time.time() >= self.expires_at


@dataclass
class CalendarEvent:
    """A calendar event."""

    summary: str
    all_day: bool = False
    start: str = ""
    end: str = ""
    start_dt: datetime | None = None
    end_dt: datetime | None = None
    description: str = ""
    recurrence: str = ""


@dataclass
class TaskMember:
    """A task member (assignee or follower)."""

    id: str
    type: str = "user"
    role: str = "assignee"

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "type": self.type, "role": self.role}


@dataclass
class CardElement:
    """A Lark card element."""

    tag: str
    content: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"tag": self.tag}
        if self.content:
            result["content"] = self.content
        result.update(self.extra)
        return result
