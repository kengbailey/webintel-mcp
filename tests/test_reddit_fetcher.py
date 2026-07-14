"""Tests for Reddit OAuth fetching."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.core.config import SearchConfig, SearchException
from src.core.reddit_fetcher import RedditFetcher


@pytest.fixture(autouse=True)
def reddit_credentials(monkeypatch):
    monkeypatch.setattr(SearchConfig, "REDDIT_CLIENT_ID", "client-id")
    monkeypatch.setattr(SearchConfig, "REDDIT_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(SearchConfig, "REDDIT_USER_AGENT", "test-agent")
    monkeypatch.setattr(SearchConfig, "REDDIT_PROXY_URL", None)


def response(status: int, payload=None, headers=None, request_url="https://example.test"):
    request = httpx.Request("GET", request_url)
    return httpx.Response(status, json=payload, headers=headers, request=request)


@pytest.mark.asyncio
async def test_fetch_uses_oauth_and_caches_token():
    token_response = response(
        200,
        {"access_token": "token-1", "expires_in": 3600},
        request_url=RedditFetcher.TOKEN_URL,
    )
    listing_response = response(200, {"kind": "Listing", "data": {"children": []}})
    client = AsyncMock()
    client.post.return_value = token_response
    client.get.return_value = listing_response
    client.__aenter__.return_value = client
    client.__aexit__.return_value = None

    with patch("src.core.reddit_fetcher.httpx.AsyncClient", return_value=client):
        fetcher = RedditFetcher()
        await fetcher.fetch_subreddit_posts("python")
        await fetcher.fetch_subreddit_posts("python")

    assert client.post.await_count == 1
    assert client.get.await_count == 2
    assert client.get.await_args.kwargs["headers"]["Authorization"] == "bearer token-1"
    assert client.get.await_args.args[0].startswith("https://oauth.reddit.com/")


@pytest.mark.asyncio
async def test_missing_credentials_has_clear_error(monkeypatch):
    monkeypatch.setattr(SearchConfig, "REDDIT_CLIENT_ID", None)
    fetcher = RedditFetcher()

    with pytest.raises(SearchException, match="REDDIT_CLIENT_ID"):
        await fetcher.fetch_subreddit_posts("python")


@pytest.mark.asyncio
async def test_rate_limit_reports_reset_time():
    fetcher = RedditFetcher()
    fetcher._get_access_token = AsyncMock(return_value="token")
    limited = response(429, {}, {"x-ratelimit-reset": "42"})
    client = AsyncMock()
    client.get.return_value = limited
    client.__aenter__.return_value = client
    client.__aexit__.return_value = None

    with patch("src.core.reddit_fetcher.httpx.AsyncClient", return_value=client):
        with pytest.raises(SearchException, match="42 seconds"):
            await fetcher.fetch_subreddit_posts("python")


@pytest.mark.parametrize(
    ("reference", "post_id", "subreddit"),
    [
        ("1abcde", "1abcde", None),
        ("t3_1abcde", "1abcde", None),
        ("https://redd.it/1abcde", "1abcde", None),
        (
            "https://www.reddit.com/r/python/comments/1abcde/example_title/",
            "1abcde",
            "python",
        ),
        ("/r/python/comments/1abcde/example_title/", "1abcde", "python"),
        ("https://www.reddit.com/comments/a/old_post/", "a", None),
    ],
)
def test_parse_post_reference(reference, post_id, subreddit):
    assert RedditFetcher.parse_post_reference(reference) == (post_id, subreddit)


def test_parse_post_reference_rejects_non_reddit_url():
    with pytest.raises(SearchException, match="Reddit post URL"):
        RedditFetcher.parse_post_reference("https://example.com/comments/1abcde")


@pytest.mark.asyncio
async def test_search_posts_scopes_to_subreddit():
    fetcher = RedditFetcher()
    fetcher._get = AsyncMock(return_value=response(200, {"kind": "Listing"}))

    result = await fetcher.search_posts(
        "asyncio",
        subreddit="python",
        sort="top",
        time_filter="week",
        limit=10,
    )

    assert result["kind"] == "Listing"
    url, params = fetcher._get.await_args.args
    assert url == "https://oauth.reddit.com/r/python/search.json"
    assert params["restrict_sr"] == "on"
    assert params["q"] == "asyncio"
    assert params["t"] == "week"


@pytest.mark.asyncio
async def test_fetch_more_comments_builds_morechildren_request():
    fetcher = RedditFetcher()
    fetcher._get = AsyncMock(return_value=response(200, {"json": {"data": {"things": []}}}))

    await fetcher.fetch_more_comments("t3_1abcde", ["t1_def456", "ghi789"])

    url, params = fetcher._get.await_args.args
    assert url == "https://oauth.reddit.com/api/morechildren"
    assert params["link_id"] == "t3_1abcde"
    assert params["children"] == "def456,ghi789"


@pytest.mark.asyncio
async def test_fetch_subreddit_info_uses_about_endpoint():
    fetcher = RedditFetcher()
    fetcher._get = AsyncMock(return_value=response(200, {"kind": "t5", "data": {}}))

    await fetcher.fetch_subreddit_info("python")

    assert fetcher._get.await_args.args[0] == "https://oauth.reddit.com/r/python/about.json"
