"""Tests for LarkClient initialization and token management."""

from __future__ import annotations

import json
import pathlib
import time
from unittest.mock import patch

import pytest

from lark_toolkit import LarkAPIError, LarkClient


class TestClientInit:
    """Test LarkClient initialization and configuration."""

    def test_init_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LARK_APP_ID", "test_id")
        monkeypatch.setenv("LARK_APP_SECRET", "test_secret")
        client = LarkClient()
        assert client.app_id == "test_id"
        assert client.app_secret == "test_secret"

    def test_init_explicit_params(self) -> None:
        client = LarkClient(app_id="my_id", app_secret="my_secret")
        assert client.app_id == "my_id"
        assert client.app_secret == "my_secret"

    def test_init_default_base_url(self) -> None:
        client = LarkClient(app_id="x", app_secret="y")
        assert client.base_url == "https://open.larksuite.com/open-apis"

    def test_init_custom_base_url(self) -> None:
        client = LarkClient(app_id="x", app_secret="y", base_url="https://custom.api/v1/")
        assert client.base_url == "https://custom.api/v1"  # trailing slash stripped

    def test_init_base_url_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LARK_BASE_URL", "https://env.api/open")
        client = LarkClient(app_id="x", app_secret="y")
        assert client.base_url == "https://env.api/open"

    def test_init_no_credentials_allowed(self) -> None:
        """Client can be created without credentials; errors happen at token time."""
        client = LarkClient()
        assert client.app_id == ""


class TestTenantToken:
    """Test tenant token acquisition and caching."""

    def test_get_tenant_token_missing_credentials(self) -> None:
        client = LarkClient(app_id="", app_secret="")
        with pytest.raises(LarkAPIError, match="LARK_APP_ID and LARK_APP_SECRET are required"):
            client.get_tenant_token()

    def test_get_tenant_token_caching(self) -> None:
        client = LarkClient(app_id="test", app_secret="test")
        fake_response = {"tenant_access_token": "tok_abc", "expire": 7200}

        with patch.object(client, "_http_json", return_value=fake_response) as mock_http:
            token1 = client.get_tenant_token()
            token2 = client.get_tenant_token()

        assert token1 == "tok_abc"
        assert token2 == "tok_abc"
        # Should only call API once due to caching
        mock_http.assert_called_once()

    def test_get_tenant_token_force_refresh(self) -> None:
        client = LarkClient(app_id="test", app_secret="test")
        fake_response = {"tenant_access_token": "tok_refreshed", "expire": 7200}

        with patch.object(client, "_http_json", return_value=fake_response) as mock_http:
            token1 = client.get_tenant_token()
            token2 = client.get_tenant_token(force_refresh=True)

        assert token1 == "tok_refreshed"
        assert token2 == "tok_refreshed"
        assert mock_http.call_count == 2

    def test_get_tenant_token_api_error(self) -> None:
        client = LarkClient(app_id="test", app_secret="test")
        fake_response = {"code": 99999, "msg": "bad request"}

        with (
            patch.object(client, "_http_json", return_value=fake_response),
            pytest.raises(LarkAPIError, match="Failed to get tenant_access_token"),
        ):
            client.get_tenant_token()


class TestUserToken:
    """Test user token reading from file."""

    def test_get_user_token_no_file(self) -> None:
        client = LarkClient(app_id="x", app_secret="y", user_token_file="/nonexistent/path")
        with pytest.raises(FileNotFoundError):
            client.get_user_token()

    def test_get_user_token_no_path_configured(self) -> None:
        client = LarkClient(app_id="x", app_secret="y")
        with pytest.raises(FileNotFoundError):
            client.get_user_token()

    def test_get_user_token_valid(self, tmp_path: pathlib.Path) -> None:
        token_file = tmp_path / "token.json"
        token_file.write_text(json.dumps({"access_token": "user_tok_123"}))

        client = LarkClient(app_id="x", app_secret="y", user_token_file=str(token_file))
        assert client.get_user_token() == "user_tok_123"

    def test_get_user_token_expired(self, tmp_path: pathlib.Path) -> None:
        token_file = tmp_path / "token.json"
        token_file.write_text(json.dumps({"access_token": "expired_tok", "expires_at": time.time() - 100}))

        client = LarkClient(app_id="x", app_secret="y", user_token_file=str(token_file))
        with pytest.raises(LarkAPIError, match="expired"):
            client.get_user_token()

    def test_get_user_token_missing_access_token(self, tmp_path: pathlib.Path) -> None:
        token_file = tmp_path / "token.json"
        token_file.write_text(json.dumps({"refresh_token": "only_refresh"}))

        client = LarkClient(app_id="x", app_secret="y", user_token_file=str(token_file))
        with pytest.raises(LarkAPIError, match="No access_token"):
            client.get_user_token()


class TestApiCall:
    """Test the generic API call method."""

    def test_api_returns_data(self) -> None:
        client = LarkClient(app_id="test", app_secret="test")
        fake_response = {"code": 0, "data": {"items": [1, 2, 3]}}

        with patch.object(client, "_http_json", return_value=fake_response):
            result = client.api("GET", "/test/endpoint", token="fake_token")

        assert result == {"items": [1, 2, 3]}

    def test_api_raw_mode(self) -> None:
        client = LarkClient(app_id="test", app_secret="test")
        fake_response = {"code": 0, "data": {"items": []}, "msg": "ok"}

        with patch.object(client, "_http_json", return_value=fake_response):
            result = client.api("GET", "/test", token="fake_token", raw=True)

        assert result == fake_response

    def test_api_error_code(self) -> None:
        client = LarkClient(app_id="test", app_secret="test")
        fake_response = {"code": 40003, "msg": "invalid token"}

        with (
            patch.object(client, "_http_json", return_value=fake_response),
            pytest.raises(LarkAPIError, match="code=40003"),
        ):
            client.api("GET", "/test", token="fake_token")

    def test_api_full_url_passthrough(self) -> None:
        client = LarkClient(app_id="test", app_secret="test")
        fake_response = {"code": 0, "data": {}}

        with patch.object(client, "_http_json", return_value=fake_response) as mock_http:
            client.api("GET", "https://other.api/endpoint", token="tok")

        call_args = mock_http.call_args
        assert call_args[0][1] == "https://other.api/endpoint"

    def test_api_path_prepends_base_url(self) -> None:
        client = LarkClient(app_id="test", app_secret="test")
        fake_response = {"code": 0, "data": {}}

        with patch.object(client, "_http_json", return_value=fake_response) as mock_http:
            client.api("GET", "/im/v1/chats", token="tok")

        call_args = mock_http.call_args
        assert call_args[0][1] == "https://open.larksuite.com/open-apis/im/v1/chats"
