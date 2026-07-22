"""
Configuration management for SearxNG search
"""

import os


class SearchConfig:
    """Configuration settings for search functionality."""
    
    # Default SearxNG host
    SEARXNG_HOST = os.getenv('SEARXNG_HOST')
    
    # Request timeout settings
    REQUEST_TIMEOUT = 10
    
    # Result limits
    MAX_GENERAL_RESULTS = 25
    MAX_VIDEO_RESULTS = 20
    MAX_SUMMARY_RESULTS = 15
    
    # Default result counts
    DEFAULT_GENERAL_RESULTS = 15
    DEFAULT_VIDEO_RESULTS = 10
    DEFAULT_SUMMARY_RESULTS = 5
    
    # Web fetching configuration
    MAX_CONTENT_LENGTH = 30000
    FETCH_TIMEOUT = 30.0
    RENDER_TIMEOUT = 30.0  # Timeout for JS rendering with Playwright (seconds)
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    
    # YouTube STT configuration
    STT_ENDPOINT = os.getenv('STT_ENDPOINT')
    STT_MODEL = os.getenv('STT_MODEL')
    STT_API_KEY = os.getenv('STT_API_KEY')
    
    # Proxy configuration (for routing fetch operations through VPN)
    # Convert empty string to None so httpx/yt-dlp use direct connection
    PROXY_URL = os.getenv('PROXY_URL') or None

    # YouTube has separate proxy control because datacenter and commercial
    # VPN exit IPs are bot-checked by YouTube (HTTP 403 / "confirm you're
    # not a bot") while residential IPs are not. Unset inherits PROXY_URL;
    # set to empty string to force a direct connection.
    YOUTUBE_PROXY_URL = (
        (os.getenv('YOUTUBE_PROXY_URL') or None)
        if 'YOUTUBE_PROXY_URL' in os.environ
        else PROXY_URL
    )

    # Reddit OAuth configuration. Reddit has separate proxy control because
    # commercial VPN exit nodes are frequently blocked by Reddit.
    REDDIT_CLIENT_ID = os.getenv('REDDIT_CLIENT_ID')
    REDDIT_CLIENT_SECRET = os.getenv('REDDIT_CLIENT_SECRET')
    REDDIT_USER_AGENT = os.getenv(
        'REDDIT_USER_AGENT',
        'python:webintel-mcp:v1.0.0'
    )
    REDDIT_PROXY_URL = os.getenv('REDDIT_PROXY_URL') or None


class SearchException(Exception):
    """Custom exception for search-related errors."""
    pass


class SearchRequestException(SearchException):
    """Exception raised when search request fails."""
    pass


class SearchParseException(SearchException):
    """Exception raised when search response parsing fails."""
    pass
