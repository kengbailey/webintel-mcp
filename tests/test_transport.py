"""
Tests for server transport configuration (PR #7).

Covers:
- resolve_transport: CLI flags, env var, defaults, invalid values
- resolve_port: CLI override, env var, defaults, invalid values
- CLI flag precedence over environment variables
"""

import pytest
from src.server.mcp_server import resolve_transport, resolve_port


class TestResolveTransport:
    """Test transport resolution logic."""

    # --- Defaults ---

    def test_default_is_http(self):
        """Default transport should be http when nothing is specified."""
        transport, warning = resolve_transport()
        assert transport == "http"
        assert warning is None

    # --- CLI flags ---

    def test_cli_http_flag(self):
        """--http flag should select http transport."""
        transport, warning = resolve_transport(cli_http=True)
        assert transport == "http"
        assert warning is None

    def test_cli_sse_flag(self):
        """--sse flag should select sse transport."""
        transport, warning = resolve_transport(cli_sse=True)
        assert transport == "sse"
        assert warning is None

    # --- Environment variable ---

    def test_env_http(self):
        """MCP_TRANSPORT=http should select http."""
        transport, warning = resolve_transport(env_transport="http")
        assert transport == "http"
        assert warning is None

    def test_env_sse(self):
        """MCP_TRANSPORT=sse should select sse."""
        transport, warning = resolve_transport(env_transport="sse")
        assert transport == "sse"
        assert warning is None

    def test_env_case_insensitive(self):
        """MCP_TRANSPORT should be case-insensitive."""
        transport, warning = resolve_transport(env_transport="HTTP")
        assert transport == "http"
        assert warning is None

        transport, warning = resolve_transport(env_transport="SSE")
        assert transport == "sse"
        assert warning is None

    def test_env_invalid_falls_back_to_http(self):
        """Invalid MCP_TRANSPORT should fall back to http with a warning."""
        transport, warning = resolve_transport(env_transport="websocket")
        assert transport == "http"
        assert warning is not None
        assert "websocket" in warning

    def test_env_empty_string_falls_back_to_http(self):
        """Empty MCP_TRANSPORT should fall back to http (treated as unset)."""
        transport, warning = resolve_transport(env_transport="")
        assert transport == "http"
        assert warning is None

    # --- CLI precedence over env ---

    def test_cli_http_overrides_env_sse(self):
        """--http flag should override MCP_TRANSPORT=sse."""
        transport, warning = resolve_transport(cli_http=True, env_transport="sse")
        assert transport == "http"
        assert warning is None

    def test_cli_sse_overrides_env_http(self):
        """--sse flag should override MCP_TRANSPORT=http."""
        transport, warning = resolve_transport(cli_sse=True, env_transport="http")
        assert transport == "sse"
        assert warning is None

    def test_cli_flag_overrides_invalid_env(self):
        """CLI flag should override an invalid MCP_TRANSPORT without warning."""
        transport, warning = resolve_transport(cli_http=True, env_transport="garbage")
        assert transport == "http"
        assert warning is None


class TestResolvePort:
    """Test port resolution logic."""

    def test_default_port(self):
        """Default port should be 3090."""
        assert resolve_port() == 3090

    def test_cli_port_override(self):
        """CLI --port should override default."""
        assert resolve_port(cli_port=8080) == 8080

    def test_env_port_override(self):
        """MCP_PORT env var should override default."""
        assert resolve_port(env_port="4000") == 4000

    def test_cli_port_overrides_env(self):
        """CLI --port should take precedence over MCP_PORT env var."""
        assert resolve_port(cli_port=8080, env_port="4000") == 8080

    def test_invalid_env_port_falls_back_to_default(self):
        """Non-numeric MCP_PORT should fall back to default."""
        assert resolve_port(env_port="notanumber") == 3090

    def test_none_env_port_falls_back_to_default(self):
        """None MCP_PORT should fall back to default."""
        assert resolve_port(env_port=None) == 3090

    def test_custom_default_port(self):
        """Custom default port should be used when nothing else is set."""
        assert resolve_port(default=5000) == 5000
