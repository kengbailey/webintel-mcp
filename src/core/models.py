"""
Pydantic models for search results and API responses
"""

from typing import List, Optional, Union
from pydantic import BaseModel


# Specific data models for different search types
class GeneralSearchResult(BaseModel):
    title: str
    url: str
    content: Optional[str] = None
    score: Optional[float] = None
    category: Optional[str] = None
    author: Optional[str] = None


class VideoSearchResult(BaseModel):
    title: str
    url: str
    content: Optional[str] = None
    published_date: Optional[str] = None
    duration: Optional[Union[str, float]] = None
    author: Optional[str] = None
    thumbnail: Optional[str] = None


# Output models for MCP tools
class SearchResultOutput(BaseModel):
    """Output model for general search results."""
    title: str
    url: str
    content: Optional[str] = None
    score: float


class VideoSearchResultOutput(BaseModel):
    """Output model for video search results."""
    url: str
    title: str
    author: Optional[str] = None
    content: Optional[str] = None
    length: Optional[Union[str, float]] = None


class FetchContentOutput(BaseModel):
    """Output model for fetch_content tool."""
    content: str
    content_length: int
    is_truncated: bool
    offset: int
    next_offset: Optional[int] = None
    total_length: int
    success: bool


class YouTubeContentOutput(BaseModel):
    """Output model for fetch_youtube_content tool."""
    video_id: str
    transcript: str
    transcript_length: int
    success: bool


# Raw response model for internal use
class RawResult(BaseModel):
    url: str
    title: str
    content: Optional[str] = None
    thumbnail: Optional[str] = None
    engine: str
    template: Optional[str] = None
    parsed_url: Optional[List[str]] = None
    img_src: Optional[str] = None
    priority: Optional[str] = None
    engines: Optional[List[str]] = None
    positions: Optional[List[int]] = None
    score: Optional[float] = None
    category: Optional[str] = None
    publishedDate: Optional[str] = None
    iframe_src: Optional[str] = None
    length: Optional[Union[str, float]] = None
    duration: Optional[Union[str, float]] = None
    author: Optional[str] = None


class RawSearxngResponse(BaseModel):
    query: str
    number_of_results: int
    results: List[RawResult]
    answers: List[dict] = []
    corrections: List[str] = []
    infoboxes: List[dict] = []
    suggestions: List[str] = []
    unresponsive_engines: List[List[str]] = []


# Reddit models
class RedditPostSummary(BaseModel):
    """Summary of a Reddit post (for listings)."""
    id: str
    title: str
    author: str
    subreddit: str
    score: int
    num_comments: int
    created_utc: float
    url: str
    permalink: str
    is_self: bool
    selftext: Optional[str] = None
    thumbnail: Optional[str] = None
    link_flair_text: Optional[str] = None


class RedditComment(BaseModel):
    """A Reddit comment with metadata."""
    id: str
    author: str
    body: str
    parent_id: str  # e.g., "t3_abc123" for post, "t1_def456" for comment
    created_utc: float
    replies: List["RedditComment"] = []  # Nested replies


class RedditPostDetail(BaseModel):
    """Detailed Reddit post with content and metadata."""
    title: str
    author: str
    num_comments: int
    created_utc: float
    url: str
    is_self: bool
    selftext: Optional[str] = None
    media_urls: List[str] = []  # Extracted media/image URLs
    comments: List[RedditComment] = []


class SubredditPostsOutput(BaseModel):
    """Output model for subreddit posts listing."""
    subreddit: str
    sort: str
    time_filter: Optional[str] = None
    posts: List[RedditPostSummary]
    after_cursor: Optional[str] = None  # For pagination
    success: bool


class RedditPostOutput(BaseModel):
    """Output model for single Reddit post with comments."""
    post: RedditPostDetail
    success: bool
