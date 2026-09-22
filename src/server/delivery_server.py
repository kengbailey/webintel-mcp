"""Opt-in v2 interface. Run: python -m src.server.delivery_server --port 3091."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from contextlib import asynccontextmanager
from functools import wraps
from typing import Annotated, Literal

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token
from pydantic import Field

from .auth import build_auth
from .handlers import SearchHandlers
from ..core.config import SearchException
from ..core.delivery import (
    Community,
    Content,
    DeliveryError,
    Item,
    Listing,
    Meta,
    Result,
    Video,
)
from ..core.delivery_service import DeliveryService
from ..core.youtube_data import video_id

service = DeliveryService()
legacy = SearchHandlers()


@asynccontextmanager
async def lifespan(server):
    try:
        yield {}
    finally:
        await service.web.close()


mcp = FastMCP(
    "WebIntel MCP — bounded delivery v2", auth=build_auth(), lifespan=lifespan
)


def owner() -> str:
    token = get_access_token()
    # Do not put bearer tokens or identity claims into cursors/logs.
    return (
        hashlib.sha256(token.token.encode()).hexdigest() if token else "anonymous-lan"
    )


def guarded(fn):
    @wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            async with asyncio.timeout(45):
                return await fn(*args, **kwargs)
        except DeliveryError as exc:
            raise ToolError(
                json.dumps({"code": exc.code, "message": str(exc)})
            ) from None
        except (TimeoutError, httpx.TimeoutException):
            raise ToolError(
                json.dumps(
                    {"code": "UPSTREAM_TIMEOUT", "message": "Request deadline exceeded"}
                )
            ) from None
        except httpx.HTTPStatusError as exc:
            code = {429: "RATE_LIMITED", 404: "NOT_FOUND", 403: "UPSTREAM_BLOCKED"}.get(
                exc.response.status_code, "UPSTREAM_ERROR"
            )
            raise ToolError(
                json.dumps({"code": code, "message": "Upstream request failed"})
            ) from None
        except SearchException as exc:
            message = str(exc).casefold()
            code = (
                "NOT_CONFIGURED"
                if "not configured" in message
                else "RATE_LIMITED"
                if "rate limit" in message
                else "UPSTREAM_TIMEOUT"
                if "timed out" in message
                else "UPSTREAM_ERROR"
            )
            raise ToolError(
                json.dumps({"code": code, "message": "Provider request failed"})
            ) from None
        except httpx.HTTPError:
            raise ToolError(
                json.dumps(
                    {"code": "UPSTREAM_ERROR", "message": "Provider request failed"}
                )
            ) from None
        except Exception:
            raise ToolError(
                json.dumps(
                    {
                        "code": "INTERNAL_ERROR",
                        "message": "Request could not be completed",
                    }
                )
            ) from None

    return wrapper


Limit = Annotated[int, Field(ge=1, le=10)]
Budget = Annotated[int, Field(ge=1, le=20000)]
Query = Annotated[str, Field(min_length=1, max_length=500)]
Cursor = Annotated[str | None, Field(max_length=128)]
READ = {"readOnlyHint": True, "openWorldHint": True}


@mcp.tool(annotations=READ)
@guarded
async def fetch_content(
    url: Query,
    max_chars: Budget = 20000,
    mode: Literal["content", "outline", "excerpts"] = "content",
    query: Query | None = None,
) -> Result[Content]:
    """Fetch public web content. Up to 20k characters/5k estimated tokens. Use read_content for next_cursor; never re-fetch to continue. Excerpts are selected paragraphs, not full coverage."""
    return await service.fetch(owner(), url, max_chars, mode, query)


@mcp.tool(annotations=READ)
@guarded
async def read_content(
    cursor: Annotated[str, Field(min_length=1, max_length=128)],
    max_chars: Budget = 20000,
) -> Result[Content]:
    """Read the next snapshot chunk for a page, post, comment, description or transcript. Cursors expire after 15 minutes and may be evicted; authenticated cursors are bearer-scoped."""
    return service.store.read(owner(), cursor, max_chars)


@mcp.tool(annotations=READ)
@guarded
async def search_reddit(
    query: Query | None = None,
    subreddit: Query | None = None,
    limit: Limit = 5,
    cursor: Cursor = None,
    match: Literal["all", "title"] = "all",
    sort: str = "relevance",
    time_filter: str | None = None,
) -> Result[Listing]:
    """Compact Reddit post discovery, not full bodies. Title match is optional. With cursor, saved query/filter settings are used; omit new filters. Read selected posts separately."""
    return await service.reddit_search(
        owner(), query, subreddit, limit, cursor, match, sort, time_filter
    )


@mcp.tool(annotations=READ)
@guarded
async def fetch_subreddit(
    subreddit: Query | None = None,
    sort: str = "hot",
    time_filter: str | None = None,
    limit: Limit = 5,
    cursor: Cursor = None,
) -> Result[Listing]:
    """Compact subreddit post listing. Cursor resumes the saved sort/filter, including undelivered upstream items."""
    return await service.subreddit(owner(), subreddit, sort, time_filter, limit, cursor)


@mcp.tool(annotations=READ)
@guarded
async def fetch_reddit_post(reference: Query) -> Result[Item]:
    """Read a Reddit post with metadata and bounded body; NEVER includes comments. Use read_content for body_cursor; fetch_reddit_comments for discussion."""
    return await service.post(owner(), reference)


@mcp.tool(annotations=READ)
@guarded
async def fetch_reddit_comments(
    reference: Query | None = None,
    limit: Limit = 10,
    cursor: Cursor = None,
    sort: str = "top",
    parent_id: Query | None = None,
) -> Result[Listing]:
    """Explicit bounded Reddit comments. parent_id focuses a thread. Cursor retains overflow and expansion IDs server-side. Large bodies have read_content cursors. Pagination uses saved parameters."""
    return await service.comments(owner(), reference, limit, cursor, sort, parent_id)


@mcp.tool(annotations=READ)
@guarded
async def fetch_youtube_content(reference: Query) -> Result[Video]:
    """Cheap video metadata, description and public counts. NO audio download, transcript or comments. Unavailable dislikes are null, never zero or estimated."""
    return await service.video(owner(), reference)


@mcp.tool(annotations=READ)
@guarded
async def fetch_youtube_transcript(
    reference: Query,
    language: Annotated[str, Field(max_length=30)] = "en",
    max_chars: Budget = 20000,
) -> Result[Content]:
    """Explicit timestamped captions (manual preferred, automatic fallback). No implicit STT. Continue with read_content. Unavailable language returns CAPTIONS_UNAVAILABLE."""
    text, source = await service.youtube.transcript(reference, language)
    return service.store.content(
        owner(),
        text,
        "https://www.youtube.com/watch?v=" + video_id(reference),
        source,
        max_chars,
    )


@mcp.tool(annotations=READ)
@guarded
async def fetch_youtube_comments(
    reference: Query | None = None,
    limit: Limit = 10,
    cursor: Cursor = None,
    order: Literal["relevance", "time"] = "relevance",
    parent_id: Query | None = None,
    query: Query | None = None,
) -> Result[Listing]:
    """Explicit YouTube comment page; requires YOUTUBE_API_KEY. Top-level comments by default; parent_id fetches replies. No automatic reply recursion. Cursor uses saved parameters."""
    return await service.video_comments(
        owner(), reference, limit, cursor, order, parent_id, query
    )


@mcp.tool(annotations=READ)
@guarded
async def search(
    query: Query | None = None, limit: Limit = 5, cursor: Cursor = None
) -> Result[Listing]:
    """Compact web search. Current SearxNG provider retained pending paid-provider selection. Snippets only; fetch selected URLs separately."""
    if cursor:
        return service.listing(
            owner(),
            "web_search",
            service.store.get(owner(), cursor, "web_search"),
            limit,
            "searxng",
            preview=True,
        )
    if not query:
        raise DeliveryError("INVALID_ARGUMENT", "Search query is required")
    rows = await asyncio.to_thread(legacy.search, query, limit)
    state = {
        "pending": [
            dict(id=str(i + 1), title=x.title, url=x.url, body=x.content or "")
            for i, x in enumerate(rows)
        ]
    }
    return service.listing(owner(), "web_search", state, limit, "searxng", preview=True)


@mcp.tool(annotations=READ)
@guarded
async def search_videos(
    query: Query | None = None, limit: Limit = 5, cursor: Cursor = None
) -> Result[Listing]:
    """Compact YouTube discovery through existing provider; no metadata/transcripts automatically fetched."""
    if cursor:
        return service.listing(
            owner(),
            "video_search",
            service.store.get(owner(), cursor, "video_search"),
            limit,
            "searxng",
            preview=True,
        )
    if not query:
        raise DeliveryError("INVALID_ARGUMENT", "Search query is required")
    rows = await asyncio.to_thread(legacy.search_videos, query, limit)
    state = {
        "pending": [
            dict(
                id=str(i + 1),
                title=x.title,
                url=x.url,
                body=x.content or "",
                author=x.author,
            )
            for i, x in enumerate(rows)
        ]
    }
    return service.listing(
        owner(), "video_search", state, limit, "searxng", preview=True
    )


@mcp.tool(annotations=READ)
@guarded
async def fetch_subreddit_info(subreddit: Query) -> Result[Community]:
    """Bounded public subreddit metadata, without posts or comments."""
    raw = await service.reddit.fetch_subreddit_info(subreddit)
    data = raw.get("data", {})
    name = data.get("display_name", subreddit)[:100]
    url = "https://www.reddit.com/r/" + name + "/"
    body, cursor = service.store.body(
        owner(), data.get("public_description") or "", url, "reddit", 3000
    )
    return Result(
        data=Community(
            name=name,
            title=(data.get("title") or "")[:300],
            description=body,
            description_cursor=cursor,
            subscribers=data.get("subscribers"),
            active_user_count=data.get("active_user_count"),
            over18=data.get("over18", False),
            url=url,
        ),
        meta=Meta(source="reddit", truncated=bool(cursor)),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=3091)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--transport", choices=["http", "sse"], default="http")
    args = parser.parse_args()
    mcp.run(transport=args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
