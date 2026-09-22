"""Explicit, cancellable audio transcription using the existing STT configuration."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import signal
import sys
import tempfile

import httpx

from .config import SearchConfig
from .delivery import DeliveryError
from .youtube_data import video_id

MAX_AUDIO_BYTES = 25 * 1024 * 1024
MAX_TEMP_BYTES = 64 * 1024 * 1024


async def download(ident: str, directory: Path) -> Path:
    args = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--no-playlist",
        "--quiet",
        "--no-warnings",
        "--socket-timeout",
        "15",
        "--retries",
        "0",
        "--extractor-retries",
        "0",
        "--max-filesize",
        str(MAX_AUDIO_BYTES),
        "--match-filter",
        "!is_live",
        "--no-continue",
        "-f",
        "worstaudio",
        "-x",
        "--audio-format",
        "opus",
        "-o",
        str(directory / "audio.%(ext)s"),
    ]
    if SearchConfig.YOUTUBE_PROXY_URL:
        args += ["--proxy", SearchConfig.YOUTUBE_PROXY_URL]
    args += ["https://www.youtube.com/watch?v=" + ident]
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        async with asyncio.timeout(120):
            while proc.returncode is None:
                size = 0
                for path in directory.iterdir():
                    try:
                        if path.is_file():
                            size += path.stat().st_size
                    except FileNotFoundError:
                        pass
                if size > MAX_TEMP_BYTES:
                    raise DeliveryError(
                        "AUDIO_TOO_LARGE",
                        "Audio download exceeds temporary storage limit",
                    )
                await asyncio.sleep(0.1)
            await proc.wait()
        if proc.returncode:
            raise DeliveryError("UPSTREAM_ERROR", "YouTube audio download failed")
        audio = directory / "audio.opus"
        if not audio.is_file() or not audio.stat().st_size:
            raise DeliveryError(
                "AUDIO_UNAVAILABLE",
                "No audio downloaded; video may be unavailable, live, or exceed the 25-MiB limit",
            )
        if audio.stat().st_size > MAX_AUDIO_BYTES:
            raise DeliveryError("AUDIO_TOO_LARGE", "Audio exceeds 25 MiB upload limit")
        return audio
    finally:
        # Kill the entire dedicated process group, including any active ffmpeg child.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await proc.wait()


async def transcribe(reference: str, language: str = "en") -> tuple[str, str]:
    ident = video_id(reference)
    if not all(
        (SearchConfig.STT_ENDPOINT, SearchConfig.STT_MODEL, SearchConfig.STT_API_KEY)
    ):
        raise DeliveryError(
            "NOT_CONFIGURED",
            "STT_ENDPOINT, STT_MODEL and STT_API_KEY are required for STT",
        )
    with tempfile.TemporaryDirectory(prefix="webintel_stt_") as root:
        audio = await download(ident, Path(root))
        async with httpx.AsyncClient(timeout=120, follow_redirects=False) as client:
            with audio.open("rb") as stream:
                async with client.stream(
                    "POST",
                    SearchConfig.STT_ENDPOINT.rstrip("/") + "/audio/transcriptions",
                    headers={"Authorization": "Bearer " + SearchConfig.STT_API_KEY},
                    data={
                        "model": SearchConfig.STT_MODEL,
                        "response_format": "text",
                        "language": language,
                    },
                    files={"file": ("audio.opus", stream, "audio/ogg")},
                ) as response:
                    response.raise_for_status()
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > 8 * 1024 * 1024:
                            raise DeliveryError(
                                "DOCUMENT_TOO_LARGE",
                                "STT transcript exceeds snapshot limit",
                            )
        text = body.decode("utf-8", errors="replace").strip()
        if not text:
            raise DeliveryError(
                "TRANSCRIPT_UNAVAILABLE", "STT returned an empty transcript"
            )
        return text, "youtube_stt"
