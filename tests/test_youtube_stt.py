import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio
from fastmcp import Client

from src.core import youtube_stt as stt
from src.core.delivery import DeliveryError
from src.server import delivery_server as server


@pytest_asyncio.fixture(autouse=True)
async def isolated_service(monkeypatch):
    from src.core.delivery_service import DeliveryService

    service = DeliveryService()
    # Legacy browser tests leave class-level handles tied to their own event loop.
    service.web._browser = None
    service.web._playwright = None
    monkeypatch.setattr(server, "service", service)
    yield
    await service.web.close()
    await service.exa.close()


@pytest.mark.asyncio
async def test_captions_default_no_stt_and_opt_out_of_error_fallback(monkeypatch):
    captions = AsyncMock(return_value=("[0.0s] captions", "youtube_captions"))
    speech = AsyncMock()
    monkeypatch.setattr(server.service.youtube, "transcript", captions)
    monkeypatch.setattr(stt, "transcribe", speech)
    async with Client(server.mcp) as client:
        result = await client.call_tool(
            "fetch_youtube_transcript", {"reference": "jNQXAC9IVRw"}
        )
        assert result.structured_content["meta"]["source"] == "youtube_captions"
        captions.side_effect = DeliveryError("CAPTIONS_UNAVAILABLE", "No captions")
        error = await client.call_tool(
            "fetch_youtube_transcript",
            {"reference": "jNQXAC9IVRw", "fallback_to_stt": False},
            raise_on_error=False,
        )
        assert error.is_error and "CAPTIONS_UNAVAILABLE" in error.content[0].text
    speech.assert_not_awaited()


@pytest.mark.asyncio
async def test_explicit_stt_lossless_continuation(monkeypatch):
    text = "Transcript 😀 sentence.\n" * 3000
    speech = AsyncMock(return_value=(text, "youtube_stt"))
    captions = AsyncMock()
    monkeypatch.setattr(stt, "transcribe", speech)
    monkeypatch.setattr(server.service.youtube, "transcript", captions)
    async with Client(server.mcp) as client:
        schema = next(
            t for t in await client.list_tools() if t.name == "fetch_youtube_transcript"
        )
        assert schema.input_schema["properties"]["source"]["default"] == "captions"
        result = await client.call_tool(
            "fetch_youtube_transcript",
            {
                "reference": "jNQXAC9IVRw",
                "source": "stt",
                "language": "fr",
                "max_chars": 2000,
            },
        )
        pieces = []
        while True:
            data = result.structured_content
            assert data["meta"]["source"] == "youtube_stt"
            assert len(data["data"]["content"]) <= 2000
            pieces.append(data["data"]["content"])
            if not data["page"]["next_cursor"]:
                break
            result = await client.call_tool(
                "read_content",
                {"cursor": data["page"]["next_cursor"], "max_chars": 2000},
            )
    assert "".join(pieces) == text
    speech.assert_awaited_once_with("jNQXAC9IVRw", "fr")
    captions.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_config_does_not_download(monkeypatch):
    monkeypatch.setattr(stt.SearchConfig, "STT_ENDPOINT", None)
    download = AsyncMock()
    monkeypatch.setattr(stt, "download", download)
    with pytest.raises(DeliveryError) as exc:
        await stt.transcribe("jNQXAC9IVRw")
    assert exc.value.code == "NOT_CONFIGURED"
    download.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [False, True])
async def test_upload_uses_existing_service_and_cleans_temp(monkeypatch, failure):
    monkeypatch.setattr(stt.SearchConfig, "STT_ENDPOINT", "https://stt.example/v1")
    monkeypatch.setattr(stt.SearchConfig, "STT_MODEL", "existing-model")
    monkeypatch.setattr(stt.SearchConfig, "STT_API_KEY", "test-only")
    roots = []

    async def download(ident, directory):
        roots.append(directory)
        path = directory / "audio.opus"
        path.write_bytes(b"fixture-audio")
        return path

    monkeypatch.setattr(stt, "download", download)

    def handle(request):
        assert str(request.url) == "https://stt.example/v1/audio/transcriptions"
        assert request.headers["Authorization"] == "Bearer test-only"
        assert (
            b"existing-model" in request.content and b"fixture-audio" in request.content
        )
        return httpx.Response(500 if failure else 200, text="transcribed text")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(stt.httpx, "AsyncClient", lambda **kwargs: client)
    if failure:
        with pytest.raises(httpx.HTTPStatusError):
            await stt.transcribe("jNQXAC9IVRw")
    else:
        assert await stt.transcribe("jNQXAC9IVRw") == (
            "transcribed text",
            "youtube_stt",
        )
    assert not roots[0].exists()


@pytest.mark.asyncio
async def test_download_cancellation_kills_process_group(monkeypatch, tmp_path):
    class Process:
        pid = 987654
        returncode = None

        async def wait(self):
            self.returncode = -9

    proc = Process()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=proc))
    with patch.object(stt.os, "killpg") as kill:
        task = asyncio.create_task(stt.download("jNQXAC9IVRw", tmp_path))
        await asyncio.sleep(0.02)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        kill.assert_called_once_with(proc.pid, stt.signal.SIGKILL)
        assert proc.returncode == -9


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        DeliveryError("CAPTIONS_UNAVAILABLE", "No captions"),
        DeliveryError("UPSTREAM_ERROR", "Caption fetch failed"),
        TimeoutError(),
        httpx.ConnectError("Failed"),
        ValueError("Malformed captions"),
    ],
)
async def test_caption_failures_automatically_use_stt(monkeypatch, failure):
    captions = AsyncMock(side_effect=failure)
    speech = AsyncMock(return_value=("spoken words", "youtube_stt"))
    monkeypatch.setattr(server.service.youtube, "transcript", captions)
    monkeypatch.setattr(stt, "transcribe", speech)
    async with Client(server.mcp) as client:
        result = await client.call_tool(
            "fetch_youtube_transcript", {"reference": "jNQXAC9IVRw"}
        )
    assert result.structured_content["meta"]["source"] == "youtube_stt"
    assert "STT fallback" in result.structured_content["meta"]["warnings"][0]
    speech.assert_awaited_once_with("jNQXAC9IVRw", "en")


@pytest.mark.asyncio
async def test_invalid_reference_never_transcribes(monkeypatch):
    speech = AsyncMock()
    monkeypatch.setattr(stt, "transcribe", speech)
    async with Client(server.mcp) as client:
        result = await client.call_tool(
            "fetch_youtube_transcript",
            {"reference": "https://example.org/"},
            raise_on_error=False,
        )
    assert result.is_error and "INVALID_ARGUMENT" in result.content[0].text
    speech.assert_not_awaited()


@pytest.mark.asyncio
async def test_caption_cancellation_never_transcribes(monkeypatch):
    started = asyncio.Event()

    async def captions(*args):
        started.set()
        await asyncio.Event().wait()

    speech = AsyncMock()
    monkeypatch.setattr(server.service.youtube, "transcript", captions)
    monkeypatch.setattr(stt, "transcribe", speech)
    task = asyncio.create_task(server.fetch_youtube_transcript("jNQXAC9IVRw"))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    speech.assert_not_awaited()
