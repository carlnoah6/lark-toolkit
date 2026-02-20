"""Messaging utilities — send text, cards, and images to Lark chats."""

from __future__ import annotations

import json
import mimetypes
import os
import time
from typing import TYPE_CHECKING, Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .types import LarkAPIError

if TYPE_CHECKING:
    from .client import LarkClient


def send_message(
    client: LarkClient,
    chat_id: str,
    text: str,
    *,
    msg_type: str = "text",
    token: str | None = None,
) -> dict[str, Any]:
    """Send a message to a Lark chat.

    Args:
        client: LarkClient instance.
        chat_id: Chat ID (``oc_xxx``).
        text: Message content. For ``msg_type="text"`` this is plain text;
              for ``msg_type="interactive"`` this is the card JSON string.
        msg_type: Message type (``text``, ``post``, ``interactive``).
        token: Explicit token, defaults to tenant token.

    Returns:
        API response data.
    """
    content = json.dumps({"text": text}) if msg_type == "text" else text

    return client.api(
        "POST",
        "/im/v1/messages?receive_id_type=chat_id",
        body={
            "receive_id": chat_id,
            "msg_type": msg_type,
            "content": content,
        },
        token=token or client.get_tenant_token(),
    )


def send_card(
    client: LarkClient,
    chat_id: str,
    card: dict[str, Any],
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """Send an interactive card message to a Lark chat.

    Args:
        client: LarkClient instance.
        chat_id: Chat ID (``oc_xxx``).
        card: Card dict (will be JSON-serialized as the ``content`` field).
        token: Explicit token, defaults to tenant token.

    Returns:
        API response data.
    """
    return send_message(
        client,
        chat_id,
        json.dumps(card, ensure_ascii=False),
        msg_type="interactive",
        token=token,
    )


def update_card(
    client: LarkClient,
    message_id: str,
    card: dict[str, Any],
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """Update (PATCH) an existing card message.

    Args:
        client: LarkClient instance.
        message_id: The message_id of the card to update.
        card: New card content dict.
        token: Explicit token, defaults to tenant token.

    Returns:
        API response data.
    """
    return client.api(
        "PATCH",
        f"/im/v1/messages/{message_id}",
        body={
            "msg_type": "interactive",
            "content": json.dumps(card, ensure_ascii=False),
        },
        token=token or client.get_tenant_token(),
    )


def upload_image(
    client: LarkClient,
    image_path: str,
    *,
    image_type: str = "message",
    token: str | None = None,
) -> str:
    """Upload an image to Lark and return the ``image_key``.

    Args:
        client: LarkClient instance.
        image_path: Local file path to the image (PNG/JPEG).
        image_type: ``"message"`` for chat images, ``"avatar"`` for avatars.
        token: Explicit token, defaults to tenant token.

    Returns:
        image_key string for use in messages/cards.
    """
    tk = token or client.get_tenant_token()
    url = f"{client.base_url}/im/v1/images"

    boundary = f"----LarkUpload{int(time.time() * 1000)}"
    body_parts: list[str] = []

    # image_type field
    body_parts.append(f"--{boundary}\r\n")
    body_parts.append('Content-Disposition: form-data; name="image_type"\r\n\r\n')
    body_parts.append(f"{image_type}\r\n")

    # image file
    filename = os.path.basename(image_path)
    mime = mimetypes.guess_type(image_path)[0] or "image/png"
    body_parts.append(f"--{boundary}\r\n")
    body_parts.append(f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n')
    body_parts.append(f"Content-Type: {mime}\r\n\r\n")

    pre_file = "".join(body_parts).encode("utf-8")
    with open(image_path, "rb") as f:
        file_data = f.read()
    post_file = f"\r\n--{boundary}--\r\n".encode()

    body_bytes = pre_file + file_data + post_file

    req = Request(url, data=body_bytes, method="POST")
    req.add_header("Authorization", f"Bearer {tk}")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")

    try:
        with urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, OSError) as exc:
        raise LarkAPIError(f"Image upload network error: {exc}") from exc

    if result.get("code", 0) != 0:
        raise LarkAPIError(
            f"Image upload failed: {result.get('msg', 'unknown')}",
            code=result.get("code"),
            response=result,
        )
    return result["data"]["image_key"]


def send_image(
    client: LarkClient,
    chat_id: str,
    image_key: str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """Send an image message to a chat.

    Args:
        client: LarkClient instance.
        chat_id: Chat ID (``oc_xxx``).
        image_key: Image key from :func:`upload_image`.
        token: Explicit token, defaults to tenant token.

    Returns:
        API response data.
    """
    return client.api(
        "POST",
        "/im/v1/messages?receive_id_type=chat_id",
        body={
            "receive_id": chat_id,
            "msg_type": "image",
            "content": json.dumps({"image_key": image_key}),
        },
        token=token or client.get_tenant_token(),
    )
