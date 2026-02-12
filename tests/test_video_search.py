"""
Tests for video search functionality
"""

import pytest
from unittest.mock import patch, Mock, MagicMock
from src.server.handlers import SearchHandlers
from src.core.config import SearchConfig
from src.core.models import VideoSearchResult


class TestVideoSearch:
    """Test cases for video search."""

    def setup_method(self):
        """Set up test fixtures with mocked SearxNG client."""
        self.handlers = SearchHandlers()

    def _mock_video_results(self, count=3):
        """Generate mock video search results."""
        return [
            VideoSearchResult(
                title=f"Video {i}",
                url=f"https://www.youtube.com/watch?v=test{i}",
                content=f"Description for video {i}",
                published_date=None,
                duration=f"{i * 60}",
                author=f"Author {i}",
                thumbnail=None,
            )
            for i in range(count)
        ]

    def test_search_videos_basic(self):
        """Test basic video search functionality."""
        mock_results = self._mock_video_results(3)
        with patch.object(self.handlers.client, 'search_videos', return_value=mock_results):
            results = self.handlers.search_videos("python tutorial", max_results=5)

            assert isinstance(results, list)
            assert len(results) == 3

            first = results[0]
            assert hasattr(first, 'url')
            assert hasattr(first, 'title')
            assert hasattr(first, 'author')
            assert hasattr(first, 'content')
            assert hasattr(first, 'length')
            assert "youtube.com" in first.url

    def test_search_videos_max_results_validation(self):
        """Test that max_results is properly validated."""
        mock_results = self._mock_video_results(20)
        with patch.object(self.handlers.client, 'search_videos', return_value=mock_results) as mock_search:
            # Value above max should be clamped
            self.handlers.search_videos("coding", max_results=100)
            _, kwargs = mock_search.call_args
            assert kwargs.get('max_results', 0) <= SearchConfig.MAX_VIDEO_RESULTS

        mock_results_one = self._mock_video_results(1)
        with patch.object(self.handlers.client, 'search_videos', return_value=mock_results_one):
            # Value below 1 should still return results
            results = self.handlers.search_videos("coding", max_results=0)
            assert len(results) >= 1

    def test_search_videos_response_fields(self):
        """Test that all expected fields are present in response."""
        mock_results = self._mock_video_results(3)
        with patch.object(self.handlers.client, 'search_videos', return_value=mock_results):
            results = self.handlers.search_videos("machine learning", max_results=3)

            for result in results:
                assert hasattr(result, 'url')
                assert hasattr(result, 'title')
                assert hasattr(result, 'author')
                assert hasattr(result, 'content')
                assert hasattr(result, 'length')
                assert isinstance(result.url, str)
                assert isinstance(result.title, str)

    def test_search_videos_empty_query(self):
        """Test that empty query raises error."""
        from fastmcp.exceptions import ToolError
        with pytest.raises(ToolError):
            self.handlers.search_videos("", max_results=5)

    def test_search_videos_search_exception(self):
        """Test handling of search exceptions."""
        from fastmcp.exceptions import ToolError
        from src.core.config import SearchException
        with patch.object(self.handlers.client, 'search_videos', side_effect=SearchException("Connection failed")):
            with pytest.raises(ToolError, match="Video search failed"):
                self.handlers.search_videos("test query")
