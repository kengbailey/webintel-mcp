"""
MCP tool handlers for search functionality
"""

from typing import List, Dict, Any
from fastmcp.exceptions import ToolError
from ..core.search import SearxngClient
from ..core.web_fetcher import WebContentFetcher
from ..core.youtube_fetcher import YouTubeContentFetcher
from ..core.reddit_fetcher import RedditFetcher
from ..core.config import SearchConfig, SearchException
from ..core.models import (
    SearchResultOutput, 
    VideoSearchResultOutput, 
    FetchContentOutput, 
    YouTubeContentOutput,
    RedditPostSummary,
    RedditComment,
    RedditPostDetail,
    SubredditPostsOutput,
    RedditPostOutput
)


class SearchHandlers:
    """Handlers for MCP search tools."""
    
    def __init__(self):
        self.client = SearxngClient()
        self.fetcher = WebContentFetcher()
        self.youtube_fetcher = YouTubeContentFetcher()
        self.reddit_fetcher = RedditFetcher()
    
    def search(self, query: str, max_results: int = 10) -> List[SearchResultOutput]:
        """
        Perform a general web search using SearxNG.
        
        Args:
            query: The search query to execute
            max_results: Maximum number of results to return (default: 10, max: 25)
            
        Returns:
            List of search results with title, url, content, score
        """
        # Validate query
        if not query or not query.strip():
            raise ToolError("Search query cannot be empty")
        
        # Validate max_results
        if max_results > SearchConfig.MAX_GENERAL_RESULTS:
            max_results = SearchConfig.MAX_GENERAL_RESULTS
        elif max_results < 1:
            max_results = 1
        
        try:
            # Call the search function
            results = self.client.search_general(query, max_results=max_results)
            
            # Convert to output models
            return [
                SearchResultOutput(
                    title=result.title,
                    url=result.url,
                    content=result.content,
                    score=result.score or 0.0,
                )
                for result in results
            ]
        except SearchException as e:
            raise ToolError(f"Search failed: {str(e)}")
        except Exception as e:
            raise ToolError(f"Unexpected error: {str(e)}")
    
    def search_videos(self, query: str, max_results: int = 10) -> List[VideoSearchResultOutput]:
        """
        Search for YouTube videos using SearxNG.
        
        Args:
            query: The search query to execute
            max_results: Maximum number of results to return (default: 10, max: 20)
            
        Returns:
            List of video results with url, title, author, content, and length
        """
        # Validate query
        if not query or not query.strip():
            raise ToolError("Video search query cannot be empty")
        
        # Validate max_results
        if max_results > SearchConfig.MAX_VIDEO_RESULTS:
            max_results = SearchConfig.MAX_VIDEO_RESULTS
        elif max_results < 1:
            max_results = 1
        
        try:
            # Call the video search function (YouTube only)
            results = self.client.search_videos(query, engines='youtube', max_results=max_results)
            
            # Convert to output models
            return [
                VideoSearchResultOutput(
                    url=result.url,
                    title=result.title,
                    author=result.author,
                    content=result.content,
                    length=result.duration,
                )
                for result in results
            ]
        except SearchException as e:
            raise ToolError(f"Video search failed: {str(e)}")
        except Exception as e:
            raise ToolError(f"Unexpected error: {str(e)}")
    
    async def fetch_content(self, url: str, offset: int = 0) -> FetchContentOutput:
        """
        Fetch and parse content from a webpage URL with pagination support.
        
        Args:
            url: The webpage URL to fetch content from
            offset: Starting position for content retrieval (default: 0)
            
        Returns:
            FetchContentOutput containing the parsed content and pagination metadata
        """
        # Validate URL
        if not url or not url.strip():
            raise ToolError("URL cannot be empty")
        
        try:
            content, is_truncated, next_offset, total_length = await self.fetcher.fetch_and_parse(url, offset)
            return FetchContentOutput(
                content=content,
                content_length=len(content),
                is_truncated=is_truncated,
                offset=offset,
                next_offset=next_offset if is_truncated else None,
                total_length=total_length,
                success=True
            )
        except SearchException as e:
            raise ToolError(f"Failed to fetch content: {str(e)}")
        except Exception as e:
            raise ToolError(f"Unexpected error: {str(e)}")
    
    def fetch_youtube_content(self, video_id: str) -> YouTubeContentOutput:
        """
        Fetch and transcribe YouTube video content.
        
        Args:
            video_id: YouTube video ID or full URL
            
        Returns:
            YouTubeContentOutput containing the video ID and transcript
        """
        # Validate video_id
        if not video_id or not video_id.strip():
            raise ToolError("Video ID or URL cannot be empty")
        
        try:
            vid_id, transcript = self.youtube_fetcher.fetch_and_transcribe(video_id)
            return YouTubeContentOutput(
                video_id=vid_id,
                transcript=transcript,
                transcript_length=len(transcript),
                success=True
            )
        except SearchException as e:
            raise ToolError(f"Failed to fetch YouTube content: {str(e)}")
        except Exception as e:
            raise ToolError(f"Unexpected error: {str(e)}")
    
    def _parse_reddit_post_summary(self, post_data: Dict[str, Any]) -> RedditPostSummary:
        """Parse Reddit post data into a RedditPostSummary model."""
        return RedditPostSummary(
            id=post_data["id"],
            title=post_data["title"],
            author=post_data.get("author", "[deleted]"),
            subreddit=post_data["subreddit"],
            score=post_data.get("score", 0),
            num_comments=post_data.get("num_comments", 0),
            created_utc=post_data.get("created_utc", 0),
            url=post_data["url"],
            permalink=post_data["permalink"],
            is_self=post_data.get("is_self", False),
            selftext=post_data.get("selftext") if post_data.get("selftext") else None,
            thumbnail=post_data.get("thumbnail") if post_data.get("thumbnail") and post_data.get("thumbnail") != "self" and post_data.get("thumbnail") != "default" else None,
            link_flair_text=post_data.get("link_flair_text")
        )
    
    def _parse_reddit_comments(self, children: List[Dict], depth: int = 0) -> List[RedditComment]:
        """Recursively parse Reddit comments."""
        comments = []
        for child in children:
            if child.get("kind") != "t1":  # Skip non-comments
                continue
            
            comment_data = child.get("data", {})
            
            # Parse parent_id and determine parent_type
            parent_id = comment_data.get("parent_id", "")
            parent_type = "post" if parent_id.startswith("t3_") else "comment"
            
            # Parse replies
            replies_data = comment_data.get("replies")
            replies = []
            if isinstance(replies_data, dict) and replies_data.get("data", {}).get("children"):
                replies = self._parse_reddit_comments(
                    replies_data["data"]["children"],
                    depth + 1
                )
            
            comment = RedditComment(
                id=comment_data.get("id", ""),
                author=comment_data.get("author", "[deleted]"),
                body=comment_data.get("body", ""),
                parent_id=parent_id,
                created_utc=comment_data.get("created_utc", 0),
                replies=replies
            )
            comments.append(comment)
        
        return comments
    
    def _extract_media_urls(self, post_data: Dict[str, Any]) -> List[str]:
        """Extract media URLs from Reddit post data."""
        media_urls = []
        
        # Check for direct image/video URL
        url = post_data.get("url", "")
        if url and any(url.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4"]):
            media_urls.append(url)
        
        # Check for gallery/media metadata
        if post_data.get("is_gallery") and "media_metadata" in post_data:
            for media_id, media_info in post_data["media_metadata"].items():
                if "s" in media_info and "u" in media_info["s"]:
                    media_urls.append(media_info["s"]["u"].replace("&amp;", "&"))
        
        # Check for preview images
        if "preview" in post_data and "images" in post_data["preview"]:
            for image in post_data["preview"]["images"]:
                if "source" in image and "url" in image["source"]:
                    media_urls.append(image["source"]["url"].replace("&amp;", "&"))
        
        return media_urls
    
    async def fetch_subreddit(
        self,
        subreddit: str,
        sort: str = "hot",
        time_filter: str = None,
        limit: int = 25,
        after: str = None
    ) -> SubredditPostsOutput:
        """
        Fetch posts from a subreddit.
        
        Args:
            subreddit: Subreddit name (without r/ prefix)
            sort: Sort order (hot, new, top, rising, controversial)
            time_filter: Time filter for top/controversial (hour, day, week, month, year, all)
            limit: Number of posts to fetch (1-100)
            after: Pagination cursor
            
        Returns:
            SubredditPostsOutput with posts and pagination info
        """
        try:
            response = await self.reddit_fetcher.fetch_subreddit_posts(
                subreddit=subreddit,
                sort=sort,
                time_filter=time_filter,
                limit=limit,
                after=after
            )
            
            # Parse response
            data = response.get("data", {})
            children = data.get("children", [])
            after_cursor = data.get("after")
            
            # Convert to post summaries
            posts = []
            for child in children:
                if child.get("kind") == "t3":  # Post
                    post_data = child.get("data", {})
                    posts.append(self._parse_reddit_post_summary(post_data))
            
            return SubredditPostsOutput(
                subreddit=subreddit,
                sort=sort,
                time_filter=time_filter,
                posts=posts,
                after_cursor=after_cursor,
                success=True
            )
        except SearchException as e:
            raise ToolError(f"Failed to fetch subreddit posts: {str(e)}")
        except Exception as e:
            raise ToolError(f"Unexpected error: {str(e)}")
    
    async def fetch_subreddit_post(
        self,
        subreddit: str,
        post_id: str,
        sort: str = "confidence",
        limit: int = 100,
        depth: int = None
    ) -> RedditPostOutput:
        """
        Fetch a Reddit post with comments.
        
        Args:
            subreddit: Subreddit name (without r/ prefix)
            post_id: Post ID (without t3_ prefix)
            sort: Comment sort (confidence, top, new, controversial, old, qa)
            limit: Max comments to fetch (1-500)
            depth: Max reply nesting depth
            
        Returns:
            RedditPostOutput with post and comments
        """
        try:
            response = await self.reddit_fetcher.fetch_post_with_comments(
                subreddit=subreddit,
                post_id=post_id,
                sort=sort,
                limit=limit,
                depth=depth
            )
            
            # Reddit returns [post_listing, comments_listing]
            if len(response) != 2:
                raise ToolError("Invalid Reddit API response format")
            
            # Parse post
            post_listing = response[0].get("data", {}).get("children", [])
            if not post_listing or post_listing[0].get("kind") != "t3":
                raise ToolError("Post not found in response")
            
            post_data = post_listing[0].get("data", {})
            
            # Parse comments
            comments_listing = response[1].get("data", {}).get("children", [])
            comments = self._parse_reddit_comments(comments_listing)
            
            # Extract media URLs
            media_urls = self._extract_media_urls(post_data)
            
            # Create detailed post
            post = RedditPostDetail(
                title=post_data["title"],
                author=post_data.get("author", "[deleted]"),
                num_comments=post_data.get("num_comments", 0),
                created_utc=post_data.get("created_utc", 0),
                url=post_data["url"],
                is_self=post_data.get("is_self", False),
                selftext=post_data.get("selftext") if post_data.get("selftext") else None,
                media_urls=media_urls,
                comments=comments
            )
            
            return RedditPostOutput(
                post=post,
                success=True
            )
        except SearchException as e:
            raise ToolError(f"Failed to fetch Reddit post: {str(e)}")
        except Exception as e:
            raise ToolError(f"Unexpected error: {str(e)}")
