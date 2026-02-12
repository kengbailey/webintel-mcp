"""
Integration tests for YouTube content fetching.

These tests make real network calls and require:
- Network access to YouTube
- STT service available (set STT_ENDPOINT, STT_MODEL, STT_API_KEY env vars)

Run with: pytest tests/test_youtube_integration.py -v -m integration -s
Skip in CI with: pytest -m "not integration"
"""

import os
import pytest
from src.core.youtube_fetcher import YouTubeContentFetcher
from src.core.config import SearchException


# Skip all integration tests if no STT endpoint configured
requires_stt = pytest.mark.skipif(
    not os.getenv('STT_ENDPOINT'),
    reason="STT_ENDPOINT not set — skipping integration tests"
)


class TestYouTubeIntegration:
    """Integration test suite for real YouTube operations."""

    def setup_method(self):
        """Set up test fixtures."""
        self.fetcher = YouTubeContentFetcher()

    def test_video_id_extraction_from_various_formats(self):
        """Test video ID extraction from various YouTube URL formats (no network needed)."""
        test_cases = [
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ]

        for input_url, expected_id in test_cases:
            result = self.fetcher._extract_video_id(input_url)
            assert result == expected_id, f"Failed to extract ID from: {input_url}"

    def test_invalid_video_id_extraction(self):
        """Test that invalid URLs raise appropriate exceptions."""
        invalid_inputs = [
            "https://invalid-url.com",
            "not-a-url-at-all",
        ]

        for invalid_input in invalid_inputs:
            with pytest.raises(SearchException) as exc_info:
                self.fetcher._extract_video_id(invalid_input)
            assert "Failed to extract video ID" in str(exc_info.value)

    @requires_stt
    @pytest.mark.integration
    def test_full_fetch_and_transcribe_pipeline(self):
        """
        Full end-to-end test: download YouTube video and transcribe.

        Requires:
        - STT_ENDPOINT, STT_MODEL, STT_API_KEY env vars set
        - Network access to YouTube
        """
        # Use a short, stable video for testing
        video_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

        video_id, transcript = self.fetcher.fetch_and_transcribe(video_url)

        assert video_id == "dQw4w9WgXcQ", f"Expected 'dQw4w9WgXcQ' but got '{video_id}'"
        assert isinstance(transcript, str), "Transcript should be a string"
        assert len(transcript) > 100, f"Transcript too short ({len(transcript)} chars)"

        print(f"\n✅ Pipeline success: {len(transcript)} chars transcribed")
        print(f"   First 150 chars: {transcript[:150]}...")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration", "-s"])
