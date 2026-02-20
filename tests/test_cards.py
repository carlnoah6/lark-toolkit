"""Tests for card building utilities."""

from __future__ import annotations

from lark_toolkit.cards import (
    build_resolved_card,
    build_wait_card,
    truncate,
    wrap_card,
)


class TestTruncate:
    def test_short_text_unchanged(self) -> None:
        assert truncate("hello") == "hello"

    def test_long_text_truncated(self) -> None:
        text = "x" * 4000
        result = truncate(text)
        assert len(result) <= 3800
        assert result.endswith("... (truncated)")

    def test_custom_max_len(self) -> None:
        text = "x" * 200
        result = truncate(text, max_len=100)
        assert len(result) <= 100


class TestWrapCard:
    def test_basic_card_structure(self) -> None:
        elements = [{"tag": "markdown", "content": "Hello"}]
        card = wrap_card("Test Title", elements, template="blue")

        assert card["header"]["title"]["content"] == "Test Title"
        assert card["header"]["template"] == "blue"
        assert card["config"]["wide_screen_mode"] is True
        assert len(card["elements"]) == 1

    def test_card_with_timestamp(self) -> None:
        elements = [{"tag": "markdown", "content": "Hello"}]
        card = wrap_card("Title", elements, timestamp="Updated: 2026-01-01")

        # Last element should be the note with timestamp
        assert card["elements"][-1]["tag"] == "note"
        assert "Updated: 2026-01-01" in card["elements"][-1]["elements"][0]["content"]


class TestBuildWaitCard:
    def test_confirm_card(self) -> None:
        card = build_wait_card("task-1", "confirm", "Proceed?", options=["Yes", "No"])

        assert "task-1" in card["header"]["title"]["content"]
        assert card["header"]["template"] == "orange"

        # Should have markdown, hr, and action elements
        actions = [e for e in card["elements"] if e["tag"] == "action"]
        assert len(actions) == 1

        buttons = actions[0]["actions"]
        # 2 options + 1 cancel = 3 buttons
        assert len(buttons) == 3
        assert buttons[0]["text"]["content"] == "Yes"
        assert buttons[0]["type"] == "primary"
        assert buttons[1]["text"]["content"] == "No"
        assert buttons[1]["type"] == "default"
        assert buttons[2]["type"] == "danger"  # cancel button

    def test_discuss_card(self) -> None:
        card = build_wait_card("task-2", "discuss", "Let's talk")

        actions = [e for e in card["elements"] if e["tag"] == "action"]
        buttons = actions[0]["actions"]
        assert len(buttons) == 2  # confirm + cancel
        assert buttons[0]["value"]["response"] == "__discuss_confirmed__"

    def test_todo_card_with_guid(self) -> None:
        card = build_wait_card("task-3", "todo", "Do this", todo_guid="guid_xyz")

        md_elements = [e for e in card["elements"] if e.get("tag") == "markdown"]
        assert any("Todo created" in e["content"] for e in md_elements)

        actions = [e for e in card["elements"] if e["tag"] == "action"]
        buttons = actions[0]["actions"]
        assert buttons[0]["value"]["response"] == "__todo_manual_confirm__"


class TestBuildResolvedCard:
    def test_basic_resolved(self) -> None:
        card = build_resolved_card("task-1", "Approved")

        assert "task-1" in card["header"]["title"]["content"]
        assert card["header"]["template"] == "green"
        md = [e for e in card["elements"] if e.get("tag") == "markdown"]
        assert any("Approved" in e["content"] for e in md)

    def test_resolved_with_wait_time(self) -> None:
        card = build_resolved_card("task-1", "Done", waited_minutes=45)

        md = [e for e in card["elements"] if e.get("tag") == "markdown"]
        assert any("45min" in e["content"] for e in md)

    def test_resolved_with_hours(self) -> None:
        card = build_resolved_card("task-1", "Done", waited_minutes=120)

        md = [e for e in card["elements"] if e.get("tag") == "markdown"]
        assert any("2.0h" in e["content"] for e in md)
