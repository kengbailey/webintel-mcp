"""
Web content fetching functionality
"""

import httpx
import trafilatura
from lxml.html import fromstring, tostring
from lxml.html.clean import Cleaner
from .config import SearchConfig, SearchException


class WebContentFetcher:
    """Handles fetching and parsing web content."""

    # Singleton browser instance (lazy init)
    _playwright = None
    _browser = None

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
        if content_type and 'application/pdf' in content_type.lower():
            return True
        if content_start and content_start.startswith(b'%PDF'):
            return True
        return False

    @staticmethod
    def _clean_browser_html(html: str) -> str:
        """
        Strip scripts, styles, noscript tags, and HTML comments from
        browser-rendered HTML so trafilatura can extract main content.

        Falls back to returning the original HTML if cleaning fails.
        """
        try:
            cleaner = Cleaner(
                scripts=True,
                javascript=True,
                style=True,
                comments=True,
                page_structure=False,
                remove_tags=["noscript"],
            )
            doc = fromstring(html)
            cleaned = cleaner.clean_html(doc)
            return tostring(cleaned, encoding="unicode")
        except Exception:
            return html

    async def _launch_browser(self):
        """Launch a new Playwright browser, closing any stale instances first."""
        if WebContentFetcher._playwright is not None:
            try:
                await WebContentFetcher._playwright.stop()
            except Exception:
                pass
        from playwright.async_api import async_playwright
        WebContentFetcher._playwright = await async_playwright().start()
        WebContentFetcher._browser = await WebContentFetcher._playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--single-process",
            ],
        )
        return WebContentFetcher._browser

    async def _ensure_browser(self):
        """Lazily initialize the Playwright browser singleton, re-launching if crashed."""
        if WebContentFetcher._browser is None or not WebContentFetcher._browser.is_connected():
            return await self._launch_browser()
        return WebContentFetcher._browser

    async def _render_with_browser(self, url: str) -> str:
        """
        Render a page in a headless browser and return the rendered HTML.

        Uses Playwright to load the page, wait for network idle,
        and extract the final DOM content.

        Args:
            url: The URL to render

        Returns:
            Rendered HTML string

        Raises:
            SearchException: If rendering fails entirely
        """
        browser = await self._ensure_browser()
        try:
            page = await browser.new_page()
        except Exception:
            # Browser died between check and use — re-launch once
            browser = await self._launch_browser()
            page = await browser.new_page()
        try:
            timeout_ms = int(SearchConfig.RENDER_TIMEOUT * 1000)
            try:
                await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            except Exception:
                # Timeout or navigation error — extract whatever HTML is available
                pass
            html = await page.content()
            return html
        except Exception as e:
            raise SearchException(f"Browser rendering failed for {url}: {str(e)}")
        finally:
            await page.close()

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

        if offset >= total_length:
            return "", False, total_length, total_length

        end_pos = min(offset + SearchConfig.MAX_CONTENT_LENGTH, total_length)
        content_chunk = content[offset:end_pos]
        is_truncated = end_pos < total_length
        next_offset = end_pos if is_truncated else total_length

        return content_chunk, is_truncated, next_offset, total_length

    def _parse_html_content(self, html_content: str, url: str = None, favor_recall: bool = False) -> str:
        """
        Parse HTML content using trafilatura and extract text as Markdown.

        Args:
            html_content: Raw HTML string
            url: Original URL (helps trafilatura with link resolution)
            favor_recall: If True, use permissive extraction (for noisy browser-rendered HTML)

        Returns:
            Extracted content as Markdown string
        """
        # Primary extraction: trafilatura with Markdown output
        text = trafilatura.extract(
            html_content,
            output_format="markdown",
            include_links=True,
            include_formatting=True,
            include_tables=True,
            url=url,
            favor_recall=favor_recall,
        )

        # Fallback chain if trafilatura returns None
        if not text:
            result = trafilatura.bare_extraction(html_content, url=url, favor_recall=favor_recall)
            if result:
                doc = result if isinstance(result, dict) else result.as_dict()
                text = doc.get("text", "")
                if text:
                    return text

            # Last resort: extract all text
            text = trafilatura.html2txt(html_content)
            if not text:
                text = ""

        return text

    async def _try_browser_fallback(self, url: str) -> str | None:
        """
        Attempt JS rendering fallback: render with browser, clean HTML, extract text.

        Returns extracted text or None if browser fails or yields empty content.
        """
        try:
            html = await self._render_with_browser(url)
            html = self._clean_browser_html(html)
            text = self._parse_html_content(html, url=url, favor_recall=True)
            if text and text.strip():
                return text
        except Exception:
            pass
        return None

    async def fetch_and_parse(self, url: str, offset: int = 0) -> tuple[str, bool, int, int]:
        """
        Fetch and parse content from a webpage or PDF.

        Fallback chain: static fetch → JS render (if empty) → Jina (if still empty/error).

        Args:
            url: The webpage URL to fetch content from
            offset: Starting position for content retrieval (default: 0)

        Returns:
            Tuple of (parsed_text, is_truncated, next_offset, total_length)

        Raises:
            SearchException: If fetching or parsing fails
        """
        try:
            if offset < 0:
                offset = 0

            # PDFs always go through Jina
            if self._is_pdf_url(url):
                content, was_truncated = await self._fetch_via_jina(url)
                return self._apply_offset_and_chunk(content, offset)

            # Standard static fetch path
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

                # Parse as HTML with trafilatura
                text = self._parse_html_content(response.text, url=url)

                # If static extraction returned content, return it
                if text and text.strip():
                    return self._apply_offset_and_chunk(text, offset)

                # Empty static result → try JS rendering fallback
                browser_text = await self._try_browser_fallback(url)
                if browser_text:
                    return self._apply_offset_and_chunk(browser_text, offset)

                # Still empty → try Jina
                content, was_truncated = await self._fetch_via_jina(url)
                return self._apply_offset_and_chunk(content, offset)

        except SearchException:
            raise
        except httpx.TimeoutException:
            # Static fetch timed out → try browser, then Jina
            browser_text = await self._try_browser_fallback(url)
            if browser_text:
                return self._apply_offset_and_chunk(browser_text, offset)
            try:
                content, was_truncated = await self._fetch_via_jina(url)
                return self._apply_offset_and_chunk(content, offset)
            except SearchException:
                raise SearchException(f"Failed to fetch {url}")

        except httpx.HTTPError as e:
            # HTTP error → try browser, then Jina
            browser_text = await self._try_browser_fallback(url)
            if browser_text:
                return self._apply_offset_and_chunk(browser_text, offset)
            try:
                content, was_truncated = await self._fetch_via_jina(url)
                return self._apply_offset_and_chunk(content, offset)
            except SearchException:
                raise SearchException(f"Failed to fetch {url}")
        except Exception as e:
            raise SearchException(f"Unexpected error while fetching content: {str(e)}")
