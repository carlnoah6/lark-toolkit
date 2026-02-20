"""OAuth handler — exchange authorization codes and handle card action callbacks.

Provides an HTTP server that handles:
1. OAuth GET ``/callback?code=xxx`` — exchange code for user_access_token
2. Card Action POST — process interactive card button clicks
3. URL Verification POST — respond to Lark webhook registration
"""

from __future__ import annotations

import contextlib
import http.server
import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

if TYPE_CHECKING:
    from .client import LarkClient


def exchange_code(client: LarkClient, code: str) -> tuple[dict[str, Any] | None, str | None]:
    """Exchange an OAuth authorization code for a user access token.

    Args:
        client: LarkClient instance.
        code: Authorization code from the OAuth redirect.

    Returns:
        Tuple of ``(token_data, error)``. On success, ``error`` is None.
        On failure, ``token_data`` is None and ``error`` contains the message.
    """
    tenant_token = client.get_tenant_token()

    data = json.dumps({"grant_type": "authorization_code", "code": code}).encode()
    req = Request(
        f"{client.base_url}/authen/v1/oidc/access_token",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {tenant_token}",
        },
        method="POST",
    )

    try:
        with urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            if result.get("code") == 0:
                return result.get("data"), None
            return None, f"API error: {result.get('msg', 'unknown')}"
    except HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode()}"
    except Exception as e:
        return None, str(e)


def refresh_user_token(client: LarkClient, refresh_token: str) -> tuple[dict[str, Any] | None, str | None]:
    """Refresh a user access token using a refresh token.

    Args:
        client: LarkClient instance.
        refresh_token: The refresh_token from a previous token exchange.

    Returns:
        Tuple of ``(token_data, error)``.
    """
    app_token = client.get_app_token()

    data = json.dumps({"grant_type": "refresh_token", "refresh_token": refresh_token}).encode()
    req = Request(
        f"{client.base_url}/authen/v1/oidc/refresh_access_token",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {app_token}",
        },
        method="POST",
    )

    try:
        with urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            if result.get("code") == 0:
                return result.get("data"), None
            return None, f"Refresh failed: {result.get('msg', 'unknown')}"
    except Exception as e:
        return None, str(e)


def save_user_token(token_data: dict[str, Any], token_file: str | Path) -> bool:
    """Save user token data to a JSON file.

    Args:
        token_data: Token response from :func:`exchange_code` or :func:`refresh_user_token`.
        token_file: Path to save the token JSON.

    Returns:
        True on success.
    """
    path = Path(token_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(token_data, f, indent=2, ensure_ascii=False)
    with contextlib.suppress(OSError):
        path.chmod(0o600)
    return True


class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for OAuth callbacks and card action webhooks.

    Attributes:
        client: LarkClient instance (set via class attribute before serving).
        token_file: Path to save OAuth tokens (set via class attribute).
        card_action_handler: Optional callback for card actions.
    """

    client: LarkClient
    token_file: str = ""
    card_action_handler: Callable[[dict[str, Any]], dict[str, Any]] | None = None

    def do_GET(self) -> None:
        """Handle OAuth redirect: ``GET /callback?code=xxx``."""
        import urllib.parse

        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)

        if "code" in query:
            code = query["code"][0]
            token_data, error = exchange_code(self.client, code)

            if token_data and self.token_file:
                save_user_token(token_data, self.token_file)
                self._html_response(200, "Authorization Successful", "Token saved. You can close this page.")
            elif error:
                self._html_response(400, "Authorization Failed", error)
            else:
                self._html_response(400, "Authorization Failed", "Unknown error")
            return

        self.send_error(404, "Not Found")

    def do_POST(self) -> None:
        """Handle POST: card actions and URL verification."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._json_response(400, {"error": "invalid json"})
            return

        # URL verification
        if data.get("type") == "url_verification":
            self._json_response(200, {"challenge": data.get("challenge", "")})
            return

        # Card action (v1 and v2 payload formats)
        event = data.get("event", data)
        action = event.get("action") or data.get("action")
        if action and isinstance(action, dict):
            action_value = action.get("value", {})
            # Inject open_message_id so handlers can update the card via API
            open_msg_id = (
                event.get("open_message_id")
                or data.get("open_message_id")
                or event.get("context", {}).get("open_message_id")
            )
            if open_msg_id:
                action_value["_open_message_id"] = open_msg_id
            # Inject open_chat_id
            open_chat_id = (
                event.get("open_chat_id") or data.get("open_chat_id") or event.get("context", {}).get("open_chat_id")
            )
            if open_chat_id:
                action_value["_open_chat_id"] = open_chat_id
            # Log full payload for debugging
            print(f"[oauth] card action keys: {list(data.keys())}, open_msg_id={open_msg_id}")
            if action_value.get("action") and self.card_action_handler:
                # Access via class to avoid descriptor protocol binding
                handler = type(self).card_action_handler
                result = handler(action_value)
                self._json_response(200, result)
                return

        self._json_response(200, {})

    def _json_response(self, code: int, body: dict[str, Any]) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def _html_response(self, code: int, title: str, message: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        html = (
            f"<!DOCTYPE html><html><head><meta charset='UTF-8'><title>{title}</title></head>"
            f"<body><h1>{title}</h1><p>{message}</p></body></html>"
        )
        self.wfile.write(html.encode())

    def log_message(self, format: str, *args: Any) -> None:
        pass  # Suppress default access logs


def run_oauth_server(
    client: LarkClient,
    *,
    host: str = "127.0.0.1",
    port: int = 8190,
    token_file: str = "",
    card_action_handler: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    background: bool = False,
) -> http.server.HTTPServer:
    """Start the OAuth/card-action callback HTTP server.

    Args:
        client: LarkClient instance for token management.
        host: Bind address.
        port: Bind port.
        token_file: Path to save OAuth tokens.
        card_action_handler: Optional callback ``(action_value) -> response_dict``
            for card button clicks.
        background: If True, run the server in a daemon thread.

    Returns:
        The HTTPServer instance.
    """
    OAuthCallbackHandler.client = client
    OAuthCallbackHandler.token_file = token_file
    OAuthCallbackHandler.card_action_handler = card_action_handler

    server = http.server.HTTPServer((host, port), OAuthCallbackHandler)

    if background:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
    else:
        server.serve_forever()

    return server
