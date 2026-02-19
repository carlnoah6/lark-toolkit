"""LarkClient — central class for Lark/Feishu API access.

Manages token lifecycle (tenant, user, app) and provides a generic API call method.
All credentials come from environment variables — no hardcoded secrets.

Environment variables:
    LARK_APP_ID       (required) — Lark app ID
    LARK_APP_SECRET   (required) — Lark app secret
    LARK_BASE_URL     (optional) — API base URL, default https://open.larksuite.com/open-apis
    LARK_USER_TOKEN_FILE (optional) — path to user token JSON file
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .types import LarkAPIError, TokenInfo

DEFAULT_BASE_URL = "https://open.larksuite.com/open-apis"


class LarkClient:
    """Central client for Lark API operations.

    Usage::

        client = LarkClient()  # reads LARK_APP_ID / LARK_APP_SECRET from env
        client.send_message(chat_id, "Hello!")
    """

    def __init__(
        self,
        *,
        app_id: str | None = None,
        app_secret: str | None = None,
        base_url: str | None = None,
        user_token_file: str | None = None,
    ) -> None:
        self.app_id = app_id or os.environ.get("LARK_APP_ID", "")
        self.app_secret = app_secret or os.environ.get("LARK_APP_SECRET", "")
        self.base_url = (base_url or os.environ.get("LARK_BASE_URL", "")).rstrip("/") or DEFAULT_BASE_URL
        self._user_token_file = user_token_file or os.environ.get("LARK_USER_TOKEN_FILE", "")
        self._tenant_token: TokenInfo | None = None

    # ── Token management ─────────────────────────────────────────

    def get_tenant_token(self, *, force_refresh: bool = False) -> str:
        """Get a tenant_access_token (app-level), with automatic caching.

        The token is cached and reused until 5 minutes before expiry.
        """
        if not force_refresh and self._tenant_token and not self._tenant_token.is_expired:
            return self._tenant_token.access_token

        if not self.app_id or not self.app_secret:
            raise LarkAPIError("LARK_APP_ID and LARK_APP_SECRET are required")

        data = self._http_json(
            "POST",
            f"{self.base_url}/auth/v3/tenant_access_token/internal",
            body={"app_id": self.app_id, "app_secret": self.app_secret},
        )
        token = data.get("tenant_access_token")
        if not token:
            raise LarkAPIError(f"Failed to get tenant_access_token: {data}")

        expire = data.get("expire", 7200)
        self._tenant_token = TokenInfo(
            access_token=token,
            expires_at=time.time() + expire - 300,
            token_type="tenant",
        )
        return token

    def get_user_token(self) -> str:
        """Read the user_access_token from the local token file.

        The token file is expected to be maintained by an external refresh process
        (e.g. the OAuth handler or a cron job).
        """
        token_path = Path(self._user_token_file) if self._user_token_file else None
        if not token_path or not token_path.exists():
            raise FileNotFoundError(
                f"User token file not found: {token_path}. "
                f"Set LARK_USER_TOKEN_FILE or pass user_token_file to LarkClient."
            )

        with open(token_path) as f:
            data = json.load(f)

        token = data.get("access_token")
        if not token:
            raise LarkAPIError(f"No access_token in {token_path}")

        expires_at = data.get("expires_at")
        if expires_at and time.time() > expires_at:
            raise LarkAPIError(f"User token expired at {time.ctime(expires_at)}.")

        return token

    def get_app_token(self) -> str:
        """Get an app_access_token (used for OAuth refresh flows)."""
        if not self.app_id or not self.app_secret:
            raise LarkAPIError("LARK_APP_ID and LARK_APP_SECRET are required")

        data = self._http_json(
            "POST",
            f"{self.base_url}/auth/v3/app_access_token/internal",
            body={"app_id": self.app_id, "app_secret": self.app_secret},
        )
        token = data.get("app_access_token")
        if not token:
            raise LarkAPIError(f"Failed to get app_access_token: {data}")
        return token

    # ── Generic API call ─────────────────────────────────────────

    def api(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        token: str | None = None,
        token_type: str = "tenant",
        timeout: int = 15,
        raw: bool = False,
    ) -> dict[str, Any]:
        """Make a Lark API call.

        Args:
            method: HTTP method (GET, POST, PUT, PATCH, DELETE).
            path: API path starting with ``/`` (e.g. ``/im/v1/chats``),
                  or a full URL.
            body: Request body dict (auto-serialized to JSON).
            token: Explicit token. If *None*, auto-fetched via *token_type*.
            token_type: ``"tenant"`` (default) or ``"user"``.
            timeout: Request timeout in seconds.
            raw: If *True*, return the full response; otherwise check the
                 ``code`` field and return the ``data`` sub-dict.

        Returns:
            API response dict.

        Raises:
            LarkAPIError: On non-zero ``code`` or HTTP errors.
        """
        if token is None:
            token = self.get_user_token() if token_type == "user" else self.get_tenant_token()

        url = path if path.startswith("http") else f"{self.base_url}{path}"
        resp = self._http_json(method, url, body=body, token=token, timeout=timeout)

        if raw:
            return resp

        code = resp.get("code")
        if code is not None and code != 0:
            raise LarkAPIError(
                f"Lark API error: code={code} msg={resp.get('msg', 'unknown')}",
                code=code,
                response=resp,
            )
        return resp.get("data", resp)

    # ── Convenience shortcuts (delegate to submodules) ───────────

    def send_message(self, chat_id: str, text: str, *, msg_type: str = "text", token: str | None = None) -> dict:
        """Send a message to a chat. See :mod:`lark_toolkit.messaging`."""
        from .messaging import send_message

        return send_message(self, chat_id, text, msg_type=msg_type, token=token)

    def send_card(self, chat_id: str, card: dict, *, token: str | None = None) -> dict:
        """Send an interactive card to a chat. See :mod:`lark_toolkit.messaging`."""
        from .messaging import send_card

        return send_card(self, chat_id, card, token=token)

    def upload_image(self, image_path: str, *, image_type: str = "message", token: str | None = None) -> str:
        """Upload an image and return the image_key. See :mod:`lark_toolkit.messaging`."""
        from .messaging import upload_image

        return upload_image(self, image_path, image_type=image_type, token=token)

    def send_image(self, chat_id: str, image_key: str, *, token: str | None = None) -> dict:
        """Send an image message to a chat. See :mod:`lark_toolkit.messaging`."""
        from .messaging import send_image

        return send_image(self, chat_id, image_key, token=token)

    def get_bot_info(self, *, token: str | None = None) -> dict:
        """Get bot information."""
        return self.api("GET", "/bot/v3/info", token=token or self.get_tenant_token())

    # ── Internal HTTP helper ─────────────────────────────────────

    def _http_json(
        self,
        method: str,
        url: str,
        *,
        body: dict[str, Any] | None = None,
        token: str | None = None,
        timeout: int = 15,
    ) -> dict[str, Any]:
        """Low-level HTTP JSON request using urllib (no external deps)."""
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        data = json.dumps(body).encode() if body else None
        req = Request(url, data=data, headers=headers, method=method)

        try:
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except HTTPError as e:
            err_body = e.read().decode()
            try:
                return json.loads(err_body)
            except json.JSONDecodeError:
                raise LarkAPIError(f"HTTP {e.code}: {err_body[:500]}", code=e.code) from e
        except URLError as e:
            raise LarkAPIError(f"URL error: {e.reason}") from e
