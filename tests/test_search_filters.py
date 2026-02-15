"""Tests for search filter parameters (categories, time_range, language)."""

import pytest
from unittest.mock import patch, MagicMock
from src.server.handlers import SearchHandlers
from src.core.models import GeneralSearchResult, RawSearxngResponse, RawResult


def _mock_raw_response(num_results=1):
    """Create a mock SearxNG response."""
    results = []
    for i in range(num_results):
        results.append(RawResult(
            url=f"https://example.com/{i}",
            title=f"Result {i}",
            content=f"Content {i}",
            engine="google",
            score=10.0 - i
        ))
    return RawSearxngResponse(
        query="test",
        number_of_results=num_results,
        results=results
    )


class TestSearchFiltersValidation:
    """Test input validation for search filters."""

    def setup_method(self):
        self.handlers = SearchHandlers()

    def test_valid_time_range_day(self):
        """'day' should be accepted as time_range."""
        with patch.object(self.handlers.client, 'search_general', return_value=[]) as mock:
            self.handlers.search("test", time_range="day")
            mock.assert_called_once_with("test", max_results=10, categories=None, time_range="day", language=None)

    def test_valid_time_range_month(self):
        """'month' should be accepted as time_range."""
        with patch.object(self.handlers.client, 'search_general', return_value=[]) as mock:
            self.handlers.search("test", time_range="month")
            mock.assert_called_once_with("test", max_results=10, categories=None, time_range="month", language=None)

    def test_valid_time_range_year(self):
        """'year' should be accepted as time_range."""
        with patch.object(self.handlers.client, 'search_general', return_value=[]) as mock:
            self.handlers.search("test", time_range="year")
            mock.assert_called_once_with("test", max_results=10, categories=None, time_range="year", language=None)

    def test_invalid_time_range_rejected(self):
        """Invalid time_range values should raise ToolError."""
        from fastmcp.exceptions import ToolError
        with pytest.raises(ToolError, match="Invalid time_range"):
            self.handlers.search("test", time_range="week")

    def test_valid_category_general(self):
        """'general' should be accepted as category."""
        with patch.object(self.handlers.client, 'search_general', return_value=[]) as mock:
            self.handlers.search("test", categories="general")
            mock.assert_called_once_with("test", max_results=10, categories="general", time_range=None, language=None)

    def test_valid_category_news(self):
        """'news' should be accepted as category."""
        with patch.object(self.handlers.client, 'search_general', return_value=[]) as mock:
            self.handlers.search("test", categories="news")
            mock.assert_called_once()

    def test_valid_category_science(self):
        """'science' should be accepted as category."""
        with patch.object(self.handlers.client, 'search_general', return_value=[]) as mock:
            self.handlers.search("test", categories="science")
            mock.assert_called_once()

    def test_valid_category_it(self):
        """'it' should be accepted as category."""
        with patch.object(self.handlers.client, 'search_general', return_value=[]) as mock:
            self.handlers.search("test", categories="it")
            mock.assert_called_once()

    def test_valid_category_music(self):
        """'music' should be accepted as category."""
        with patch.object(self.handlers.client, 'search_general', return_value=[]) as mock:
            self.handlers.search("test", categories="music")
            mock.assert_called_once()

    def test_valid_multiple_categories(self):
        """Comma-separated categories should be accepted."""
        with patch.object(self.handlers.client, 'search_general', return_value=[]) as mock:
            self.handlers.search("test", categories="news,science")
            mock.assert_called_once_with("test", max_results=10, categories="news,science", time_range=None, language=None)

    def test_invalid_category_rejected(self):
        """Invalid category values should raise ToolError."""
        from fastmcp.exceptions import ToolError
        with pytest.raises(ToolError, match="Invalid category"):
            self.handlers.search("test", categories="invalid")

    def test_language_passed_through(self):
        """Language parameter should be passed through to backend."""
        with patch.object(self.handlers.client, 'search_general', return_value=[]) as mock:
            self.handlers.search("test", language="en")
            mock.assert_called_once_with("test", max_results=10, categories=None, time_range=None, language="en")

    def test_all_filters_combined(self):
        """All filters should work together."""
        with patch.object(self.handlers.client, 'search_general', return_value=[]) as mock:
            self.handlers.search("test", categories="news", time_range="day", language="de")
            mock.assert_called_once_with("test", max_results=10, categories="news", time_range="day", language="de")

    def test_none_filters_default(self):
        """None filters should not be sent to backend."""
        with patch.object(self.handlers.client, 'search_general', return_value=[]) as mock:
            self.handlers.search("test")
            mock.assert_called_once_with("test", max_results=10, categories=None, time_range=None, language=None)


class TestSearchBackendFilters:
    """Test that filters are correctly passed to SearxNG API."""

    def test_time_range_in_params(self):
        """time_range should be added to SearxNG request params."""
        from src.core.search import SearxngClient
        client = SearxngClient("http://localhost:8080")
        
        with patch('src.core.search.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "query": "test", "number_of_results": 0, "results": []
            }
            mock_get.return_value = mock_response
            
            client.search_general("test", time_range="day")
            
            call_args = mock_get.call_args
            params = call_args[1].get('params', call_args[0][1] if len(call_args[0]) > 1 else {})
            if not params:
                params = call_args.kwargs.get('params', {})
            assert params.get('time_range') == 'day'

    def test_language_in_params(self):
        """language should be added to SearxNG request params."""
        from src.core.search import SearxngClient
        client = SearxngClient("http://localhost:8080")
        
        with patch('src.core.search.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "query": "test", "number_of_results": 0, "results": []
            }
            mock_get.return_value = mock_response
            
            client.search_general("test", language="fr")
            
            call_args = mock_get.call_args
            params = call_args.kwargs.get('params', {})
            assert params.get('language') == 'fr'

    def test_categories_in_params(self):
        """categories should be added to SearxNG request params."""
        from src.core.search import SearxngClient
        client = SearxngClient("http://localhost:8080")
        
        with patch('src.core.search.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "query": "test", "number_of_results": 0, "results": []
            }
            mock_get.return_value = mock_response
            
            client.search_general("test", categories="science")
            
            call_args = mock_get.call_args
            params = call_args.kwargs.get('params', {})
            assert params.get('categories') == 'science'

    def test_no_filters_clean_params(self):
        """Without filters, params should only have q and format."""
        from src.core.search import SearxngClient
        client = SearxngClient("http://localhost:8080")
        
        with patch('src.core.search.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "query": "test", "number_of_results": 0, "results": []
            }
            mock_get.return_value = mock_response
            
            client.search_general("test")
            
            call_args = mock_get.call_args
            params = call_args.kwargs.get('params', {})
            assert 'time_range' not in params
            assert 'language' not in params
            assert 'categories' not in params
