"""
FastMCP Server for exposing search functionality
Provides general web search capabilities via SearxNG
"""

import argparse
import os
import sys
from typing import List, Annotated
from pydantic import Field
from fastmcp import FastMCP
from .handlers import SearchHandlers
from ..core.models import (
    SearchResultOutput, 
    VideoSearchResultOutput, 
    FetchContentOutput, 
    YouTubeContentOutput,
    SubredditPostsOutput,
    RedditPostOutput
)


# Create the MCP server
mcp = FastMCP("WebIntel MCP")
handlers = SearchHandlers()


@mcp.tool(
    tags={"search", "web"},
    annotations={
        "title": "Web Search",
        "readOnlyHint": True,
        "openWorldHint": True,
        "idempotentHint": True
    }
)
def search(
    query: Annotated[str, Field(
        description="The search query to execute",
        min_length=1,
        max_length=500
    )],
    max_results: Annotated[int, Field(
        description="Maximum number of results to return (default: 10, min: 1, max: 25)",
        ge=1,
        le=25
    )] = 10
) -> List[SearchResultOutput]:
    """
    Perform a general web search using SearxNG.
    
    Returns:
        List of search results with title, url, content, score
    """
    return handlers.search(query, max_results)


@mcp.tool(
    tags={"search", "video", "youtube"},
    annotations={
        "title": "YouTube Video Search",
        "readOnlyHint": True,
        "openWorldHint": True,
        "idempotentHint": True
    }
)
def search_videos(
    query: Annotated[str, Field(
        description="The video search query to execute",
        min_length=1,
        max_length=500
    )],
    max_results: Annotated[int, Field(
        description="Maximum number of results to return (default: 10, min: 1, max: 20)",
        ge=1,
        le=20
    )] = 10
) -> List[VideoSearchResultOutput]:
    """
    Search for YouTube videos using SearxNG.
    
    Returns:
        List of video results with url, title, author, content, and length
    """
    return handlers.search_videos(query, max_results)


@mcp.tool(
    name="fetch_content",
    tags={"web", "fetch", "content"},
    annotations={
        "title": "Fetch Web Content",
        "readOnlyHint": True,
        "openWorldHint": True,
        "idempotentHint": False
    }
)
async def fetch_content(
    url: Annotated[str, Field(
        description="The webpage URL to fetch content from",
        min_length=1
    )],
    offset: Annotated[int, Field(
        description="Starting position for content retrieval (default: 0, min: 0). Use 'next_offset' from previous response",
        ge=0
    )] = 0
) -> FetchContentOutput:
    """
    Fetch and parse content from a webpage URL with pagination support.
    
    Content is retrieved in chunks of 30,000 characters. If content is truncated,
    use the returned 'next_offset' value in a subsequent call to retrieve the next chunk.
    
    Returns:
        FetchContentOutput with parsed content and pagination metadata
    """
    return await handlers.fetch_content(url, offset)


@mcp.tool(
    name="fetch_youtube_content",
    tags={"youtube", "transcript", "content"},
    annotations={
        "title": "Fetch YouTube Transcript",
        "readOnlyHint": True,
        "openWorldHint": True,
        "idempotentHint": False
    }
)
def fetch_youtube_content(
    video_id: Annotated[str, Field(
        description="YouTube video ID or full URL (e.g., 'dQw4w9WgXcQ' or 'https://www.youtube.com/watch?v=dQw4w9WgXcQ')",
        min_length=1,
        max_length=200
    )]
) -> YouTubeContentOutput:
    """
    Fetch and transcribe YouTube video content using STT.
    
    Downloads the audio from a YouTube video and transcribes it using a
    speech-to-text service. Accepts either a video ID or full YouTube URL.
    
    Returns:
        YouTubeContentOutput with video_id, transcript, and metadata
    """
    return handlers.fetch_youtube_content(video_id)


