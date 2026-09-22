"""V2 public-web fetch lifecycle, bounded downloads and browser readiness."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx

from .config import SearchConfig
from .delivery import DeliveryError, MAX_DOCUMENT_BYTES
from .web_fetcher import WebContentFetcher


async def validate_url(url: str) -> None:
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password:
        raise DeliveryError(
            "INVALID_ARGUMENT",
            "Only public HTTP(S) URLs without credentials are supported",
        )
    try:
        addresses = await asyncio.get_running_loop().getaddrinfo(
            p.hostname, p.port or 443, type=socket.SOCK_STREAM
        )
    except (OSError, ValueError):
        raise DeliveryError("UPSTREAM_ERROR", "URL hostname could not be resolved")
    if not addresses or any(
        not ipaddress.ip_address(a[4][0]).is_global for a in addresses
    ):
        raise DeliveryError(
            "INVALID_ARGUMENT",
            "Private, loopback and reserved addresses are not supported",
        )


class PublicWebFetcher(WebContentFetcher):
    def __init__(self) -> None:
        super().__init__()
        self.client: httpx.AsyncClient | None = None
        self._browser_lock = asyncio.Lock()
        self._browser_slots = asyncio.Semaphore(2)

    def http(self) -> httpx.AsyncClient:
        if self.client is None:
            self.client = httpx.AsyncClient(
                proxy=SearchConfig.PROXY_URL,
                timeout=10,
                limits=httpx.Limits(max_connections=12, max_keepalive_connections=6),
            )
        return self.client

    async def close(self) -> None:
        if self.client:
            await self.client.aclose()
            self.client = None
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        WebContentFetcher._browser = None
        WebContentFetcher._playwright = None

    async def download(self, url: str) -> tuple[str, bytes]:
        for _ in range(6):
            await validate_url(url)
            async with self.http().stream(
                "GET",
                url,
                headers={
                    **self.headers,
                    "Accept": "text/markdown, text/html;q=0.9, */*;q=0.5",
                },
            ) as r:
                if r.is_redirect:
                    url = urljoin(url, r.headers.get("location", ""))
                    continue
                r.raise_for_status()
                chunks, size = [], 0
                async for chunk in r.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_DOCUMENT_BYTES:
                        raise DeliveryError(
                            "DOCUMENT_TOO_LARGE",
                            "Download exceeds 8 MiB decompressed limit",
                        )
                    chunks.append(chunk)
                return r.headers.get("content-type", ""), b"".join(chunks)
        raise DeliveryError("UPSTREAM_ERROR", "Too many redirects")

    async def _render_with_browser(self, url: str) -> str:
        async with self._browser_slots:
            async with self._browser_lock:
                browser = await self._ensure_browser()
            page = await self._new_browser_page(browser)

            async def route(request_route):
                try:
                    await validate_url(request_route.request.url)
                    if request_route.request.resource_type in (
                        "image",
                        "media",
                        "font",
                    ):
                        await request_route.abort()
                    else:
                        await request_route.continue_()
                except (DeliveryError, ValueError):
                    await request_route.abort()

            await page.route("**/*", route)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=12000)
                # Bounded text-stability observation: don't wait for analytics/polling.
                previous = ""
                stable = 0
                for attempt in range(20):
                    main = page.locator("main, article, [role=main]").first
                    has_main = await main.count() > 0
                    current = await (
                        main if has_main else page.locator("body")
                    ).inner_text(timeout=1000)
                    stable = (
                        stable + 1
                        if current == previous and len(current.strip()) > 100
                        else 0
                    )
                    if stable >= 2 and (has_main or attempt >= 10):
                        break
                    previous = current
                    await asyncio.sleep(0.15)
                return await page.content()
            finally:
                await page.close()

    async def fetch_and_parse(
        self, url: str, offset: int = 0, max_length: int | None = None
    ) -> tuple[str, bool, int, int]:
        await validate_url(url)
        text = None
        try:
            content_type, raw = await self.download(url)
            if not self._is_pdf_content(content_type, raw[:8]):
                html = httpx.Response(
                    200, headers={"content-type": content_type}, content=raw
                ).text
                if not self._is_security_interstitial(html):
                    text = (
                        html
                        if any(
                            t in content_type for t in ("text/markdown", "text/plain")
                        )
                        else await asyncio.to_thread(
                            self._parse_html_content, html, url
                        )
                    )
        except httpx.HTTPError:
            pass
        if not text:
            text = (
                await self._try_browser_fallback(url)
                if not self._is_pdf_url(url)
                else None
            )
        if not text:
            # Public URL validated above; reader response is bounded too.
            _, raw = await self.download("https://r.jina.ai/" + url)
            text = raw.decode("utf-8", errors="replace")
        if self._is_security_interstitial(text):
            raise DeliveryError(
                "UPSTREAM_BLOCKED", "Website returned a security interstitial"
            )
        if len(text.encode()) > MAX_DOCUMENT_BYTES:
            raise DeliveryError(
                "DOCUMENT_TOO_LARGE", "Extracted content exceeds 8 MiB limit"
            )
        return self._apply_offset_and_chunk(text, offset, max_length)
