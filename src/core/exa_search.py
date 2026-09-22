"""Bounded Exa discovery; no implicit fetches, retries, or provider fallbacks."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from urllib.parse import urlsplit

import httpx

from .delivery import DeliveryError
from .youtube_data import video_id


class ExaSearch:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self.client = client or httpx.AsyncClient(timeout=20, follow_redirects=False)

    async def close(self) -> None:
        await self.client.aclose()

    async def search(
        self,
        query: str,
        limit: int = 5,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
        start_published_date: str | None = None,
        end_published_date: str | None = None,
        videos: bool = False,
    ) -> list[dict]:
        if not query.strip() or len(query) > 500 or not 1 <= limit <= 10:
            raise DeliveryError(
                "INVALID_ARGUMENT", "Query and limit are outside allowed bounds"
            )
        payload = {
            "query": query,
            "numResults": limit,
            "type": "auto",
            "contents": {"text": {"maxCharacters": 350}},
        }
        for name, domains in (
            ("includeDomains", include_domains),
            ("excludeDomains", exclude_domains),
        ):
            if domains is not None:
                if len(domains) > 20 or any(
                    not isinstance(d, str)
                    or not d.strip()
                    or len(d) > 200
                    or "://" in d
                    or any(c.isspace() for c in d)
                    for d in domains
                ):
                    raise DeliveryError(
                        "INVALID_ARGUMENT",
                        "Use at most 20 domain or domain/path filters",
                    )
                if domains:
                    payload[name] = domains
        dates = []
        for name, value in (
            ("startPublishedDate", start_published_date),
            ("endPublishedDate", end_published_date),
        ):
            parsed = None
            if value:
                try:
                    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        raise ValueError()
                except (ValueError, TypeError):
                    raise DeliveryError(
                        "INVALID_ARGUMENT",
                        "Published dates require ISO-8601 timestamps with timezone",
                    ) from None
                payload[name] = value
            dates.append(parsed)
        if all(dates) and dates[0] > dates[1]:
            raise DeliveryError(
                "INVALID_ARGUMENT", "Start date must not follow end date"
            )
        if videos:
            payload["includeDomains"] = [
                "youtube.com/watch",
                "youtube.com/shorts",
                "youtu.be",
            ]
        key = os.environ.get("EXA_API_KEY")
        if not key:
            raise DeliveryError("NOT_CONFIGURED", "EXA_API_KEY is not configured")
        async with self.client.stream(
            "POST",
            "https://api.exa.ai/search",
            json=payload,
            headers={"x-api-key": key},
        ) as response:
            if response.status_code != 200:
                code = {
                    401: "AUTH_FAILED",
                    403: "UPSTREAM_BLOCKED",
                    429: "RATE_LIMITED",
                }.get(response.status_code, "UPSTREAM_ERROR")
                raise DeliveryError(code, "Exa search request failed")
            data = bytearray()
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > 1024 * 1024:
                    raise DeliveryError(
                        "UPSTREAM_ERROR", "Exa response exceeds size limit"
                    )
        try:
            raw = json.loads(data)
            results = raw["results"]
            if not isinstance(results, list):
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise DeliveryError("UPSTREAM_ERROR", "Invalid Exa response") from None
        rows, seen = [], set()
        for entry in results[:limit]:
            if not isinstance(entry, dict):
                continue
            url = entry.get("url")
            if not isinstance(url, str) or len(url) > 2000:
                continue
            try:
                parsed = urlsplit(url)
                if (
                    parsed.scheme not in {"http", "https"}
                    or not parsed.hostname
                    or parsed.username
                    or parsed.password
                ):
                    continue
                identity = url.split("#", 1)[0]
                if videos:
                    identity = "https://www.youtube.com/watch?v=" + video_id(url)
            except (ValueError, DeliveryError):
                continue
            if identity in seen:
                continue
            seen.add(identity)

            def field(name: str, cap: int) -> str:
                value = entry.get(name)
                return value[:cap] if isinstance(value, str) else ""

            rows.append(
                dict(
                    id=hashlib.sha256(identity.encode()).hexdigest()[:24],
                    url=identity,
                    title=field("title", 300),
                    body=field("text", 350),
                    author=field("author", 100),
                )
            )
        return rows
