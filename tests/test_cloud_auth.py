"""Tests for cloud auth (OAuth 2.1 WorkOS AuthKit + HMAC-JWT via MultiAuth).

Construction/verification tests only -- no network calls. They validate the
``build_auth()`` factory and the headless JWT round trip against the installed
FastMCP auth classes.
"""
import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.server.auth import build_auth

REPO_ROOT = Path(__file__).resolve().parents[1]
MINT = REPO_ROOT / "scripts" / "mint-machine-jwt.py"

_ENV_KEYS = (
    "MCP_AUTHKIT_DOMAIN",
    "MCP_BASE_URL",
    "MCP_RESOURCE_URL",
    "MCP_MACHINE_SECRET",
    "MCP_REQUIRED_SCOPES",
    "MCP_MACHINE_ISSUER",
)


@pytest.fixture
def clean_env(monkeypatch):
    for k in _ENV_KEYS:
        monkeypatch.delenv(k, raising=False)


def test_no_env_returns_none(clean_env):
    assert build_auth() is None


def test_oauth_only_builds_authkitprovider(clean_env, monkeypatch):
    from fastmcp.server.auth.providers.workos import AuthKitProvider

    monkeypatch.setenv("MCP_AUTHKIT_DOMAIN", "https://x.authkit.app")
    monkeypatch.setenv("MCP_BASE_URL", "https://mcp.example.com")
    assert isinstance(build_auth(), AuthKitProvider)


def test_multi_auth_composes_oauth_and_machine(clean_env, monkeypatch):
    from fastmcp.server.auth import MultiAuth

    monkeypatch.setenv("MCP_AUTHKIT_DOMAIN", "https://x.authkit.app")
    monkeypatch.setenv("MCP_BASE_URL", "https://mcp.example.com")
    monkeypatch.setenv("MCP_RESOURCE_URL", "https://mcp.example.com/mcp")
    monkeypatch.setenv("MCP_MACHINE_SECRET", "a" * 48)
    a = build_auth()
    assert isinstance(a, MultiAuth)
    assert len(a.verifiers) == 1
    assert a.server is not None


def test_machine_jwt_round_trip(clean_env, monkeypatch):
    secret = "a" * 48
    resource = "https://mcp.example.com/mcp"
    monkeypatch.setenv("MCP_AUTHKIT_DOMAIN", "https://x.authkit.app")
    monkeypatch.setenv("MCP_BASE_URL", "https://mcp.example.com")
    monkeypatch.setenv("MCP_RESOURCE_URL", resource)
    monkeypatch.setenv("MCP_MACHINE_SECRET", secret)

    verifier = build_auth().verifiers[0]

    env = {**os.environ, "MCP_MACHINE_SECRET": secret, "MCP_RESOURCE_URL": resource}
    token = subprocess.check_output(
        [sys.executable, str(MINT), "--ttl-hours", "1"], env=env
    ).decode().strip()

    result = asyncio.run(verifier.verify_token(token))
    assert result is not None
    assert result.client_id == "machine"
