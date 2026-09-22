"""Losslessness, budgets and access boundaries for opt-in v2 delivery."""

import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastmcp import Client

from src.core.delivery import DeliveryError, SnapshotStore, tokens
from src.core.delivery_service import DeliveryService
from src.core.youtube_data import video_id, YouTubeData
from src.core.web_fetcher import WebContentFetcher


@pytest.mark.parametrize(
    "text", ["abc\n" * 21000, "这是一个测试。😀" * 6000, "<|endoftext|>λ" * 4000]
)
def test_content_reconstructs_without_unicode_or_token_loss(text):
    store = SnapshotStore()
    result = store.content("alice", text, "https://example.com", "fixture")
    output = []
    while True:
        assert len(result.data.content) <= 20000
        assert tokens(result.data.content) <= 5000
        output.append(result.data.content)
        if not result.page.has_more:
            break
        result = store.read("alice", result.page.next_cursor)
    assert "".join(output) == text


def test_cursor_scope_kind_expiry_and_snapshot_immutability():
    store = SnapshotStore(ttl=10)
    original = {"pending": [{"body": "original"}]}
    cursor = store.put("alice", "listing", original)
    original["pending"][0]["body"] = "changed"
    assert store.get("alice", cursor, "listing")["pending"][0]["body"] == "original"
    with pytest.raises(DeliveryError, match="caller"):
        store.get("bob", cursor, "listing")
    with pytest.raises(DeliveryError, match="another tool"):
        store.get("alice", cursor, "content")
    with patch("src.core.delivery.time.monotonic", return_value=time.monotonic() + 11):
        with pytest.raises(DeliveryError, match="expired"):
            store.get("alice", cursor, "listing")


def test_eviction_and_oversized_snapshot():
    store = SnapshotStore(max_bytes=150)
    first = store.put("a", "x", {"body": "a" * 60})
    store.put("a", "x", {"body": "b" * 60})
    assert store._bytes <= 150
    with pytest.raises(DeliveryError):
        store.get("a", first, "x")
    with pytest.raises(DeliveryError, match="storage limit"):
        store.put("a", "x", {"body": "c" * 151})


@pytest.mark.asyncio
async def test_jina_no_longer_discards_later_pages():
    fetcher = WebContentFetcher()
    raw = "abc" * 25000
    response = httpx.Response(
        200, text=raw, request=httpx.Request("GET", "https://r.jina.ai/test.pdf")
    )
    with patch("src.core.web_fetcher.httpx.AsyncClient") as cls:
        cls.return_value.__aenter__.return_value.get = AsyncMock(return_value=response)
        parts = []
        offset = 0
        while True:
            body, more, offset, total = await fetcher.fetch_and_parse(
                "https://example.com/test.pdf", offset
            )
            parts.append(body)
            assert total == len(raw)
            if not more:
                break
    assert "".join(parts) == raw


@pytest.mark.asyncio
async def test_reddit_search_retains_overflow_before_upstream_cursor():
    service = DeliveryService()
    service.reddit.search_posts = AsyncMock(
        side_effect=[
            {
                "data": {
                    "children": [
                        {
                            "kind": "t3",
                            "data": {
                                "id": str(i),
                                "title": str(i),
                                "selftext": "X" * 5000,
                            },
                        }
                        for i in range(10)
                    ],
                    "after": "next",
                }
            },
            {
                "data": {
                    "children": [{"kind": "t3", "data": {"id": "10", "title": "last"}}],
                    "after": None,
                }
            },
        ]
    )
    first = await service.reddit_search(
        "a", "query", None, 5, None, "all", "relevance", None
    )
    assert len(first.data.items) == 5
    assert all(len(x.body) <= 300 for x in first.data.items)
    second = await service.reddit_search(
        "a", None, None, 5, first.page.next_cursor, "all", "relevance", None
    )
    assert service.reddit.search_posts.await_count == 1
    third = await service.reddit_search(
        "a", None, None, 5, second.page.next_cursor, "all", "relevance", None
    )
    assert [x.id for r in [first, second, third] for x in r.data.items] == [
        str(i) for i in range(11)
    ]
    assert not third.page.has_more
    assert service.reddit.search_posts.call_args.kwargs["after"] == "next"


