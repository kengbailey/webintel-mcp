"""
Tests for web content fetching functionality
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch
import httpx
from src.core.web_fetcher import WebContentFetcher
from src.core.config import SearchException


class TestWebContentFetcher:
    """Test cases for WebContentFetcher."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.fetcher = WebContentFetcher()
    
    @pytest.mark.asyncio
    async def test_fetch_valid_url(self):
        """Test fetching from a valid URL."""
        # Use a reliable test URL
        url = "https://httpbin.org/html"
        
        content, is_truncated, next_offset, total_length = await self.fetcher.fetch_and_parse(url)
        
        assert isinstance(content, str)
        assert len(content) > 0
        assert "Herman Melville" in content  # httpbin.org/html contains this
        assert isinstance(is_truncated, bool)
        assert isinstance(total_length, int)
    
    @pytest.mark.asyncio
    async def test_fetch_invalid_url(self):
        """Test handling of invalid URL."""
        url = "https://this-domain-does-not-exist-12345.com"
        
        with pytest.raises(SearchException):
            await self.fetcher.fetch_and_parse(url)
    
    @pytest.mark.asyncio
    async def test_content_truncation(self):
        """Test that long content gets truncated."""
        # This test would require a reliable URL with very long content
        # For now, we can test the truncation logic by mocking or
        # using a known URL with substantial content
        pass
    
    @pytest.mark.asyncio
    async def test_content_cleaning(self):
        """Test that HTML content is properly cleaned."""
        # httpbin.org/html has known HTML structure
        url = "https://httpbin.org/html"
        
        content, is_truncated, next_offset, total_length = await self.fetcher.fetch_and_parse(url)
        
        # Should not contain HTML tags
        assert "<" not in content
        assert ">" not in content
        
        # Should contain readable text
        assert len(content.strip()) > 0
    
    @pytest.mark.asyncio
    async def test_fetch_pdf_content(self):
        """Test fetching and parsing PDF content using a real PDF URL."""        
        pdf_url = "https://s28.q4cdn.com/823357996/files/doc_financials/2025/q1/DNA-Q1-2025-10Q.pdf"
        content, is_truncated, next_offset, total_length = await self.fetcher.fetch_and_parse(pdf_url)
        
        # Basic assertions
        assert content is not None
        assert isinstance(content, str)
        assert len(content) > 0
        
        # Should contain some expected financial document content
        text_lower = content.lower()
        assert any(term in text_lower for term in ["financial", "quarterly", "revenue", "10-q"])
        
        # Check truncation flag is boolean
        assert isinstance(is_truncated, bool)
        assert isinstance(total_length, int)
    
    @pytest.mark.asyncio
    async def test_pagination_with_offset(self):
        """Test pagination with offset parameter."""
        # Use PDF that's likely to be > 30K characters
        pdf_url = "https://s28.q4cdn.com/823357996/files/doc_financials/2025/q1/DNA-Q1-2025-10Q.pdf"
        
        # Fetch first chunk
        content1, is_truncated1, next_offset1, total_length1 = await self.fetcher.fetch_and_parse(pdf_url, offset=0)
        
        if is_truncated1:
            # Fetch second chunk using next_offset
            content2, is_truncated2, next_offset2, total_length2 = await self.fetcher.fetch_and_parse(pdf_url, offset=next_offset1)
            
            # Content should be different
            assert content1 != content2
            
            # Total length should be the same
            assert total_length1 == total_length2
            
            # next_offset should have advanced
            assert next_offset2 > next_offset1
            
            # Content lengths should be reasonable
            assert len(content1) > 0
            assert len(content2) > 0
    
    @pytest.mark.asyncio
    async def test_offset_beyond_content(self):
        """Test offset beyond total content length."""
        url = "https://httpbin.org/html"
        
        # First get the total length
        _, _, _, total_length = await self.fetcher.fetch_and_parse(url)
        
        # Request with offset beyond content
        content, is_truncated, next_offset, total = await self.fetcher.fetch_and_parse(url, offset=total_length + 1000)
        
        # Should return empty content
        assert content == ""
        assert is_truncated is False
        assert next_offset == total_length
    
    @pytest.mark.asyncio
    async def test_negative_offset(self):
        """Test that negative offset is treated as 0."""
        url = "https://httpbin.org/html"
        
        # Fetch with negative offset
        content1, _, _, _ = await self.fetcher.fetch_and_parse(url, offset=-100)
        
        # Fetch with offset 0
        content2, _, _, _ = await self.fetcher.fetch_and_parse(url, offset=0)
        
        # Should be identical
        assert content1 == content2
    
    @pytest.mark.asyncio
    async def test_small_content_no_truncation(self):
        """Test that small content is not truncated."""
        url = "https://httpbin.org/html"
        
        content, is_truncated, next_offset, total_length = await self.fetcher.fetch_and_parse(url)
        
        # Small content should not be truncated
        assert is_truncated is False
        
        # next_offset should equal total_length when not truncated
        assert next_offset == total_length
        
        # Content length should match total length
        assert len(content) == total_length

    @pytest.mark.asyncio
    async def test_timeout_and_jina_failure_gives_simple_error(self):
        """When direct fetch times out and Jina also fails, error message is simplified."""
        url = "https://example.com/some-page"

        with patch("src.core.web_fetcher.httpx.AsyncClient") as mock_client_cls:
            # Make direct fetch raise TimeoutException
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get.side_effect = httpx.TimeoutException("timed out")
            mock_client_cls.return_value = mock_client

            # Make Jina fallback also fail
            with patch.object(self.fetcher, "_fetch_via_jina", side_effect=SearchException("Jina broke")):
                with pytest.raises(SearchException, match=f"Failed to fetch {url}"):
                    await self.fetcher.fetch_and_parse(url)

    @pytest.mark.asyncio
    async def test_http_error_and_jina_failure_gives_simple_error(self):
        """When direct fetch returns HTTP error and Jina also fails, error message is simplified."""
        url = "https://example.com/some-page"

        with patch("src.core.web_fetcher.httpx.AsyncClient") as mock_client_cls:
            # Make direct fetch raise HTTPError
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get.side_effect = httpx.HTTPError("503 Service Unavailable")
            mock_client_cls.return_value = mock_client

            # Make Jina fallback also fail
            with patch.object(self.fetcher, "_fetch_via_jina", side_effect=SearchException("Jina broke")):
                with pytest.raises(SearchException, match=f"Failed to fetch {url}"):
                    await self.fetcher.fetch_and_parse(url)