@mcp.tool(
    name="fetch_subreddit",
    tags={"reddit", "subreddit", "posts"},
    annotations={
        "title": "Fetch Subreddit Posts",
        "readOnlyHint": True,
        "openWorldHint": True,
        "idempotentHint": False
    }
)
async def fetch_subreddit(
    subreddit: Annotated[str, Field(
        description="Subreddit name (without r/ prefix, e.g., 'python' or 'accelerate')",
        min_length=1,
        max_length=100
    )],
    sort: Annotated[str, Field(
        description="Sort order: hot, new, top, rising, or controversial (default: hot)"
    )] = "hot",
    time_filter: Annotated[str, Field(
        description="Time filter for top/controversial: hour, day, week, month, year, or all (optional)"
    )] = None,
    limit: Annotated[int, Field(
        description="Number of posts to fetch (default: 25, min: 1, max: 100)",
        ge=1,
        le=100
    )] = 25,
    after: Annotated[str, Field(
        description="Pagination cursor from previous response (optional)"
    )] = None
) -> SubredditPostsOutput:
    """
    Fetch posts from a subreddit using old.reddit.com API.
    
    Retrieves a list of posts with title, author, score, comments count,
    and other metadata. Supports pagination via the 'after' cursor.
    
    Returns:
        SubredditPostsOutput with posts list and pagination info
    """
    return await handlers.fetch_subreddit(
        subreddit=subreddit,
        sort=sort,
        time_filter=time_filter,
        limit=limit,
        after=after
    )


@mcp.tool(
    name="fetch_subreddit_post",
    tags={"reddit", "post", "comments"},
    annotations={
        "title": "Fetch Subreddit Post with Comments",
        "readOnlyHint": True,
        "openWorldHint": True,
        "idempotentHint": False
    }
)
async def fetch_subreddit_post(
    subreddit: Annotated[str, Field(
        description="Subreddit name (without r/ prefix, e.g., 'python')",
        min_length=1,
        max_length=100
    )],
    post_id: Annotated[str, Field(
        description="Reddit post ID (without t3_ prefix, e.g., '1p6j7ht')",
        min_length=1,
        max_length=20
    )],
    sort: Annotated[str, Field(
        description="Comment sort: confidence, top, new, controversial, old, or qa (default: confidence)"
    )] = "confidence",
    limit: Annotated[int, Field(
        description="Maximum comments to fetch (default: 100, min: 1, max: 500)",
        ge=1,
        le=500
    )] = 100,
    depth: Annotated[int, Field(
        description="Maximum reply nesting depth (optional, min: 1)"
    )] = None
) -> RedditPostOutput:
    """
    Fetch a Reddit post with its comments using old.reddit.com API.
    
    Retrieves the post content including title, body, media URLs, and all
    comments with nested replies maintaining parent-child relationships.
    
    Returns:
        RedditPostOutput with detailed post and comment tree
    """
    return await handlers.fetch_subreddit_post(
        subreddit=subreddit,
        post_id=post_id,
        sort=sort,
        limit=limit,
        depth=depth
    )


def run_server():
    """Run the MCP server with appropriate transport and configurable port.
    
    Transport priority:
    1. CLI flags (--http or --sse)
    2. Environment variable (MCP_TRANSPORT=http|sse)
    3. Default: http
    """
    parser = argparse.ArgumentParser(description="Run MCP server with configurable transport and port")
    parser.add_argument('--port', type=int, default=int(os.getenv('MCP_PORT', '3090')), 
                        help='Port number (default: 3090, or MCP_PORT env var)')
    parser.add_argument('--http', action='store_true', help='Run server with HTTP transport')
    parser.add_argument('--sse', action='store_true', help='Run server with SSE transport')
    args = parser.parse_args()

    # Determine transport: CLI flags take precedence, then env var, then default
    if args.http:
        transport = "http"
    elif args.sse:
        transport = "sse"
    else:
        transport = os.getenv('MCP_TRANSPORT', 'http').lower()
        if transport not in ('http', 'sse'):
            print(f"Warning: Invalid MCP_TRANSPORT '{transport}', defaulting to 'http'")
            transport = "http"

    print(f"Starting WebIntel MCP server on http://0.0.0.0:{args.port} with {transport.upper()} transport")
    mcp.run(transport=transport, host="0.0.0.0", port=args.port)



if __name__ == "__main__":
    run_server()
