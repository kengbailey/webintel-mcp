"""
Web content fetching functionality
"""

import re
import httpx
from bs4 import BeautifulSoup
from .config import SearchConfig, SearchException
        

class WebContentFetcher:
    """Handles fetching and parsing web content."""
    
    def __init__(self):
        self.headers = {
            "User-Agent": SearchConfig.USER_AGENT
        }
    
    def _is_pdf_url(self, url: str) -> bool:
        """Check if URL points to a PDF file based on URL patterns."""
        url_lower = url.lower()
        return (
            url_lower.endswith('.pdf') or
            '.pdf?' in url_lower or
            '.pdf#' in url_lower or
            '/pdf/' in url_lower
        )

    def _is_pdf_content(self, content_type: str, content_start: bytes) -> bool:
        """Check if content is PDF based on headers and magic numbers."""
        # Check Content-Type header
        if content_type and 'application/pdf' in content_type.lower():
            return True

        # Check PDF magic numbers
        if content_start and content_start.startswith(b'%PDF'):
            return True

        return False

    async def _fetch_via_jina(self, url: str) -> tuple[str, bool]:
        """Fetch content using Jina Reader API."""
        fallback_url = f"https://r.jina.ai/{url}"
        try:
            async with httpx.AsyncClient(proxy=SearchConfig.PROXY_URL) as client:
                response = await client.get(
                        fallback_url,
                        timeout=SearchConfig.FETCH_TIMEOUT,
                    )
                response.raise_for_status()

                # Truncate if too long 
                is_truncated = False
                text = response.text
                if len(text) > SearchConfig.MAX_CONTENT_LENGTH:
                    text = text[:SearchConfig.MAX_CONTENT_LENGTH] + "... [content truncated]"
                    is_truncated = True
                
                return text, is_truncated
            
        except Exception as e:
            raise SearchException(f"Failed to fetch via Jina Reader: {e}")

    def _apply_offset_and_chunk(self, content: str, offset: int) -> tuple[str, bool, int, int]:
        """
        Apply offset and chunk the content.
        
        Args:
            content: Full content text
            offset: Starting position
            
        Returns:
            Tuple of (content_chunk, is_truncated, next_offset, total_length)
        """
        total_length = len(content)
        
        # If offset is beyond content, return empty
        if offset >= total_length:
            return "", False, total_length, total_length
        
        # Calculate end position
        end_pos = min(offset + SearchConfig.MAX_CONTENT_LENGTH, total_length)
        
        # Extract chunk
        content_chunk = content[offset:end_pos]
        
        # Determine if truncated
        is_truncated = end_pos < total_length
        
        # Calculate next offset
        next_offset = end_pos if is_truncated else total_length
        
        return content_chunk, is_truncated, next_offset, total_length
    
    async def _parse_html_content(self, html_content: str) -> str:
        """Parse HTML content and extract text."""
        try:
            soup = BeautifulSoup(html_content, "lxml")
        except Exception as e:
            soup = BeautifulSoup(html_content, "html.parser")

        # Remove script and style elements
        # TODO: evaluate more comprehensive approach
        unwanted_tags = [
            "script", "style", "nav", "header", "footer", "aside",
            "advertisement", "ads", "sidebar", "menu", "widget", "banner"
        ]
        for element in soup(unwanted_tags):
            element.decompose()

        # Get the text content
        # TODO: evaluate Readability integration
        text = soup.get_text()

        # Clean up the text
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split(" "))
        text = " ".join(chunk for chunk in chunks if chunk)

        # Remove extra whitespace
        text = re.sub(r"\s+", " ", text).strip()

        return text

    async def fetch_and_parse(self, url: str, offset: int = 0) -> tuple[str, bool, int, int]:
        """
        Fetch and parse content from a webpage or PDF.

        Args:
            url: The webpage URL to fetch content from
            offset: Starting position for content retrieval (default: 0)
            
        Returns:
            Tuple of (parsed_text, is_truncated, next_offset, total_length)

        Raises:
            SearchException: If fetching or parsing fails
        """
        try:
            # Validate offset
            if offset < 0:
                offset = 0
            
            # Check if url is a PDF
            if self._is_pdf_url(url):
                content, was_truncated = await self._fetch_via_jina(url)
                return self._apply_offset_and_chunk(content, offset)

            # request
            async with httpx.AsyncClient(proxy=SearchConfig.PROXY_URL) as client:
                response = await client.get(
                    url,
                    headers=self.headers,
                    follow_redirects=True,
                    timeout=SearchConfig.FETCH_TIMEOUT,
                )
                response.raise_for_status()
                
                # Check if the response is a PDF
                content_type = response.headers.get('content-type', '')
                content_start = response.content[:8] if response.content else b''

                if self._is_pdf_content(content_type, content_start):
                    content, was_truncated = await self._fetch_via_jina(url)
                    return self._apply_offset_and_chunk(content, offset)

                # Parse as HTML
                text = await self._parse_html_content(response.text)

                # Apply offset and chunking
                return self._apply_offset_and_chunk(text, offset)
                
        except httpx.TimeoutException:
            # Fallback to Jina Reader API for any timeout
            content, was_truncated = await self._fetch_via_jina(url)
            return self._apply_offset_and_chunk(content, offset)

        except httpx.HTTPError as e:
            # Fallback to Jina Reader API for HTTP errors
            content, was_truncated = await self._fetch_via_jina(url)
            return self._apply_offset_and_chunk(content, offset)
        except Exception as e:
            raise SearchException(f"Unexpected error while fetching content: {str(e)}")
