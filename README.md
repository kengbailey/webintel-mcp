# WebIntel MCP

Bounded web, Reddit and YouTube tools for AI assistants. The default container now
runs the **v2 interface**, with Exa search and no SearxNG dependency.

## Tools

| Tool | Purpose |
|---|---|
| `search` | Exa previews, domain/path and publication-date filters |
| `fetch_content` | Page text, outline or matching excerpts |
| `read_content` | Continue a saved content chunk without refetching |
| `search_reddit` | Native Reddit discovery, subreddit/title scoping |
| `fetch_subreddit` | Compact post listing |
| `fetch_subreddit_info` | Community metadata |
| `fetch_reddit_post` | Post body/metadata, no comments |
| `fetch_reddit_comments` | Explicit comment pages and thread focus |
| `search_videos` | Exa YouTube video discovery |
| `fetch_youtube_content` | Description and public video counts, no transcript/comments |
| `fetch_youtube_transcript` | Captions first; STT fallback, or explicit STT |
| `fetch_youtube_comments` | Explicit comments and replies |

Search defaults to five previews, comments to ten items. Page bodies are bounded
at 20,000 characters / 5,000 estimated tokens. Cursors retain overflow for 15 minutes;
`read_content` never repeats a fetch or transcription. Dislikes are unavailable,
not fabricated zeros. All successful tools return a typed v2 envelope.

```json
{"reference":"jNQXAC9IVRw","source":"captions","fallback_to_stt":true}
```

The transcript default above tries captions then configured STT on failure.
Use `source="stt"` to bypass captions; `fallback_to_stt=false` for captions-only.
STT-enabled requests can take up to 300 seconds; configure client timeouts accordingly.

## Container setup

```sh
cp runtime.env.example runtime.env
chmod 600 runtime.env
# Edit runtime.env locally; never commit credentials.
docker compose up -d --build webintel-mcp
```

Default endpoint: `http://HOST:3090/mcp`. Set `MCP_TRANSPORT=sse` in the runtime env
file for `/sse`. Docker listens on 0.0.0.0:3090; direct Python invocation retains
loopback:3091 unless MCP_HOST/MCP_PORT or CLI flags override it.

- `EXA_API_KEY`: required for web/video search.
- `YOUTUBE_API_KEY`: official metadata and public comment/reply API.
- Reddit credentials: native Reddit search, posts and comments.
- Existing `STT_ENDPOINT`, `STT_MODEL`, `STT_API_KEY`: speech transcription.
- Preserve working `PROXY_URL`, `REDDIT_PROXY_URL`, `YOUTUBE_PROXY_URL` settings.
- Existing MCP AuthKit/machine-JWT configuration can be supplied in the same file.
  The current LAN/no-auth behavior is unchanged when it is absent.

Compose controls: `WEBINTEL_IMAGE` selects an immutable release image,
`WEBINTEL_ENV_FILE` selects the runtime env file, `MCP_HOST_PORT` changes the host
port and `MCP_BIND_ADDRESS` changes the bind address. Optional `--profile vpn`
retains Gluetun for installations using its HTTP proxy. Do not stop a working
proxy merely because SearxNG is removed.

## Migration and compatibility

**Refresh clients' tool catalogs before using v2.** Names/arguments/output schemas
changed, especially `fetch_youtube_content`, which is now metadata-only. The old
server remains available with `python -m src.server.mcp_server`, but requires its
legacy provider configuration. See [legacy documentation](doc/legacy-interface.md).
Do not use `docker compose down` or `--remove-orphans` during migration: existing
proxy services and rollback containers may still be required.

See [v2 contracts and limits](doc/delivery-v2.md) and
[release/cutover procedure](doc/release-v2.md) for validation and rollback.

## Versions and checks

FastMCP 4.0.5, yt-dlp 2026.8.19 with default extras, and Deno 2.9.5 are pinned;
the Dockerfile no longer installs a floating yt-dlp nightly. This is not a full
transitive/OS dependency lock. Deploy the tested image digest, not a rebuilt tag.

```sh
python -m pytest tests/ -q -m 'not integration' \
  --ignore=tests/test_searxng_integration.py \
  --ignore=tests/test_youtube_integration.py
```

Excluded integration suites manage containers or invoke legacy live audio/STT.
Release validation additionally exercises the built image and actual HTTP client.
