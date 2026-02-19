"""Card building utilities — streaming cards (CardKit) and interactive cards."""

from __future__ import annotations

import json
import sys
import time
from typing import TYPE_CHECKING, Any
from urllib.request import Request, urlopen

if TYPE_CHECKING:
    from .client import LarkClient

# ── Card builder helpers ─────────────────────────────────────────

MAX_CONTENT_LEN = 3800


def truncate(text: str, max_len: int = MAX_CONTENT_LEN) -> str:
    """Truncate text to fit within card content limits."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 20] + "\n\n... (truncated)"


def wrap_card(
    title: str,
    elements: list[dict[str, Any]],
    *,
    template: str = "blue",
    timestamp: str | None = None,
    wide_screen: bool = True,
) -> dict[str, Any]:
    """Wrap card elements with a standard header and optional timestamp footer.

    Args:
        title: Card header title.
        elements: List of card element dicts.
        template: Header color template (blue, green, red, orange, grey, etc.).
        timestamp: Optional timestamp string for the footer note.
        wide_screen: Enable wide-screen mode.

    Returns:
        Complete card dict ready for sending.
    """
    all_elements = list(elements)

    if timestamp:
        all_elements.append(
            {
                "tag": "note",
                "elements": [{"tag": "plain_text", "content": timestamp}],
            }
        )

    return {
        "config": {"wide_screen_mode": wide_screen},
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "template": template,
        },
        "elements": all_elements,
    }


def build_wait_card(
    task_id: str,
    wait_type: str,
    prompt: str,
    *,
    options: list[str] | None = None,
    todo_guid: str | None = None,
) -> dict[str, Any]:
    """Build an interactive card for a waiting/confirmation state.

    Args:
        task_id: Task identifier displayed in the card.
        wait_type: One of ``"confirm"``, ``"discuss"``, ``"todo"``.
        prompt: The question or instruction shown to the user.
        options: List of option strings (for ``confirm`` type).
        todo_guid: Lark todo GUID (for ``todo`` type, informational).

    Returns:
        Lark interactive card dict.
    """
    type_labels = {"confirm": "Awaiting Confirmation", "discuss": "Discussion Needed", "todo": "Awaiting Action"}
    type_icons = {"confirm": "?", "discuss": ">>", "todo": "[]"}

    header_text = f"{type_icons.get(wait_type, '||')} Task {task_id} — {type_labels.get(wait_type, 'Awaiting Input')}"

    elements: list[dict[str, Any]] = [{"tag": "markdown", "content": prompt}]

    if wait_type == "todo" and todo_guid:
        elements.append(
            {
                "tag": "markdown",
                "content": "Todo created — mark it complete in Lark to continue automatically.",
            }
        )

    elements.append({"tag": "hr"})

    actions: list[dict[str, Any]] = []

    if wait_type == "confirm" and options:
        for i, opt in enumerate(options):
            actions.append(
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": opt},
                    "type": "primary" if i == 0 else "default",
                    "value": {"action": "task_wait_respond", "task_id": task_id, "response": opt},
                }
            )
    elif wait_type == "discuss":
        actions.append(
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "Confirm & Continue"},
                "type": "primary",
                "value": {"action": "task_wait_respond", "task_id": task_id, "response": "__discuss_confirmed__"},
            }
        )
    elif wait_type == "todo":
        actions.append(
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "I've completed it"},
                "type": "primary",
                "value": {"action": "task_wait_respond", "task_id": task_id, "response": "__todo_manual_confirm__"},
            }
        )

    # Always add cancel button
    actions.append(
        {
            "tag": "button",
            "text": {"tag": "plain_text", "content": "Cancel Task"},
            "type": "danger",
            "value": {"action": "task_wait_cancel", "task_id": task_id},
        }
    )

    if actions:
        elements.append({"tag": "action", "actions": actions})

    return wrap_card(header_text, elements, template="orange")


def build_resolved_card(
    task_id: str,
    response: str,
    *,
    waited_minutes: float = 0,
) -> dict[str, Any]:
    """Build a card showing a resolved/completed wait state.

    Args:
        task_id: Task identifier.
        response: The response text that resolved the wait.
        waited_minutes: How long the task waited, in minutes.

    Returns:
        Lark card dict.
    """
    waited_str = ""
    if waited_minutes > 0:
        waited_str = f"{waited_minutes:.0f}min" if waited_minutes < 60 else f"{waited_minutes / 60:.1f}h"

    elements: list[dict[str, Any]] = [
        {"tag": "markdown", "content": f"Response: **{response}**"},
    ]
    if waited_str:
        elements.append({"tag": "markdown", "content": f"Wait time: {waited_str}"})

    return wrap_card(f"Task {task_id} Resumed", elements, template="green")


# ── Streaming card (CardKit) ────────────────────────────────────


def _log(msg: str) -> None:
    print(f"[streaming-card] {msg}", file=sys.stderr, flush=True)


class StreamingCard:
    """A CardKit-based streaming card that can be updated in real-time.

    Args:
        client: LarkClient instance for token management.
        chat_id: Target chat for the card.
    """

    def __init__(self, client: LarkClient, chat_id: str) -> None:
        self.client = client
        self.chat_id = chat_id
        self.card_id: str | None = None
        self.message_id: str | None = None
        self.seq = 0
        self.current_text = ""
        self.alive = False

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.client.get_tenant_token()}",
            "Content-Type": "application/json",
        }

    def create(self) -> bool:
        """Create the streaming card and send it to the chat.

        Returns:
            True if card was created and sent successfully.
        """
        card_json = {
            "schema": "2.0",
            "config": {"wide_screen_mode": True, "streaming_mode": True},
            "body": {
                "elements": [
                    {"tag": "markdown", "content": "Thinking...", "element_id": "content"},
                    {"tag": "markdown", "content": " ", "element_id": "status"},
                ]
            },
        }
        try:
            cardkit_url = f"{self.client.base_url}/cardkit/v1/cards"
            req = Request(
                cardkit_url,
                data=json.dumps({"type": "card_json", "data": json.dumps(card_json)}).encode(),
                headers=self._headers(),
                method="POST",
            )
            r = json.loads(urlopen(req, timeout=10).read())
            if r.get("code") != 0:
                _log(f"cardkit.create failed: {r}")
                return False
            self.card_id = r["data"]["card_id"]

            im_url = f"{self.client.base_url}/im/v1/messages?receive_id_type=chat_id"
            req2 = Request(
                im_url,
                data=json.dumps(
                    {
                        "receive_id": self.chat_id,
                        "msg_type": "interactive",
                        "content": json.dumps({"type": "card", "data": {"card_id": self.card_id}}),
                    }
                ).encode(),
                headers=self._headers(),
                method="POST",
            )
            r2 = json.loads(urlopen(req2, timeout=10).read())
            if r2.get("code") != 0:
                _log(f"im.send failed: {r2}")
                return False
            self.message_id = r2.get("data", {}).get("message_id", "")
            self.current_text = "Thinking..."
            self.alive = True
            _log(f"Card created: {self.card_id}")
            return True
        except Exception as e:
            _log(f"Create failed: {e}")
            return False

    def update(self, text: str) -> bool:
        """Update the main content element of the streaming card.

        Args:
            text: New markdown content.

        Returns:
            True on success.
        """
        if not self.alive or text == self.current_text:
            return True
        text = truncate(text)
        self.current_text = text
        self.seq += 1
        try:
            url = f"{self.client.base_url}/cardkit/v1/cards/{self.card_id}/elements/content/content"
            req = Request(
                url,
                data=json.dumps({"content": text or " ", "sequence": self.seq}).encode(),
                headers=self._headers(),
                method="PUT",
            )
            r = json.loads(urlopen(req, timeout=10).read())
            if r.get("code") == 300309:
                _log("Session expired (300309)")
                self.alive = False
                return False
            return r.get("code") == 0
        except Exception as e:
            _log(f"Update failed: {e}")
            return False

    def update_status(self, status: str) -> None:
        """Update the status element (small text below main content).

        Args:
            status: Status markdown string.
        """
        if not self.alive:
            return
        self.seq += 1
        try:
            url = f"{self.client.base_url}/cardkit/v1/cards/{self.card_id}/elements/status/content"
            req = Request(
                url,
                data=json.dumps({"content": status or " ", "sequence": self.seq}).encode(),
                headers=self._headers(),
                method="PUT",
            )
            urlopen(req, timeout=10)
        except Exception:
            pass

    def close(self, final_text: str = "") -> None:
        """Close the streaming card with final content and disable streaming mode.

        Args:
            final_text: Final markdown content. Defaults to current text.
        """
        if not self.alive:
            return
        text = truncate(final_text or self.current_text)
        try:
            self.seq += 1
            url = f"{self.client.base_url}/cardkit/v1/cards/{self.card_id}/elements/content/content"
            req = Request(
                url,
                data=json.dumps({"content": text or " ", "sequence": self.seq}).encode(),
                headers=self._headers(),
                method="PUT",
            )
            urlopen(req, timeout=10)

            self.seq += 1
            url = f"{self.client.base_url}/cardkit/v1/cards/{self.card_id}/elements/status/content"
            req = Request(
                url,
                data=json.dumps({"content": " ", "sequence": self.seq}).encode(),
                headers=self._headers(),
                method="PUT",
            )
            urlopen(req, timeout=10)

            self.seq += 1
            url = f"{self.client.base_url}/cardkit/v1/cards/{self.card_id}/settings"
            req = Request(
                url,
                data=json.dumps({"settings": json.dumps({"streaming_mode": False}), "sequence": self.seq}).encode(),
                headers=self._headers(),
                method="PUT",
            )
            urlopen(req, timeout=10)

            _log(f"Card closed: {self.card_id}")
        except Exception as e:
            _log(f"Close failed: {e}")
        self.alive = False


# ── Text stream bridge ──────────────────────────────────────────


def stream_to_card(
    client: LarkClient,
    chat_id: str,
    text_iterator: Any,
    *,
    update_interval: float = 0.8,
    timeout: float = 900,
) -> None:
    """Stream text chunks from an iterator into a Lark streaming card.

    This is a generic replacement for the OpenClaw-specific streaming bridge.
    It accepts any iterable that yields ``(text, tool_status)`` tuples.

    Args:
        client: LarkClient instance.
        chat_id: Target chat ID.
        text_iterator: Iterable yielding ``(text: str, tool_status: str | None)``
            tuples. When the iterator is exhausted the card is closed.
        update_interval: Minimum seconds between card updates.
        timeout: Maximum total time in seconds.
    """
    card = StreamingCard(client, chat_id)
    if not card.create():
        _log("Failed to create card")
        return

    start = time.time()
    accumulated: list[str] = []
    last_update = 0.0

    try:
        for text_chunk, tool_status in text_iterator:
            if time.time() - start > timeout:
                break

            if text_chunk:
                accumulated.append(text_chunk)

            now = time.time()
            if now - last_update >= update_interval:
                if accumulated:
                    card.update("\n\n".join(accumulated))
                if tool_status:
                    card.update_status(tool_status)
                last_update = now
    except Exception as e:
        _log(f"Stream error: {e}")

    final = "\n\n".join(accumulated) if accumulated else "Done"
    card.close(final)
