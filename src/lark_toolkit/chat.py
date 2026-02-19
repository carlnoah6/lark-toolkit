"""Chat management — create, lookup, list, and manage Lark chats."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .client import LarkClient


def get_chat_info(
    client: LarkClient,
    chat_id: str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """Get information about a chat.

    Args:
        client: LarkClient instance.
        chat_id: Chat ID (``oc_xxx``).
        token: Explicit token, defaults to tenant token.

    Returns:
        Chat info dict.
    """
    return client.api("GET", f"/im/v1/chats/{chat_id}", token=token or client.get_tenant_token())


def get_chat_members(
    client: LarkClient,
    chat_id: str,
    *,
    token: str | None = None,
) -> list[dict[str, Any]]:
    """Get all members of a chat (with automatic pagination).

    Args:
        client: LarkClient instance.
        chat_id: Chat ID (``oc_xxx``).
        token: Explicit token, defaults to tenant token.

    Returns:
        List of member dicts.
    """
    tk = token or client.get_tenant_token()
    members: list[dict[str, Any]] = []
    page_token = ""
    while True:
        url = f"/im/v1/chats/{chat_id}/members?page_size=100"
        if page_token:
            url += f"&page_token={page_token}"
        data = client.api("GET", url, token=tk)
        members.extend(data.get("items", []))
        if not data.get("has_more"):
            break
        page_token = data.get("page_token", "")
    return members


def list_chats(
    client: LarkClient,
    *,
    token: str | None = None,
) -> list[dict[str, Any]]:
    """List all chats the bot is in (with automatic pagination).

    Args:
        client: LarkClient instance.
        token: Explicit token, defaults to tenant token.

    Returns:
        List of chat dicts with ``chat_id``, ``name``, and ``user_count`` keys.
    """
    tk = token or client.get_tenant_token()
    chats: list[dict[str, Any]] = []
    page_token = ""
    while True:
        url = "/im/v1/chats?page_size=50"
        if page_token:
            url += f"&page_token={page_token}"
        data = client.api("GET", url, token=tk)
        items = data.get("items", [])
        for c in items:
            chats.append(
                {
                    "chat_id": c["chat_id"],
                    "name": c.get("name", "(unnamed)"),
                    "user_count": c.get("user_count", 0),
                }
            )
        if not data.get("has_more"):
            break
        page_token = data.get("page_token", "")
    return chats


def search_chats(
    client: LarkClient,
    query: str,
    *,
    token: str | None = None,
) -> list[dict[str, Any]]:
    """Search chats by name (case-insensitive substring match).

    Fetches the full chat list and filters locally.

    Args:
        client: LarkClient instance.
        query: Search string to match against chat names.
        token: Explicit token, defaults to tenant token.

    Returns:
        List of matching chat dicts.
    """
    all_chats = list_chats(client, token=token)
    q = query.lower()
    return [c for c in all_chats if q in c["name"].lower()]
