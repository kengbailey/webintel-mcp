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
    RedditPostOutput,
    RedditSearchOutput,
    RedditCommentsOutput,
    SubredditInfoOutput,
)


class SearchHandlers:
    """Handlers for MCP search tools."""
    
    def __init__(self):
        self.client = SearxngClient()
        self.fetcher = WebContentFetcher()
        self.youtube_fetcher = YouTubeContentFetcher()
        self.reddit_fetcher = RedditFetcher()
    
    def search(
        self, 
        query: str, 
        max_results: int = 10,
        categories: str = None,
        time_range: str = None,
        language: str = None
    ) -> List[SearchResultOutput]:
        """
        Perform a general web search using SearxNG.
        
        Args:
            query: The search query to execute
            max_results: Maximum number of results to return (default: 10, max: 25)
            categories: Search categories (e.g., 'general', 'news', 'science', 'it', 'music')
            time_range: Time filter ('day', 'month', 'year')
            language: Language code filter (e.g., 'en', 'de', 'fr')
            
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
        
        # Validate time_range
        valid_time_ranges = ['day', 'month', 'year']
        if time_range and time_range not in valid_time_ranges:
            raise ToolError(f"Invalid time_range: '{time_range}'. Must be one of: {valid_time_ranges}")
        
        # Validate categories
        valid_categories = ['general', 'news', 'science', 'it', 'music', 'images', 'videos', 'files', 'social_media', 'map']
        if categories:
            for cat in categories.split(','):
                cat = cat.strip()
                if cat not in valid_categories:
                    raise ToolError(f"Invalid category: '{cat}'. Must be one of: {valid_categories}")
        
        try:
            # Call the search function
            results = self.client.search_general(
                query, 
                max_results=max_results,
                categories=categories,
                time_range=time_range,
                language=language
            )
            
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
    
    def _parse_reddit_comments(self, children: List[Dict], depth: int = 0, max_depth: int = 10) -> List[RedditComment]:
        """Parse Reddit comments into a flat list with depth tracking.
        
        Comments are returned as a flat list ordered by tree traversal.
        Use parent_id and depth to reconstruct the tree structure.
        
        Args:
            children: List of Reddit comment objects
            depth: Current nesting depth (internal tracker)
            max_depth: Maximum reply nesting depth to parse (default 10)
        """
        comments = []
        for child in children:
            if child.get("kind") != "t1":  # Skip non-comments
                continue
            
            comment_data = child.get("data", {})
            parent_id = comment_data.get("parent_id", "")
            
            comment = RedditComment(
                id=comment_data.get("id", ""),
                author=comment_data.get("author", "[deleted]"),
                body=comment_data.get("body", ""),
                parent_id=parent_id,
                created_utc=comment_data.get("created_utc", 0),
                depth=comment_data.get("depth", depth),
            )
            comments.append(comment)
            
            # Flatten nested replies into the same list
            replies_data = comment_data.get("replies")
            if depth + 1 < max_depth and isinstance(replies_data, dict) and replies_data.get("data", {}).get("children"):
                replies = self._parse_reddit_comments(
                    replies_data["data"]["children"],
                    depth + 1,
                    max_depth
                )
                comments.extend(replies)
        
        return comments

    def _collect_more_comment_ids(self, children: List[Dict]) -> List[str]:
        """Collect expandable comment IDs from nested Reddit `more` objects."""
        comment_ids = []
        for child in children:
            if child.get("kind") == "more":
                for comment_id in child.get("data", {}).get("children", []):
                    if comment_id and comment_id not in comment_ids:
                        comment_ids.append(comment_id)
                continue
            replies = child.get("data", {}).get("replies")
            if isinstance(replies, dict):
                nested = replies.get("data", {}).get("children", [])
                for comment_id in self._collect_more_comment_ids(nested):
                    if comment_id not in comment_ids:
                        comment_ids.append(comment_id)
        return comment_ids
    
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
    
    async def _fetch_reddit_post_by_id(
        self,
        subreddit: str | None,
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
            # Cap parse depth to prevent recursion overflow in serialization
            parse_depth = depth if depth is not None else 10
            comments = self._parse_reddit_comments(comments_listing, max_depth=parse_depth)
            
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
                comments=comments,
                id=post_data.get("id"),
                subreddit=post_data.get("subreddit"),
                score=post_data.get("score", 0),
                permalink=post_data.get("permalink"),
                more_comment_ids=self._collect_more_comment_ids(comments_listing),
            )
            
            return RedditPostOutput(
                post=post,
                success=True
            )
        except SearchException as e:
            raise ToolError(f"Failed to fetch Reddit post: {str(e)}")
        except Exception as e:
            raise ToolError(f"Unexpected error: {str(e)}")

    async def search_reddit(
        self,
        query: str,
        subreddit: str = None,
        sort: str = "relevance",
        time_filter: str = None,
        limit: int = 25,
        after: str = None,
    ) -> RedditSearchOutput:
        """Search Reddit posts globally or within a subreddit."""
        try:
            response = await self.reddit_fetcher.search_posts(
                query=query,
                subreddit=subreddit,
                sort=sort,
                time_filter=time_filter,
                limit=limit,
                after=after,
            )
            data = response.get("data", {})
            posts = [
                self._parse_reddit_post_summary(child.get("data", {}))
                for child in data.get("children", [])
                if child.get("kind") == "t3"
            ]
            return RedditSearchOutput(
                query=query,
                subreddit=subreddit,
                sort=sort,
                time_filter=time_filter,
                posts=posts,
                after_cursor=data.get("after"),
                success=True,
            )
        except SearchException as e:
            raise ToolError(f"Failed to search Reddit: {str(e)}")
        except Exception as e:
            raise ToolError(f"Unexpected error: {str(e)}")

    async def fetch_reddit_post(
        self,
        reference: str,
        sort: str = "confidence",
        limit: int = 100,
        depth: int = None,
    ) -> RedditPostOutput:
        """Fetch a post from its URL, permalink, redd.it URL, or post ID."""
        try:
            post_id, subreddit = await self.reddit_fetcher.resolve_post_reference(
                reference
            )
        except SearchException as e:
            raise ToolError(f"Invalid Reddit post reference: {str(e)}")
        return await self._fetch_reddit_post_by_id(
            subreddit=subreddit,
            post_id=post_id,
            sort=sort,
            limit=limit,
            depth=depth,
        )

    async def fetch_more_comments(
        self,
        post_id: str,
        comment_ids: List[str],
        sort: str = "confidence",
    ) -> RedditCommentsOutput:
        """Expand comment IDs from a post's `more_comment_ids` field."""
        try:
            response = await self.reddit_fetcher.fetch_more_comments(
                post_id=post_id,
                comment_ids=comment_ids,
                sort=sort,
            )
            things = response.get("json", {}).get("data", {}).get("things", [])
            return RedditCommentsOutput(
                post_id=post_id.removeprefix("t3_"),
                comments=self._parse_reddit_comments(things),
                more_comment_ids=self._collect_more_comment_ids(things),
                success=True,
            )
        except SearchException as e:
            raise ToolError(f"Failed to expand Reddit comments: {str(e)}")
        except Exception as e:
            raise ToolError(f"Unexpected error: {str(e)}")

    async def fetch_subreddit_info(self, subreddit: str) -> SubredditInfoOutput:
        """Fetch public metadata describing a subreddit."""
        try:
            response = await self.reddit_fetcher.fetch_subreddit_info(subreddit)
            data = response.get("data", {})
            return SubredditInfoOutput(
                display_name=data.get("display_name", subreddit),
                title=data.get("title", ""),
                public_description=data.get("public_description", ""),
                subscribers=data.get("subscribers"),
                active_user_count=data.get("active_user_count"),
                created_utc=data.get("created_utc"),
                over18=data.get("over18", False),
                quarantined=data.get("quarantine", False),
                subreddit_type=data.get("subreddit_type"),
                url=data.get("url", f"/r/{subreddit}/"),
                icon_img=data.get("icon_img") or None,
                banner_img=data.get("banner_img") or None,
                success=True,
            )
        except SearchException as e:
            raise ToolError(f"Failed to fetch subreddit info: {str(e)}")
        except Exception as e:
            raise ToolError(f"Unexpected error: {str(e)}")
