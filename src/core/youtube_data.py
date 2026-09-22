"""YouTube metadata/captions without implicit audio or comment downloads."""

from __future__ import annotations

import asyncio
import json
import os
import re
from urllib.parse import parse_qs, urlparse

import httpx

from .config import SearchConfig
from .delivery import DeliveryError


def video_id(reference: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", reference):
        return reference
    p = urlparse(reference)
    host = (p.hostname or "").lower()
    parts = p.path.strip("/").split("/")
    ident = None
    if p.scheme in ("https", "http"):
        if host == "youtu.be":
            ident = parts[0]
        elif host in (
            "youtube.com",
            "www.youtube.com",
            "m.youtube.com",
            "music.youtube.com",
        ):
            ident = parse_qs(p.query).get("v", [None])[0]
            if (
                not ident
                and len(parts) == 2
                and parts[0] in ("shorts", "embed", "live", "watch")
            ):
                ident = parts[1]
    if ident and re.fullmatch(r"[A-Za-z0-9_-]{11}", ident):
        return ident
    raise DeliveryError(
        "INVALID_ARGUMENT", "Expected a YouTube video ID or supported YouTube URL"
    )


class YouTubeData:
    def __init__(self) -> None:
        self.key = os.getenv("YOUTUBE_API_KEY")

    async def api(self, endpoint: str, params: dict) -> dict:
        if not self.key:
            raise DeliveryError(
                "NOT_CONFIGURED", "YOUTUBE_API_KEY is required for paginated comments"
            )
        async with httpx.AsyncClient(
            proxy=SearchConfig.YOUTUBE_PROXY_URL, timeout=15
        ) as client:
            r = await client.get(
                "https://www.googleapis.com/youtube/v3/" + endpoint,
                params={**params, "key": self.key},
            )
        if r.status_code >= 400:
            try:
                reason = r.json()["error"]["errors"][0]["reason"]
            except (KeyError, ValueError, IndexError):
                reason = ""
            code = {
                "commentsDisabled": "COMMENTS_DISABLED",
                "quotaExceeded": "RATE_LIMITED",
                "videoNotFound": "NOT_FOUND",
            }.get(reason, "UPSTREAM_ERROR")
            raise DeliveryError(code, "YouTube API could not complete this request")
        return r.json()

    async def metadata(self, reference: str) -> dict:
        ident = video_id(reference)
        # The official API is stable and cheap; yt-dlp is a no-account fallback.
        if self.key:
            data = await self.api(
                "videos", {"id": ident, "part": "snippet,statistics,contentDetails"}
            )
            if not data.get("items"):
                raise DeliveryError("NOT_FOUND", "Video is unavailable")
            x = data["items"][0]
            s = x["snippet"]
            stats = x.get("statistics", {})
            duration = x.get("contentDetails", {}).get("duration", "")
            match = re.fullmatch(
                r"P(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration
            )
            seconds = (
                sum(
                    int(v or 0) * unit
                    for v, unit in zip(match.groups(), (86400, 3600, 60, 1))
                )
                if match
                else None
            )
            return dict(
                id=ident,
                title=s.get("title"),
                channel=s.get("channelTitle"),
                duration=seconds,
                published_at=s.get("publishedAt"),
                description=s.get("description", ""),
                view_count=stats.get("viewCount"),
                like_count=stats.get("likeCount"),
                comment_count=stats.get("commentCount"),
                source="youtube_api",
            )
        return await self.extract(ident)

    async def extract(self, reference: str) -> dict:
        import sys

        ident = video_id(reference)
        fields = "%(.{id,title,channel,description,upload_date,duration,view_count,like_count,comment_count,subtitles,automatic_captions})j"
        args = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--skip-download",
            "--no-playlist",
            "--socket-timeout",
            "10",
            "--retries",
            "0",
            "--extractor-retries",
            "0",
            "--quiet",
            "--no-warnings",
            "--print",
            fields,
        ]
        if SearchConfig.YOUTUBE_PROXY_URL:
            args += ["--proxy", SearchConfig.YOUTUBE_PROXY_URL]
        args += ["https://www.youtube.com/watch?v=" + ident]
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
        )
        try:
            async with asyncio.timeout(35):
                chunks = []
                size = 0
                while chunk := await proc.stdout.read(65536):
                    size += len(chunk)
                    if size > 8 * 1024 * 1024:
                        raise DeliveryError(
                            "DOCUMENT_TOO_LARGE", "Video metadata exceeds limit"
                        )
                    chunks.append(chunk)
                await proc.wait()
            if proc.returncode:
                raise DeliveryError(
                    "UPSTREAM_ERROR", "Video metadata unavailable through yt-dlp"
                )
            data = json.loads(b"".join(chunks))
            data["source"] = "yt_dlp"
            stamp = data.get("upload_date")
            if stamp and re.fullmatch(r"\d{8}", stamp):
                data["published_at"] = f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}"
            return data
        finally:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()

    async def transcript(self, reference: str, language: str = "en") -> tuple[str, str]:
        data = await self.extract(reference)
        tracks = data.get("subtitles", {}).get(language)
        source = "youtube_captions"
        if not tracks:
            tracks = data.get("automatic_captions", {}).get(language)
            source = "youtube_auto_captions"
        track = next((x for x in tracks or [] if x.get("ext") == "json3"), None)
        if not track:
            raise DeliveryError(
                "CAPTIONS_UNAVAILABLE",
                "No JSON captions for requested language; no STT was started",
            )
        from .public_fetch import validate_url

        await validate_url(track["url"])
        async with httpx.AsyncClient(
            proxy=SearchConfig.YOUTUBE_PROXY_URL, timeout=15
        ) as client:
            async with client.stream("GET", track["url"]) as r:
                if r.status_code != 200:
                    raise DeliveryError("UPSTREAM_ERROR", "Caption download failed")
                parts = []
                size = 0
                async for part in r.aiter_bytes():
                    size += len(part)
                    if size > 8 * 1024 * 1024:
                        raise DeliveryError(
                            "DOCUMENT_TOO_LARGE", "Caption file exceeds limit"
                        )
                    parts.append(part)
        raw = json.loads(b"".join(parts))
        lines = []
        for event in raw.get("events", []):
            text = "".join(s.get("utf8", "") for s in event.get("segs", [])).strip()
            if text:
                lines.append(f"[{event.get('tStartMs', 0) / 1000:.3f}s] {text}")
        if not lines:
            raise DeliveryError("CAPTIONS_UNAVAILABLE", "Caption track is empty")
        return "\n".join(lines), source
