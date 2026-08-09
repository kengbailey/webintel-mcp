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
        """Test fetching from a valid URL returns Markdown content."""
        url = "https://httpbin.org/html"

        content, is_truncated, next_offset, total_length = await self.fetcher.fetch_and_parse(url)

        assert isinstance(content, str)
        assert len(content) > 0
        # httpbin.org/html contains a Moby Dick excerpt
        assert any(term in content for term in ["Herman Melville", "Availing", "blacksmith"])
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
        pass

    @pytest.mark.asyncio
    async def test_content_is_markdown(self):
        """Test that content is returned as Markdown, not plain text with tags stripped."""
        url = "https://httpbin.org/html"

        content, is_truncated, next_offset, total_length = await self.fetcher.fetch_and_parse(url)

        assert len(content.strip()) > 0
        assert "<script" not in content
        assert "<style" not in content

    @pytest.mark.asyncio
    async def test_fetch_pdf_content(self):
        """Test fetching and parsing PDF content using a real PDF URL."""
        pdf_url = "https://s28.q4cdn.com/823357996/files/doc_financials/2025/q1/DNA-Q1-2025-10Q.pdf"
        content, is_truncated, next_offset, total_length = await self.fetcher.fetch_and_parse(pdf_url)

        assert content is not None
        assert isinstance(content, str)
        assert len(content) > 0

        text_lower = content.lower()
        assert any(term in text_lower for term in ["financial", "quarterly", "revenue", "10-q"])

        assert isinstance(is_truncated, bool)
        assert isinstance(total_length, int)

    @pytest.mark.asyncio
    async def test_pagination_with_offset(self):
        """Test pagination with offset parameter."""
        pdf_url = "https://s28.q4cdn.com/823357996/files/doc_financials/2025/q1/DNA-Q1-2025-10Q.pdf"

        content1, is_truncated1, next_offset1, total_length1 = await self.fetcher.fetch_and_parse(pdf_url, offset=0)

        if is_truncated1:
            content2, is_truncated2, next_offset2, total_length2 = await self.fetcher.fetch_and_parse(pdf_url, offset=next_offset1)

            assert content1 != content2
            assert total_length1 == total_length2
            assert next_offset2 > next_offset1
            assert len(content1) > 0
            assert len(content2) > 0

    @pytest.mark.asyncio
    async def test_offset_beyond_content(self):
        """Test offset beyond total content length."""
        url = "https://httpbin.org/html"

        _, _, _, total_length = await self.fetcher.fetch_and_parse(url)

        content, is_truncated, next_offset, total = await self.fetcher.fetch_and_parse(url, offset=total_length + 1000)

        assert content == ""
        assert is_truncated is False
        assert next_offset == total_length

    @pytest.mark.asyncio
    async def test_negative_offset(self):
        """Test that negative offset is treated as 0."""
        url = "https://httpbin.org/html"

        content1, _, _, _ = await self.fetcher.fetch_and_parse(url, offset=-100)
        content2, _, _, _ = await self.fetcher.fetch_and_parse(url, offset=0)

        assert content1 == content2

    @pytest.mark.asyncio
    async def test_small_content_no_truncation(self):
        """Test that small content is not truncated."""
        url = "https://httpbin.org/html"

        content, is_truncated, next_offset, total_length = await self.fetcher.fetch_and_parse(url)

        assert is_truncated is False
        assert next_offset == total_length
        assert len(content) == total_length

    @pytest.mark.asyncio
    async def test_timeout_and_jina_failure_gives_simple_error(self):
        """When direct fetch times out and Jina also fails, error message is simplified."""
        url = "https://example.com/some-page"

        with patch("src.core.web_fetcher.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get.side_effect = httpx.TimeoutException("timed out")
            mock_client_cls.return_value = mock_client

            with patch.object(self.fetcher, "_fetch_via_jina", side_effect=SearchException("Jina broke")):
                with pytest.raises(SearchException, match=f"Failed to fetch {url}"):
                    await self.fetcher.fetch_and_parse(url)

    @pytest.mark.asyncio
    async def test_http_error_and_jina_failure_gives_simple_error(self):
        """When direct fetch returns HTTP error and Jina also fails, error message is simplified."""
        url = "https://example.com/some-page"

        with patch("src.core.web_fetcher.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get.side_effect = httpx.HTTPError("503 Service Unavailable")
            mock_client_cls.return_value = mock_client

            with patch.object(self.fetcher, "_fetch_via_jina", side_effect=SearchException("Jina broke")):
                with pytest.raises(SearchException, match=f"Failed to fetch {url}"):
                    await self.fetcher.fetch_and_parse(url)

    @pytest.mark.asyncio
    async def test_trafilatura_fallback_on_empty(self):
        """Test fallback chain when primary trafilatura extraction returns None."""
        minimal_html = "<html><body><p>Short text.</p></body></html>"

        with patch("src.core.web_fetcher.trafilatura.extract", return_value=None):
            text = self.fetcher._parse_html_content(minimal_html)
            assert isinstance(text, str)

    def test_security_interstitial_detection(self):
        """Recognize Bunny Shield HTML and extracted verification text."""
        bunny_html = """
        <html>
            <script src="/.bunny-shield/assets/shield-challenge.js"></script>
            <body>We are checking your browser to establish a secure connection.</body>
        </html>
        """
        jina_text = """
        ## Performing security verification

        This website uses a security service to protect against malicious bots.
        """

        assert self.fetcher._is_security_interstitial(bunny_html) is True
        assert self.fetcher._is_security_interstitial(jina_text) is True

    def test_security_interstitial_detection_ignores_normal_noscript_text(self):
        """Do not reject ordinary pages that merely recommend enabling JS."""
        content = "JavaScript is disabled. For a better experience, please enable JavaScript."

        assert self.fetcher._is_security_interstitial(content) is False

    # --- Auto JS rendering fallback tests ---

    @pytest.mark.asyncio
    async def test_new_browser_page_uses_non_automation_profile(self):
        """Browser fallback should not advertise Playwright's default profile."""
        browser = AsyncMock()
        browser.version = "149.0.7827.0"
        page = AsyncMock()
        browser.new_page.return_value = page

        result = await self.fetcher._new_browser_page(browser)

        browser.new_page.assert_awaited_once_with(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/149.0.7827.0 Safari/537.36"
            ),
            locale="en-US",
            viewport={"width": 1365, "height": 768},
        )
        page.add_init_script.assert_awaited_once_with(self.fetcher._BROWSER_INIT_SCRIPT)
        assert result is page

    @pytest.mark.asyncio
    async def test_launch_browser_avoids_single_process_fingerprint(self):
        """Chromium launch flags should reduce the automation fingerprint."""
        original_playwright = WebContentFetcher._playwright
        original_browser = WebContentFetcher._browser
        manager = AsyncMock()
        playwright = AsyncMock()
        browser = AsyncMock()
        manager.start.return_value = playwright
        playwright.chromium.launch.return_value = browser

        WebContentFetcher._playwright = None
        WebContentFetcher._browser = None
        try:
            with patch("playwright.async_api.async_playwright", return_value=manager):
                result = await self.fetcher._launch_browser()

            launch_kwargs = playwright.chromium.launch.await_args.kwargs
            assert "--disable-blink-features=AutomationControlled" in launch_kwargs["args"]
            assert "--single-process" not in launch_kwargs["args"]
            assert result is browser
        finally:
            WebContentFetcher._playwright = original_playwright
            WebContentFetcher._browser = original_browser

    @pytest.mark.asyncio
    async def test_browser_fallback_rejects_security_interstitial(self):
        """A rendered challenge page is not successful browser content."""
        url = "https://example.com/protected"
        challenge_html = """
        <html>
            <script src="/.bunny-shield/assets/shield-challenge.js"></script>
            <body>Calculating...</body>
        </html>
        """

        with patch.object(
            self.fetcher,
            "_render_with_browser",
            new_callable=AsyncMock,
            return_value=challenge_html,
        ):
            with patch.object(self.fetcher, "_parse_html_content") as mock_parse:
                result = await self.fetcher._try_browser_fallback(url)

        assert result is None
        mock_parse.assert_not_called()

    @pytest.mark.asyncio
    async def test_static_security_interstitial_tries_browser(self):
        """A parseable HTTP 200 challenge should still use browser fallback."""
        url = "https://example.com/protected"
        challenge_html = """
        <html><body>
            This website is using a security service to protect itself from online attacks.
        </body></html>
        """
        mock_response = AsyncMock()
        mock_response.headers = {"content-type": "text/html"}
        mock_response.content = challenge_html.encode()
        mock_response.text = challenge_html
        mock_response.raise_for_status = lambda: None

        with patch("src.core.web_fetcher.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            with patch.object(
                self.fetcher,
                "_try_browser_fallback",
                new_callable=AsyncMock,
                return_value="Rendered article content",
            ) as mock_browser:
                content, _, _, _ = await self.fetcher.fetch_and_parse(url)

        mock_browser.assert_awaited_once_with(url)
        assert content == "Rendered article content"

    @pytest.mark.asyncio
    async def test_jina_rejects_security_interstitial(self):
        """Jina verification text should raise instead of becoming success output."""
        url = "https://example.com/protected"
        mock_response = AsyncMock()
        mock_response.text = (
            "## Performing security verification\n\n"
            "This website uses a security service to protect against malicious bots."
        )
        mock_response.raise_for_status = lambda: None

        with patch("src.core.web_fetcher.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            with pytest.raises(SearchException, match="security verification interstitial"):
                await self.fetcher._fetch_via_jina(url)

    @pytest.mark.asyncio
    async def test_browser_fallback_on_empty_static(self):
        """When static fetch returns empty text, browser fallback is attempted."""
        url = "https://example.com/spa"
        browser_html = "<html><body><article><p>JS-rendered content here</p></article></body></html>"

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.content = b"<html></html>"
        mock_response.text = "<html><body></body></html>"
        mock_response.raise_for_status = lambda: None

        with patch("src.core.web_fetcher.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            with patch.object(self.fetcher, "_parse_html_content", side_effect=["", "JS-rendered content here"]):
                with patch.object(self.fetcher, "_render_with_browser", new_callable=AsyncMock, return_value=browser_html) as mock_browser:
                    content, _, _, _ = await self.fetcher.fetch_and_parse(url)

                    mock_browser.assert_called_once_with(url)
                    assert "JS-rendered content" in content

    @pytest.mark.asyncio
    async def test_render_timeout_extracts_partial(self):
        """When static returns empty and browser returns partial HTML, content is extracted."""
        url = "https://example.com/slow-spa"
        partial_html = "<html><body><article><p>Partial content before timeout</p></article></body></html>"

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.content = b"<html></html>"
        mock_response.text = "<html><body></body></html>"
        mock_response.raise_for_status = lambda: None

        with patch("src.core.web_fetcher.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            with patch.object(self.fetcher, "_parse_html_content", side_effect=["", "Partial content before timeout"]):
                with patch.object(self.fetcher, "_render_with_browser", new_callable=AsyncMock, return_value=partial_html):
                    content, _, _, _ = await self.fetcher.fetch_and_parse(url)

                    assert isinstance(content, str)
                    assert len(content) > 0

    @pytest.mark.asyncio
    async def test_pdf_url_skips_browser_uses_jina(self):
        """PDF URLs go straight to Jina, skipping both static parse and browser."""
        pdf_url = "https://example.com/report.pdf"

        with patch.object(self.fetcher, "_render_with_browser") as mock_browser:
            with patch.object(self.fetcher, "_fetch_via_jina", new_callable=AsyncMock, return_value=("PDF content here", False)) as mock_jina:
                content, _, _, _ = await self.fetcher.fetch_and_parse(pdf_url)

                mock_browser.assert_not_called()
                mock_jina.assert_called_once_with(pdf_url)
                assert "PDF content" in content

    @pytest.mark.asyncio
    async def test_empty_static_and_browser_falls_back_to_jina(self):
        """When both static fetch and browser return empty, Jina is used as last resort."""
        url = "https://example.com/tricky-page"

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.content = b"<html></html>"
        mock_response.text = "<html><body></body></html>"
        mock_response.raise_for_status = lambda: None

        with patch("src.core.web_fetcher.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            with patch.object(self.fetcher, "_parse_html_content", return_value=""):
                with patch.object(self.fetcher, "_render_with_browser", new_callable=AsyncMock, return_value="<html></html>"):
                    with patch.object(self.fetcher, "_fetch_via_jina", new_callable=AsyncMock, return_value=("Jina content", False)) as mock_jina:
                        content, _, _, _ = await self.fetcher.fetch_and_parse(url)

                        mock_jina.assert_called_once_with(url)
                        assert "Jina content" in content

    @pytest.mark.asyncio
    async def test_timeout_tries_browser_then_jina(self):
        """When static fetch times out, browser is tried first, then Jina."""
        url = "https://example.com/timeout-page"

        with patch("src.core.web_fetcher.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get.side_effect = httpx.TimeoutException("timed out")
            mock_client_cls.return_value = mock_client

            # Browser also fails → falls through to Jina
            with patch.object(self.fetcher, "_try_browser_fallback", new_callable=AsyncMock, return_value=None) as mock_browser:
                with patch.object(self.fetcher, "_fetch_via_jina", new_callable=AsyncMock, return_value=("Jina fallback", False)) as mock_jina:
                    content, _, _, _ = await self.fetcher.fetch_and_parse(url)

                    mock_browser.assert_called_once_with(url)
                    mock_jina.assert_called_once_with(url)
                    assert "Jina fallback" in content

    @pytest.mark.asyncio
    async def test_http_error_tries_browser_then_jina(self):
        """When static fetch returns HTTP error, browser is tried first, then Jina."""
        url = "https://example.com/error-page"

        with patch("src.core.web_fetcher.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get.side_effect = httpx.HTTPError("503 Service Unavailable")
            mock_client_cls.return_value = mock_client

            # Browser succeeds → no Jina needed
            with patch.object(self.fetcher, "_try_browser_fallback", new_callable=AsyncMock, return_value="Browser content") as mock_browser:
                with patch.object(self.fetcher, "_fetch_via_jina") as mock_jina:
                    content, _, _, _ = await self.fetcher.fetch_and_parse(url)

                    mock_browser.assert_called_once_with(url)
                    mock_jina.assert_not_called()
                    assert "Browser content" in content

    # --- HTML cleaning tests ---

    def test_clean_browser_html_removes_scripts_and_styles(self):
        """Verify script, style, noscript tags and HTML comments are removed."""
        noisy_html = """
        <html><head>
            <script>var x = 1;</script>
            <style>body { color: red; }</style>
        </head><body>
            <!-- this is a comment -->
            <noscript>Enable JS</noscript>
            <article><p>Real content</p></article>
            <script>alert('xss')</script>
        </body></html>
        """
        cleaned = WebContentFetcher._clean_browser_html(noisy_html)

        assert "<script" not in cleaned
        assert "<style" not in cleaned
        assert "<noscript" not in cleaned
        assert "<!--" not in cleaned
        assert "Real content" in cleaned

    def test_clean_browser_html_preserves_content_structure(self):
        """Verify semantic HTML elements are preserved after cleaning."""
        html = """
        <html><body>
            <article><h1>Title</h1><p>Paragraph</p></article>
            <a href="https://example.com">Link</a>
            <ul><li>Item</li></ul>
        </body></html>
        """
        cleaned = WebContentFetcher._clean_browser_html(html)

        assert "<article" in cleaned
        assert "<h1" in cleaned
        assert "<p>" in cleaned or "<p " in cleaned
        assert "<a " in cleaned
        assert "<ul" in cleaned
        assert "<li" in cleaned

    def test_clean_browser_html_handles_malformed_html(self):
        """Graceful fallback on malformed/empty input."""
        # Empty string — should return original
        assert WebContentFetcher._clean_browser_html("") == ""

        # Not valid HTML at all — lxml may still parse it, but shouldn't crash
        result = WebContentFetcher._clean_browser_html("just plain text, no tags")
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_browser_fallback_cleans_html(self):
        """Integration: noisy browser HTML is cleaned before trafilatura extraction in fallback."""
        url = "https://example.com/spa"
        noisy_html = """
        <html><head>
            <script src="app.js"></script>
            <style>.cls { display: none; }</style>
        </head><body>
            <script>window.__DATA__ = {};</script>
            <noscript>Please enable JavaScript</noscript>
            <article><h1>Main Article</h1><p>This is the real content of the page.</p></article>
            <script>trackEvent('view');</script>
        </body></html>
        """
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.content = b"<html></html>"
        mock_response.text = "<html><body></body></html>"
        mock_response.raise_for_status = lambda: None

        with patch("src.core.web_fetcher.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            # Static parse returns empty → triggers browser fallback
            original_parse = self.fetcher._parse_html_content
            call_count = [0]
            def parse_side_effect(html, url=None, favor_recall=False):
                call_count[0] += 1
                if call_count[0] == 1:
                    return ""  # Static path returns empty
                return original_parse(html, url=url, favor_recall=favor_recall)

            with patch.object(self.fetcher, "_parse_html_content", side_effect=parse_side_effect):
                with patch.object(self.fetcher, "_render_with_browser", new_callable=AsyncMock, return_value=noisy_html):
                    with patch.object(WebContentFetcher, "_clean_browser_html", wraps=WebContentFetcher._clean_browser_html) as mock_clean:
                        content, _, _, _ = await self.fetcher.fetch_and_parse(url)

                        mock_clean.assert_called_once()
                        assert isinstance(content, str)
                        assert len(content) > 0

    @pytest.mark.asyncio
    async def test_static_fetch_path_not_cleaned(self):
        """Confirm the static fetch path does not call _clean_browser_html when content is found."""
        url = "https://httpbin.org/html"

        with patch.object(
            WebContentFetcher, "_clean_browser_html", wraps=WebContentFetcher._clean_browser_html,
        ) as mock_clean:
            content, _, _, _ = await self.fetcher.fetch_and_parse(url)

            mock_clean.assert_not_called()
            assert len(content) > 0

    @pytest.mark.asyncio
    async def test_browser_lazy_singleton(self):
        """Test that _ensure_browser returns existing browser when already initialized."""
        original_browser = WebContentFetcher._browser
        try:
            # Set a fake browser as the singleton
            mock_browser = AsyncMock()
            mock_browser.is_connected = lambda: True
            WebContentFetcher._browser = mock_browser

            # _ensure_browser should return the existing instance without re-launching
            result = await self.fetcher._ensure_browser()
            assert result is mock_browser
        finally:
            WebContentFetcher._browser = original_browser
