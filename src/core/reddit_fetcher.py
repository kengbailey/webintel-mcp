"""
Reddit content fetching functionality using old.reddit.com API
"""

import httpx
from typing import Optional
from .config import SearchConfig, SearchException


class RedditFetcher:
    """Handles fetching Reddit content via old.reddit.com JSON API."""
    
    BASE_URL = "https://old.reddit.com"
    
    def __init__(self):
        self.headers = {
            "User-Agent": SearchConfig.USER_AGENT
        }
    
    async def fetch_subreddit_posts(
        self,
        subreddit: str,
        sort: str = "hot",
        time_filter: Optional[str] = None,
        limit: int = 25,
        after: Optional[str] = None
    ) -> dict:
        """
        Fetch post listings from a subreddit.
        
        Args:
            subreddit: Subreddit name (without r/ prefix)
            sort: Sort order (hot, new, top, rising, controversial)
            time_filter: Time filter for top/controversial (hour, day, week, month, year, all)
            limit: Number of posts to fetch (1-100, default 25)
            after: Pagination cursor for next page
            
        Returns:
            Raw Reddit API response (Listing object)
            
        Raises:
            SearchException: If fetching fails
        """
        # Validate inputs
        valid_sorts = ["hot", "new", "top", "rising", "controversial"]
        if sort not in valid_sorts:
            raise SearchException(f"Invalid sort: {sort}. Must be one of {valid_sorts}")
        
        valid_time_filters = ["hour", "day", "week", "month", "year", "all"]
        if time_filter and time_filter not in valid_time_filters:
            raise SearchException(f"Invalid time filter: {time_filter}. Must be one of {valid_time_filters}")
        
        if limit < 1 or limit > 100:
            raise SearchException("Limit must be between 1 and 100")
        
        # Build URL
        url = f"{self.BASE_URL}/r/{subreddit}/{sort}.json"
        
        # Build query params
        params = {"limit": limit}
        if time_filter and sort in ["top", "controversial"]:
            params["t"] = time_filter
        if after:
            params["after"] = after
        
        try:
            async with httpx.AsyncClient(proxy=SearchConfig.PROXY_URL) as client:
                response = await client.get(
                    url,
                    headers=self.headers,
                    params=params,
                    follow_redirects=True,
                    timeout=SearchConfig.FETCH_TIMEOUT,
                )
                response.raise_for_status()
                return response.json()
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise SearchException(f"Subreddit not found: r/{subreddit}")
            elif e.response.status_code == 403:
                raise SearchException(f"Access forbidden to r/{subreddit} (private or banned)")
            else:
                raise SearchException(f"HTTP error {e.response.status_code}: {str(e)}")
        except httpx.TimeoutException:
            raise SearchException("Request timed out while fetching subreddit posts")
        except Exception as e:
            raise SearchException(f"Failed to fetch subreddit posts: {str(e)}")
    
    async def fetch_post_with_comments(
        self,
        subreddit: str,
        post_id: str,
        sort: str = "confidence",
        limit: int = 100,
        depth: Optional[int] = None,
        comment_id: Optional[str] = None,
        context: Optional[int] = None
    ) -> list:
        """
        Fetch a single post with comments.
        
        Args:
            subreddit: Subreddit name (without r/ prefix)
            post_id: Post ID (without t3_ prefix)
            sort: Comment sort (confidence, top, new, controversial, old, qa)
            limit: Max comments to fetch (1-500, default 100)
            depth: Max reply nesting depth (1-10+, default unlimited)
            comment_id: Focus on specific comment thread
            context: Number of parent comments to include (used with comment_id, 0-8)
            
        Returns:
            Raw Reddit API response (array with 2 Listings: [post, comments])
            
        Raises:
            SearchException: If fetching fails
        """
        # Validate inputs
        valid_sorts = ["confidence", "top", "new", "controversial", "old", "qa"]
        if sort not in valid_sorts:
            raise SearchException(f"Invalid sort: {sort}. Must be one of {valid_sorts}")
        
        if limit < 1 or limit > 500:
            raise SearchException("Limit must be between 1 and 500")
        
        if depth is not None and depth < 1:
            raise SearchException("Depth must be at least 1")
        
        if context is not None and (context < 0 or context > 8):
            raise SearchException("Context must be between 0 and 8")
        
        # Build URL - need to get the slug from the post first or use a generic path
        # Reddit is flexible with the slug, so we can use a placeholder
        url = f"{self.BASE_URL}/r/{subreddit}/comments/{post_id}.json"
        
        # Build query params
        params = {
            "sort": sort,
            "limit": limit
        }
        if depth is not None:
            params["depth"] = depth
        if comment_id:
            params["comment"] = comment_id
        if context is not None and comment_id:
            params["context"] = context
        
        try:
            async with httpx.AsyncClient(proxy=SearchConfig.PROXY_URL) as client:
                response = await client.get(
                    url,
                    headers=self.headers,
                    params=params,
                    follow_redirects=True,
                    timeout=SearchConfig.FETCH_TIMEOUT,
                )
                response.raise_for_status()
                return response.json()
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise SearchException(f"Post not found: {post_id} in r/{subreddit}")
            elif e.response.status_code == 403:
                raise SearchException(f"Access forbidden to post or subreddit")
            else:
                raise SearchException(f"HTTP error {e.response.status_code}: {str(e)}")
        except httpx.TimeoutException:
            raise SearchException("Request timed out while fetching post")
        except Exception as e:
            raise SearchException(f"Failed to fetch post: {str(e)}")
