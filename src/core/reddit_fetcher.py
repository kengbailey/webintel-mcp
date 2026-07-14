"""Reddit content fetching using Reddit's OAuth Data API."""

import asyncio
import time
from typing import Optional

import httpx

from .config import SearchConfig, SearchException


class RedditFetcher:
    """Handles fetching Reddit content via the OAuth Data API."""
    
    BASE_URL = "https://oauth.reddit.com"
    TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
    TOKEN_EXPIRY_MARGIN = 60
    
    def __init__(self):
        self.headers = {
            "User-Agent": SearchConfig.REDDIT_USER_AGENT
        }
        self._access_token: Optional[str] = None
        self._token_expires_at = 0.0
        self._token_lock = asyncio.Lock()

    def _validate_credentials(self) -> None:
        if not SearchConfig.REDDIT_CLIENT_ID or not SearchConfig.REDDIT_CLIENT_SECRET:
            raise SearchException(
                "Reddit OAuth is not configured. Set REDDIT_CLIENT_ID and "
                "REDDIT_CLIENT_SECRET."
            )

    async def _get_access_token(self, force_refresh: bool = False) -> str:
        """Return a cached application-only OAuth token."""
        self._validate_credentials()
        now = time.monotonic()
        if not force_refresh and self._access_token and now < self._token_expires_at:
            return self._access_token

        async with self._token_lock:
            now = time.monotonic()
            if not force_refresh and self._access_token and now < self._token_expires_at:
                return self._access_token

            try:
                async with httpx.AsyncClient(proxy=SearchConfig.REDDIT_PROXY_URL) as client:
                    response = await client.post(
                        self.TOKEN_URL,
                        auth=(
                            SearchConfig.REDDIT_CLIENT_ID,
                            SearchConfig.REDDIT_CLIENT_SECRET,
                        ),
                        headers=self.headers,
                        data={"grant_type": "client_credentials"},
                        timeout=SearchConfig.FETCH_TIMEOUT,
                    )
                    response.raise_for_status()
                    payload = response.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    raise SearchException(
                        "Reddit rejected the OAuth client ID or client secret"
                    )
                raise SearchException(
                    f"Reddit OAuth token request failed with HTTP {e.response.status_code}"
                )
            except httpx.TimeoutException:
                raise SearchException("Reddit OAuth token request timed out")
            except httpx.HTTPError as e:
                raise SearchException(f"Reddit OAuth token request failed: {e}")

            token = payload.get("access_token")
            if not token:
                raise SearchException("Reddit OAuth response did not contain an access token")

            expires_in = max(int(payload.get("expires_in", 3600)), 0)
            self._access_token = token
            self._token_expires_at = time.monotonic() + max(
                expires_in - self.TOKEN_EXPIRY_MARGIN, 0
            )
            return token

    async def _get(self, url: str, params: dict) -> httpx.Response:
        """Make an authenticated request, refreshing once if the token expired."""
        for attempt in range(2):
            token = await self._get_access_token(force_refresh=attempt == 1)
            headers = {**self.headers, "Authorization": f"bearer {token}"}
            async with httpx.AsyncClient(proxy=SearchConfig.REDDIT_PROXY_URL) as client:
                response = await client.get(
                    url,
                    headers=headers,
                    params=params,
                    follow_redirects=True,
                    timeout=SearchConfig.FETCH_TIMEOUT,
                )
            if response.status_code != 401 or attempt == 1:
                response.raise_for_status()
                return response

            self._access_token = None
            self._token_expires_at = 0.0

        raise SearchException("Reddit authentication failed")

    @staticmethod
    def _rate_limit_message(response: httpx.Response) -> str:
        retry_after = response.headers.get("retry-after")
        reset = response.headers.get("x-ratelimit-reset")
        wait = retry_after or reset
        if wait:
            return f"Reddit rate limit exceeded; retry in {wait} seconds"
        return "Reddit rate limit exceeded; retry later"
    
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
            response = await self._get(url, params)
            return response.json()
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise SearchException(f"Subreddit not found: r/{subreddit}")
            elif e.response.status_code == 403:
                raise SearchException(
                    f"Reddit denied access to r/{subreddit}; it may be private, banned, "
                    "or unavailable to this OAuth application"
                )
            elif e.response.status_code == 429:
                raise SearchException(self._rate_limit_message(e.response))
            else:
                raise SearchException(f"HTTP error {e.response.status_code}: {str(e)}")
        except httpx.TimeoutException:
            raise SearchException("Request timed out while fetching subreddit posts")
        except SearchException:
            raise
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
            response = await self._get(url, params)
            return response.json()
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise SearchException(f"Post not found: {post_id} in r/{subreddit}")
            elif e.response.status_code == 403:
                raise SearchException(
                    "Reddit denied access to the post; it may be private, banned, "
                    "or unavailable to this OAuth application"
                )
            elif e.response.status_code == 429:
                raise SearchException(self._rate_limit_message(e.response))
            else:
                raise SearchException(f"HTTP error {e.response.status_code}: {str(e)}")
        except httpx.TimeoutException:
            raise SearchException("Request timed out while fetching post")
        except SearchException:
            raise
        except Exception as e:
            raise SearchException(f"Failed to fetch post: {str(e)}")
