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
