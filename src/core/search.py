"""
Core search functionality for SearxNG
"""

import requests
from typing import List, Optional, Union

from .models import (
    GeneralSearchResult, 
    VideoSearchResult, 
    RawSearxngResponse
)
from .config import (
    SearchConfig, 
    SearchRequestException, 
    SearchParseException
)


class SearxngClient:
    """Client for interacting with SearxNG search API."""
    
    def __init__(self, host: str = None):
        """
        Initialize the SearxNG client.
        
        Args:
            host: SearxNG server URL (uses default from config if not provided)
        """
        self.host = host or SearchConfig.SEARXNG_HOST
    
    def _search_raw(
        self, 
        query: str, 
        engines: Union[str, List[str]] = None, 
        categories: Union[str, List[str]] = None, 
        max_results: int = None
    ) -> RawSearxngResponse:
        """
        Internal method to perform raw SearxNG search.
        
        Args:
            query: The search query
            engines: Search engines to use
            categories: Search categories to use
            max_results: Maximum number of results to return
            
        Returns:
            RawSearxngResponse object with raw search data
            
        Raises:
            SearchRequestException: If the search request fails
            SearchParseException: If response parsing fails
        """
        url = f"{self.host}/search"
        params = {'q': query, 'format': 'json'}
        
        if engines:
            if isinstance(engines, list):
                params['engines'] = ','.join(engines)
            else:
                params['engines'] = engines
                
        if categories:
            if isinstance(categories, list):
                params['categories'] = ','.join(categories)
            else:
                params['categories'] = categories
        
        try:
            response = requests.get(
                url, 
                params=params, 
                timeout=SearchConfig.REQUEST_TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
            
            # Slice results if max_results is specified
            if max_results is not None and 'results' in data:
                data['results'] = data['results'][:max_results]
            
            return RawSearxngResponse(**data)
            
        except requests.exceptions.RequestException as e:
            raise SearchRequestException(f"Search request failed: {e}")
        except Exception as e:
            raise SearchParseException(f"Failed to parse search response: {e}")
    
    def search_general(
        self, 
        query: str, 
        max_results: int = None
    ) -> List[GeneralSearchResult]:
        """
        Perform a general web search and return cleaned results.
        
        Args:
            query: The search query
            max_results: Maximum number of results to return
            
        Returns:
            List of GeneralSearchResult objects
        """
        if max_results is None:
            max_results = SearchConfig.DEFAULT_GENERAL_RESULTS
        elif max_results > SearchConfig.MAX_GENERAL_RESULTS:
            max_results = SearchConfig.MAX_GENERAL_RESULTS
        
        raw_response = self._search_raw(query, max_results=max_results)
        
        results = []
        for result in raw_response.results:
            results.append(GeneralSearchResult(
                title=result.title,
                url=result.url,
                content=result.content,
                score=round(result.score, 2),
                category=result.category,
                author=result.author
            ))
        
        return results
    
    def search_videos(
        self, 
        query: str, 
        engines: str = 'youtube', 
        max_results: int = None
    ) -> List[VideoSearchResult]:
        """
        Perform a video search and return cleaned results.
        
        Args:
            query: The search query
            engines: Video engines to use (default: 'youtube')
            max_results: Maximum number of results to return
            
        Returns:
            List of VideoSearchResult objects
        """
        if max_results is None:
            max_results = SearchConfig.DEFAULT_VIDEO_RESULTS
        elif max_results > SearchConfig.MAX_VIDEO_RESULTS:
            max_results = SearchConfig.MAX_VIDEO_RESULTS
        
        raw_response = self._search_raw(
            query,
            engines=engines,
            categories='videos',
            max_results=max_results
        )
        
        results = []
        for result in raw_response.results:
            # Use length or duration, whichever is available
            duration = result.length or result.duration
            
            results.append(VideoSearchResult(
                title=result.title,
                url=result.url,
                content=result.content,
                published_date=result.publishedDate,
                duration=duration,
                author=result.author,
                thumbnail=result.img_src or result.thumbnail
            ))
        
        return results


# Convenience functions that maintain backward compatibility
def search_general(query: str, host: str = None, max_results: int = None) -> List[GeneralSearchResult]:
    """
    Perform a general web search and return cleaned results.
    
    Args:
        query: The search query
        host: SearxNG server URL
        max_results: Maximum number of results to return
        
    Returns:
        List of GeneralSearchResult objects
    """
    client = SearxngClient(host)
    return client.search_general(query, max_results)


def search_videos(query: str, host: str = None, engines: str = 'youtube', max_results: int = None) -> List[VideoSearchResult]:
    """
    Perform a video search and return cleaned results.
    
    Args:
        query: The search query
        host: SearxNG server URL
        engines: Video engines to use (default: 'youtube')
        max_results: Maximum number of results to return
        
    Returns:
        List of VideoSearchResult objects
    """
    client = SearxngClient(host)
    return client.search_videos(query, engines, max_results)
