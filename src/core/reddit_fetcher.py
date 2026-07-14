"""Reddit content fetching using Reddit's OAuth Data API."""

import asyncio
import re
import time
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx

from .config import SearchConfig, SearchException


class RedditFetcher:
    """Handles fetching Reddit content via the OAuth Data API."""
    
    BASE_URL = "https://oauth.reddit.com"
    TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
    TOKEN_EXPIRY_MARGIN = 60
    SUBREDDIT_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,100}$")
    POST_ID_PATTERN = re.compile(r"^[a-z0-9]{1,12}$", re.IGNORECASE)
    
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

    @classmethod
    def _validate_subreddit(cls, subreddit: str) -> str:
        subreddit = subreddit.removeprefix("r/").strip()
        if not cls.SUBREDDIT_PATTERN.fullmatch(subreddit):
            raise SearchException("Invalid subreddit name")
        return subreddit

    @classmethod
    def parse_post_reference(cls, reference: str) -> tuple[str, Optional[str]]:
        """Extract a post ID and optional subreddit from a Reddit URL or ID."""
        reference = reference.strip()
        plain_id = reference.removeprefix("t3_")
        if cls.POST_ID_PATTERN.fullmatch(plain_id):
            return plain_id.lower(), None

        if reference.startswith("/"):
            reference = f"https://www.reddit.com{reference}"
        parsed = urlparse(reference)
        host = (parsed.hostname or "").lower()
        is_reddit_host = host == "reddit.com" or host.endswith(".reddit.com")
        if (
            parsed.scheme not in {"http", "https"}
            or (not is_reddit_host and host != "redd.it")
        ):
            raise SearchException("Expected a Reddit post URL, redd.it URL, or post ID")

        parts = [part for part in parsed.path.split("/") if part]
        subreddit = None
        post_id = None
        if host == "redd.it" and parts:
            post_id = parts[0]
        elif "comments" in parts:
            comments_index = parts.index("comments")
            if comments_index + 1 < len(parts):
                post_id = parts[comments_index + 1]
            if comments_index >= 2 and parts[comments_index - 2].lower() == "r":
                subreddit = cls._validate_subreddit(parts[comments_index - 1])

        if not post_id or not cls.POST_ID_PATTERN.fullmatch(post_id):
            raise SearchException("Could not find a valid post ID in the Reddit URL")
        return post_id.lower(), subreddit

    async def resolve_post_reference(self, reference: str) -> tuple[str, Optional[str]]:
        """Resolve canonical references directly and Reddit share URLs via redirects."""
        try:
            return self.parse_post_reference(reference)
        except SearchException as e:
            parse_error = e

        share_url = reference.strip()
        if share_url.startswith("/"):
            share_url = f"https://www.reddit.com{share_url}"
        parsed = urlparse(share_url)
        host = (parsed.hostname or "").lower()
        parts = [part for part in parsed.path.split("/") if part]
        is_reddit_host = host == "reddit.com" or host.endswith(".reddit.com")
        is_share_url = (
            parsed.scheme in {"http", "https"}
            and is_reddit_host
            and len(parts) >= 4
            and parts[0].lower() == "r"
            and parts[2].lower() == "s"
        )
        if not is_share_url:
            raise parse_error

        try:
            async with httpx.AsyncClient(proxy=SearchConfig.REDDIT_PROXY_URL) as client:
                for _ in range(5):
                    response = await client.get(
                        share_url,
                        headers=self.headers,
                        follow_redirects=False,
                        timeout=SearchConfig.FETCH_TIMEOUT,
                    )
                    location = response.headers.get("location")
                    if not response.is_redirect or not location:
                        response.raise_for_status()
                        break

                    share_url = urljoin(str(response.url), location)
                    try:
                        return self.parse_post_reference(share_url)
                    except SearchException:
                        redirect = urlparse(share_url)
                        redirect_host = (redirect.hostname or "").lower()
                        if not (
                            redirect.scheme in {"http", "https"}
                            and (
                                redirect_host == "reddit.com"
                                or redirect_host.endswith(".reddit.com")
                            )
                        ):
                            raise SearchException(
                                "Reddit share URL redirected outside Reddit"
                            )
        except httpx.TimeoutException:
            raise SearchException("Reddit share URL resolution timed out")
        except httpx.HTTPStatusError as e:
            raise SearchException(
                f"Reddit share URL resolution failed with HTTP {e.response.status_code}"
            )
        except httpx.HTTPError as e:
            raise SearchException(f"Reddit share URL resolution failed: {e}")

        raise SearchException("Reddit share URL did not resolve to a post")

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
        subreddit = self._validate_subreddit(subreddit)
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
        subreddit: Optional[str],
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
            subreddit: Optional subreddit name (without r/ prefix)
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
        if subreddit:
            subreddit = self._validate_subreddit(subreddit)
        post_id = post_id.removeprefix("t3_").lower()
        if not self.POST_ID_PATTERN.fullmatch(post_id):
            raise SearchException("Invalid Reddit post ID")
        valid_sorts = ["confidence", "top", "new", "controversial", "old", "qa"]
        if sort not in valid_sorts:
            raise SearchException(f"Invalid sort: {sort}. Must be one of {valid_sorts}")
        
        if limit < 1 or limit > 500:
            raise SearchException("Limit must be between 1 and 500")
        
        if depth is not None and depth < 1:
            raise SearchException("Depth must be at least 1")
        
        if context is not None and (context < 0 or context > 8):
            raise SearchException("Context must be between 0 and 8")
        
        path = f"/r/{subreddit}/comments/{post_id}.json" if subreddit else f"/comments/{post_id}.json"
        url = f"{self.BASE_URL}{path}"
        
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

    async def search_posts(
        self,
        query: str,
        subreddit: Optional[str] = None,
        sort: str = "relevance",
        time_filter: Optional[str] = None,
        limit: int = 25,
        after: Optional[str] = None,
    ) -> dict:
        """Search public Reddit posts globally or within one subreddit."""
        query = query.strip()
        if not query:
            raise SearchException("Reddit search query cannot be empty")
        if len(query) > 500:
            raise SearchException("Reddit search query cannot exceed 500 characters")
        valid_sorts = ["relevance", "hot", "top", "new", "comments"]
        if sort not in valid_sorts:
            raise SearchException(f"Invalid search sort: {sort}. Must be one of {valid_sorts}")
        valid_time_filters = ["hour", "day", "week", "month", "year", "all"]
        if time_filter and time_filter not in valid_time_filters:
            raise SearchException(
                f"Invalid time filter: {time_filter}. Must be one of {valid_time_filters}"
            )
        if limit < 1 or limit > 100:
            raise SearchException("Limit must be between 1 and 100")

        if subreddit:
            subreddit = self._validate_subreddit(subreddit)
            url = f"{self.BASE_URL}/r/{subreddit}/search.json"
        else:
            url = f"{self.BASE_URL}/search.json"
        params = {"q": query, "sort": sort, "limit": limit, "raw_json": 1}
        if subreddit:
            params["restrict_sr"] = "on"
        if time_filter:
            params["t"] = time_filter
        if after:
            params["after"] = after

        try:
            response = await self._get(url, params)
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise SearchException(self._rate_limit_message(e.response))
            raise SearchException(f"Reddit search failed with HTTP {e.response.status_code}")
        except httpx.TimeoutException:
            raise SearchException("Reddit search request timed out")

    async def fetch_more_comments(
        self,
        post_id: str,
        comment_ids: list[str],
        sort: str = "confidence",
    ) -> dict:
        """Expand comment IDs returned in a thread's `more` placeholders."""
        post_id = post_id.removeprefix("t3_").lower()
        if not self.POST_ID_PATTERN.fullmatch(post_id):
            raise SearchException("Invalid Reddit post ID")
        if not comment_ids or len(comment_ids) > 100:
            raise SearchException("comment_ids must contain between 1 and 100 IDs")
        clean_ids = []
        for comment_id in comment_ids:
            clean_id = comment_id.removeprefix("t1_").lower()
            if not self.POST_ID_PATTERN.fullmatch(clean_id):
                raise SearchException(f"Invalid Reddit comment ID: {comment_id}")
            if clean_id not in clean_ids:
                clean_ids.append(clean_id)
        valid_sorts = ["confidence", "top", "new", "controversial", "old", "qa"]
        if sort not in valid_sorts:
            raise SearchException(f"Invalid comment sort: {sort}. Must be one of {valid_sorts}")

        params = {
            "api_type": "json",
            "link_id": f"t3_{post_id}",
            "children": ",".join(clean_ids),
            "sort": sort,
            "limit_children": "false",
            "raw_json": 1,
        }
        try:
            response = await self._get(f"{self.BASE_URL}/api/morechildren", params)
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise SearchException(self._rate_limit_message(e.response))
            raise SearchException(
                f"Reddit comment expansion failed with HTTP {e.response.status_code}"
            )
        except httpx.TimeoutException:
            raise SearchException("Reddit comment expansion timed out")

    async def fetch_subreddit_info(self, subreddit: str) -> dict:
        """Fetch public metadata for a subreddit."""
        subreddit = self._validate_subreddit(subreddit)
        try:
            response = await self._get(
                f"{self.BASE_URL}/r/{subreddit}/about.json",
                {"raw_json": 1},
            )
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise SearchException(f"Subreddit not found: r/{subreddit}")
            if e.response.status_code == 403:
                raise SearchException(f"Reddit denied access to r/{subreddit}")
            if e.response.status_code == 429:
                raise SearchException(self._rate_limit_message(e.response))
            raise SearchException(
                f"Subreddit metadata request failed with HTTP {e.response.status_code}"
            )
        except httpx.TimeoutException:
            raise SearchException("Subreddit metadata request timed out")
