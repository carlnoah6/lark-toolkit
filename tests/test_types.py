"""Tests for shared types."""

from __future__ import annotations

import time

from lark_toolkit.types import CalendarEvent, LarkAPIError, TaskMember, TokenInfo


class TestLarkAPIError:
    def test_basic_error(self) -> None:
        err = LarkAPIError("test error")
        assert str(err) == "test error"
        assert err.code is None
        assert err.response == {}

    def test_error_with_code(self) -> None:
        err = LarkAPIError("bad request", code=40003, response={"msg": "invalid"})
        assert err.code == 40003
        assert err.response == {"msg": "invalid"}

    def test_error_is_exception(self) -> None:
        with __import__("pytest").raises(LarkAPIError):
            raise LarkAPIError("test")


class TestTokenInfo:
    def test_expired_token(self) -> None:
        token = TokenInfo(access_token="tok", expires_at=time.time() - 100)
        assert token.is_expired is True

    def test_valid_token(self) -> None:
        token = TokenInfo(access_token="tok", expires_at=time.time() + 3600)
        assert token.is_expired is False


class TestTaskMember:
    def test_to_dict(self) -> None:
        member = TaskMember(id="ou_123", type="user", role="assignee")
        assert member.to_dict() == {"id": "ou_123", "type": "user", "role": "assignee"}

    def test_default_values(self) -> None:
        member = TaskMember(id="ou_456")
        assert member.type == "user"
        assert member.role == "assignee"


class TestCalendarEvent:
    def test_defaults(self) -> None:
        event = CalendarEvent(summary="Meeting")
        assert event.summary == "Meeting"
        assert event.all_day is False
        assert event.start == ""
        assert event.recurrence == ""
