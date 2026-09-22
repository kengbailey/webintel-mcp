import json

import httpx
import pytest

from src.core.delivery import DeliveryError
from src.core.exa_search import ExaSearch


@pytest.mark.asyncio
async def test_bounded_payload_filters_dedup(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-only")
    calls = []

    def handle(request):
        calls.append(json.loads(request.content))
        assert request.headers["x-api-key"] == "test-only"
        return httpx.Response(
            200,
            json={
                "results": [
                    {"url": "https://example.org/a", "title": "A", "text": "x" * 5000},
                    {"url": "https://example.org/a#fragment"},
                    {"url": "javascript:alert(1)"},
                    {"url": "https://example.org/b?version=2"},
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        rows = await ExaSearch(client).search(
            "query", 5, ["example.org"], start_published_date="2026-01-01T00:00:00Z"
        )
    assert len(calls) == 1
    assert calls[0]["contents"] == {"text": {"maxCharacters": 350}}
    assert calls[0]["includeDomains"] == ["example.org"]
    assert calls[0]["type"] == "auto"
    assert len(rows) == 2 and len(rows[0]["body"]) == 350
    assert rows[1]["url"].endswith("?version=2")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,code",
    [(401, "AUTH_FAILED"), (429, "RATE_LIMITED"), (500, "UPSTREAM_ERROR")],
)
async def test_safe_errors_no_retry(monkeypatch, status, code):
    monkeypatch.setenv("EXA_API_KEY", "test-only")
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(status, text="sensitive upstream diagnostic")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(DeliveryError) as exc:
            await ExaSearch(client).search("query")
    assert exc.value.code == code
    assert "sensitive" not in str(exc.value)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_video_postfilter(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "test-only")

    def handle(request):
        assert "youtube.com/watch" in json.loads(request.content)["includeDomains"]
        return httpx.Response(
            200,
            json={
                "results": [
                    {"url": "https://www.youtube.com/@channel"},
                    {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
                    {"url": "https://youtu.be/dQw4w9WgXcQ"},
                    {"url": "https://evil.example/watch?v=dQw4w9WgXcQ"},
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        rows = await ExaSearch(client).search("query", videos=True)
    assert len(rows) == 1
    assert rows[0]["url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs",
    [
        dict(query=" "),
        dict(query="q", limit=11),
        dict(query="q", include_domains=["https://example.org"]),
        dict(query="q", start_published_date="yesterday"),
        dict(
            query="q",
            start_published_date="2026-01-02T00:00:00Z",
            end_published_date="2026-01-01T00:00:00Z",
        ),
    ],
)
async def test_validation_before_request(kwargs):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: pytest.fail("Unexpected request"))
    ) as client:
        with pytest.raises(DeliveryError) as exc:
            await ExaSearch(client).search(**kwargs)
    assert exc.value.code == "INVALID_ARGUMENT"


@pytest.mark.asyncio
async def test_missing_key(monkeypatch):
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    async with httpx.AsyncClient() as client:
        with pytest.raises(DeliveryError) as exc:
            await ExaSearch(client).search("query")
    assert exc.value.code == "NOT_CONFIGURED"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body", [b"invalid", b'{"results": {}}', b"x" * (1024 * 1024 + 1)]
)
async def test_invalid_and_oversized_response(monkeypatch, body):
    monkeypatch.setenv("EXA_API_KEY", "test-only")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=body))
    ) as client:
        with pytest.raises(DeliveryError) as exc:
            await ExaSearch(client).search("query")
    assert exc.value.code == "UPSTREAM_ERROR"


@pytest.mark.asyncio
async def test_mcp_search_cursor_does_not_call_provider(monkeypatch):
    from unittest.mock import AsyncMock
    from fastmcp import Client
    from src.server import delivery_server as server

    fake = AsyncMock(
        return_value=[dict(id="a", url="https://example.org", body="short")]
    )
    monkeypatch.setattr(server.service.exa, "search", fake)
    async with Client(server.mcp) as client:
        first = await client.call_tool(
            "search", {"query": "test", "include_domains": ["example.org"]}
        )
        assert first.structured_content["meta"]["source"] == "exa"
        assert len(first.structured_content["data"]["items"]) == 1
        cursor = server.service.store.put(
            "anonymous-lan", "web_search", {"pending": [dict(id="b", body="remaining")]}
        )
        page = await client.call_tool("search", {"cursor": cursor})
        assert page.structured_content["data"]["items"][0]["id"] == "b"
        assert not page.structured_content["page"]["has_more"]
    assert fake.await_count == 1
    assert fake.call_args.args[2] == ["example.org"]
