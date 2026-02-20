"""Tests for messaging functions."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from lark_toolkit import LarkClient
from lark_toolkit.messaging import send_card, send_image, send_message


class TestSendMessage:
    """Test send_message function."""

    def test_send_text_message(self) -> None:
        client = MagicMock(spec=LarkClient)
        client.get_tenant_token.return_value = "tok"
        client.api.return_value = {"message_id": "msg_001"}

        result = send_message(client, "oc_abc", "Hello!")

        client.api.assert_called_once_with(
            "POST",
            "/im/v1/messages?receive_id_type=chat_id",
            body={
                "receive_id": "oc_abc",
                "msg_type": "text",
                "content": json.dumps({"text": "Hello!"}),
            },
            token="tok",
        )
        assert result == {"message_id": "msg_001"}

    def test_send_interactive_message(self) -> None:
        client = MagicMock(spec=LarkClient)
        client.get_tenant_token.return_value = "tok"
        client.api.return_value = {}

        card_json = '{"header": {}}'
        send_message(client, "oc_abc", card_json, msg_type="interactive")

        call_body = client.api.call_args[1]["body"]
        assert call_body["msg_type"] == "interactive"
        assert call_body["content"] == card_json

    def test_send_card(self) -> None:
        client = MagicMock(spec=LarkClient)
        client.get_tenant_token.return_value = "tok"
        client.api.return_value = {}

        card = {"header": {"title": "test"}, "elements": []}
        send_card(client, "oc_abc", card)

        call_body = client.api.call_args[1]["body"]
        assert call_body["msg_type"] == "interactive"
        assert json.loads(call_body["content"]) == card

    def test_send_image(self) -> None:
        client = MagicMock(spec=LarkClient)
        client.get_tenant_token.return_value = "tok"
        client.api.return_value = {"message_id": "msg_002"}

        send_image(client, "oc_abc", "img_key_123")

        call_body = client.api.call_args[1]["body"]
        assert call_body["msg_type"] == "image"
        assert json.loads(call_body["content"]) == {"image_key": "img_key_123"}