@pytest.mark.asyncio
async def test_comments_preserve_large_bodies_and_no_repeated_ids():
    service = DeliveryService()
    giant = "你好😀\n" * 2000
    service.reddit.resolve_post_reference = AsyncMock(return_value=("abc", "test"))
    initial = [
        {"kind": "t1", "data": {"id": "one", "body": giant, "parent_id": "t3_abc"}},
        {"kind": "more", "data": {"children": ["two"]}},
    ]
    service.reddit.fetch_post_with_comments = AsyncMock(
        return_value=[{}, {"data": {"children": initial}}]
    )
    service.reddit.fetch_more_comments = AsyncMock(
        return_value={
            "json": {
                "data": {
                    "things": [
                        {"kind": "t1", "data": {"id": "one", "body": giant}},
                        {"kind": "t1", "data": {"id": "two", "body": "second"}},
                    ]
                }
            }
        }
    )
    first = await service.comments("a", "abc", 1, None, "top", None)
    item = first.data.items[0]
    parts = [item.body]
    cursor = item.body_cursor
    while cursor:
        part = service.store.read("a", cursor)
        parts.append(part.data.content)
        cursor = part.page.next_cursor
    assert "".join(parts) == giant
    second = await service.comments("a", None, 1, first.page.next_cursor, "top", None)
    assert [x.id for x in second.data.items] == ["two"]
    assert not second.page.has_more


@pytest.mark.asyncio
async def test_post_never_calls_comment_endpoint():
    service = DeliveryService()
    service.reddit.resolve_post_reference = AsyncMock(return_value=("abc", None))
    service.reddit._get = AsyncMock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "children": [
                        {
                            "data": {
                                "id": "abc",
                                "selftext": "post",
                                "num_comments": 100000,
                            }
                        }
                    ]
                }
            },
        )
    )
    service.reddit.fetch_post_with_comments = AsyncMock()
    result = await service.post("a", "abc")
    assert result.data.num_comments == 100000
    assert "comments" not in result.data.model_dump()
    service.reddit.fetch_post_with_comments.assert_not_called()
    assert "/api/info" in service.reddit._get.call_args.args[0]


@pytest.mark.asyncio
async def test_youtube_comments_hold_unused_provider_items_and_reply_parameters():
    service = DeliveryService()
    service.youtube.api = AsyncMock(
        return_value={
            "items": [
                {"id": str(i), "snippet": {"textDisplay": "body", "parentId": "parent"}}
                for i in range(10)
            ],
            "nextPageToken": "yt-next",
        }
    )
    first = await service.video_comments(
        "a", "jNQXAC9IVRw", 5, None, "relevance", "parent", None
    )
    second = await service.video_comments(
        "a", None, 5, first.page.next_cursor, "relevance", None, None
    )
    assert len(first.data.items + second.data.items) == 10
    assert service.youtube.api.await_count == 1
    assert service.youtube.api.call_args.args[0] == "comments"
    assert service.youtube.api.call_args.args[1]["parentId"] == "parent"


@pytest.mark.asyncio
async def test_metadata_has_no_implicit_transcription_or_comments():
    service = DeliveryService()
    service.youtube.metadata = AsyncMock(
        return_value={"id": "jNQXAC9IVRw", "description": "hello", "source": "yt_dlp"}
    )
    service.youtube.transcript = AsyncMock()
    service.youtube.api = AsyncMock()
    result = await service.video("a", "jNQXAC9IVRw")
    assert result.data.description == "hello"
    assert result.data.dislike_count is None
    service.youtube.transcript.assert_not_called()
    service.youtube.api.assert_not_called()


@pytest.mark.parametrize(
    "reference",
    [
        "jNQXAC9IVRw",
        "https://youtu.be/jNQXAC9IVRw",
        "https://www.youtube.com/watch?v=jNQXAC9IVRw",
        "https://youtube.com/shorts/jNQXAC9IVRw",
    ],
)
def test_video_reference_parsing_is_local(reference):
    assert video_id(reference) == "jNQXAC9IVRw"


@pytest.mark.parametrize(
    "reference",
    [
        "https://youtube.com.evil.test/watch?v=jNQXAC9IVRw",
        "http://127.0.0.1/",
        "not-an-id",
    ],
)
def test_reject_arbitrary_video_urls(reference):
    with pytest.raises(DeliveryError):
        video_id(reference)


@pytest.mark.asyncio
async def test_wire_schema_errors_and_no_context_duplication_in_text():
    from src.server.delivery_server import mcp, service

    result = service.store.content(
        "anonymous-lan", "test" * 6000, "https://example.com", "fixture"
    )
    async with Client(mcp) as client:
        tools = await client.list_tools()
        assert {
            "fetch_reddit_comments",
            "read_content",
            "fetch_youtube_transcript",
        } <= {x.name for x in tools}
        out = await client.call_tool(
            "read_content", {"cursor": result.page.next_cursor}
        )
        assert out.structured_content["schema_version"] == 2
        assert len([x for x in out.content if x.type == "text"]) == 1
        bad = await client.call_tool(
            "read_content", {"cursor": "invalid"}, raise_on_error=False
        )
        assert bad.is_error
        assert "CURSOR_EXPIRED" in bad.content[0].text
        invalid = await client.call_tool(
            "fetch_reddit_comments", {"limit": 11}, raise_on_error=False
        )
        assert invalid.is_error


@pytest.mark.asyncio
async def test_public_url_rejects_private_and_credentials():
    from src.core.public_fetch import validate_url

    for url in [
        "http://127.0.0.1/",
        "http://user:secret@example.com",
        "file:///tmp/test",
    ]:
        with pytest.raises(DeliveryError):
            await validate_url(url)


@pytest.mark.asyncio
async def test_download_redirect_private_target_is_rejected():
    from src.core.public_fetch import PublicWebFetcher

    fetcher = PublicWebFetcher()

    async def validate(url):
        if "127.0.0.1" in url:
            raise DeliveryError("INVALID_ARGUMENT", "Private address")

    def response(request):
        return httpx.Response(302, headers={"location": "http://127.0.0.1/secret"})

    fetcher.client = httpx.AsyncClient(transport=httpx.MockTransport(response))
    with patch("src.core.public_fetch.validate_url", side_effect=validate):
        with pytest.raises(DeliveryError, match="Private"):
            await fetcher.download("https://example.com")
    await fetcher.close()


@pytest.mark.asyncio
async def test_markdown_bypasses_html_and_client_is_reused():
    from src.core.public_fetch import PublicWebFetcher

    fetcher = PublicWebFetcher()
    calls = []

    def response(request):
        calls.append(request.url)
        return httpx.Response(
            200,
            text="# Heading\n\nA [link](https://example.com).",
            headers={"content-type": "text/markdown"},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(response))
    fetcher.client = client
    with (
        patch("src.core.public_fetch.validate_url", new_callable=AsyncMock),
        patch.object(fetcher, "_parse_html_content") as parse,
    ):
        a = await fetcher.fetch_and_parse("https://example.com")
        await fetcher.fetch_and_parse("https://example.com")
        assert "[link]" in a[0]
        parse.assert_not_called()
        assert fetcher.http() is client
    await fetcher.close()
    assert client.is_closed


@pytest.mark.asyncio
async def test_youtube_error_codes_without_key_leak():
    data = YouTubeData()
    data.key = "DO_NOT_LEAK"
    response = httpx.Response(
        403, json={"error": {"errors": [{"reason": "commentsDisabled"}]}}
    )
    with patch("src.core.youtube_data.httpx.AsyncClient") as client:
        client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=response
        )
        with pytest.raises(DeliveryError) as exc:
            await data.api("commentThreads", {})
    assert exc.value.code == "COMMENTS_DISABLED"
    assert "DO_NOT_LEAK" not in str(exc.value)


@pytest.mark.asyncio
async def test_community_metadata_uses_common_envelope():
    from src.server.delivery_server import mcp, service

    with patch.object(
        service.reddit,
        "fetch_subreddit_info",
        AsyncMock(
            return_value={
                "data": {
                    "display_name": "test",
                    "title": "A test community",
                    "public_description": "hello",
                    "subscribers": 123,
                }
            }
        ),
    ):
        async with Client(mcp) as client:
            result = await client.call_tool(
                "fetch_subreddit_info", {"subreddit": "test"}
            )
            assert result.structured_content["schema_version"] == 2
            assert result.structured_content["data"]["subscribers"] == 123
            assert result.structured_content["data"]["description"] == "hello"


@pytest.mark.asyncio
async def test_browser_readiness_and_cancellation_close_page():
    import asyncio
    from unittest.mock import Mock
    from src.core.public_fetch import PublicWebFetcher

    fetcher = PublicWebFetcher()
    page = AsyncMock()
    main = Mock()
    main.count = AsyncMock(return_value=1)
    main.inner_text = AsyncMock(return_value="Ready article text. " * 20)
    locator = Mock()
    locator.first = main
    page.locator = Mock(return_value=locator)
    page.content = AsyncMock(return_value="<article>ready</article>")
    with (
        patch.object(fetcher, "_ensure_browser", AsyncMock()),
        patch.object(fetcher, "_new_browser_page", AsyncMock(return_value=page)),
    ):
        assert (
            await fetcher._render_with_browser("https://example.com")
            == "<article>ready</article>"
        )
        assert page.goto.call_args.kwargs["wait_until"] == "domcontentloaded"
        page.close.assert_awaited_once()
        page.close.reset_mock()
        page.goto.side_effect = asyncio.CancelledError()
        with pytest.raises(asyncio.CancelledError):
            await fetcher._render_with_browser("https://example.com")
        page.close.assert_awaited_once()
