# WebIntel MCP

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-green.svg)](https://www.python.org)
[![FastMCP](https://img.shields.io/badge/FastMCP-3.0-purple.svg)](https://github.com/jlowin/fastmcp)

A FastMCP server providing web search, content fetching, YouTube transcription, and Reddit browsing tools for AI assistants. Includes a bundled SearxNG instance — no external dependencies required.

## Tools

### Search

- **`search`** — Web search via SearxNG
  - `query` (required) — search terms
  - `max_results` (optional, default: 10, max: 25)
  - `categories` (optional) — comma-separated: `general`, `news`, `science`, `it`, `music`
  - `time_range` (optional) — `day`, `month`, or `year`
  - `language` (optional) — ISO language code (e.g., `en`, `de`, `fr`)
  - Returns: title, url, content snippet, score

- **`search_videos`** — YouTube video search
  - `query` (required) — video search terms
  - `max_results` (optional, default: 10, max: 20)
  - Returns: url, title, author, content summary, length

### Content Fetching

- **`fetch_content`** — Fetch and extract readable content from any URL
  - `url` (required) — URL to fetch
  - `offset` (optional, default: 0) — pagination offset
  - Automatic fallback chain: static fetch → JS rendering (if empty) → Jina Reader (if still empty/error)
  - Content is returned in 30K character chunks. Use `next_offset` from the response to paginate.

- **`fetch_youtube_content`** — Download and transcribe YouTube video audio
  - `video_id` (required) — video ID or full URL (e.g. `dQw4w9WgXcQ` or `https://www.youtube.com/watch?v=dQw4w9WgXcQ`)
  - Returns: video_id, transcript, transcript_length
  - Requires: STT endpoint (see [Configuration](#configuration))

### Reddit

- **`fetch_subreddit`** — Browse subreddit posts
  - `subreddit` (required) — subreddit name without `r/` prefix
  - `sort` (optional, default: `hot`) — hot, new, top, rising, controversial
  - `time_filter` (optional) — hour, day, week, month, year, all (for top/controversial)
  - `limit` (optional, default: 25, max: 100)
  - `after` (optional) — pagination cursor from previous response
  - Returns: post summaries with title, author, score, comment count, url

- **`fetch_subreddit_post`** — Fetch a post with full comment tree
  - `subreddit` (required) — subreddit name without `r/` prefix
  - `post_id` (required) — post ID without `t3_` prefix
  - `sort` (optional, default: `confidence`) — confidence, top, new, controversial, old, qa
  - `limit` (optional, default: 100, max: 500) — max comments
  - `depth` (optional) — max reply nesting depth
  - Returns: post detail with selftext, media URLs, and nested comments

## Quick Start

```bash
git clone https://github.com/kengbailey/webintel-mcp.git
cd webintel-mcp

docker build -t webintel-mcp .
docker compose up -d
```

Server available at `http://localhost:3090/mcp`

This starts **WebIntel MCP** (port 3090) and **SearxNG** (internal, not exposed).

## Connecting MCP Clients

### Claude Desktop

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "webintel": {
      "url": "http://localhost:3090/mcp"
    }
  }
}
```

### Cursor

Add to `.cursor/mcp.json` in your project:

```json
{
  "mcpServers": {
    "webintel": {
      "url": "http://localhost:3090/mcp"
    }
  }
}
```

### mcporter

```bash
mcporter call webintel-mcp.search query="latest news" max_results=5

# Search with filters
mcporter call webintel-mcp.search query="AI breakthroughs" categories="science" time_range="month"
mcporter call webintel-mcp.search query="open source LLM" categories="news" time_range="day" language="en"
mcporter call webintel-mcp.fetch_content url="https://example.com"
mcporter call webintel-mcp.fetch_subreddit subreddit="python" sort="top" time_filter="week"
```

## Docker Options

### Option A: Bundled SearxNG (recommended)

```bash
docker build -t webintel-mcp .
docker compose up -d
```

### Option B: External SearxNG

```bash
docker run -p 3090:3090 \
  -e SEARXNG_HOST=http://your-searxng:8189 \
  ghcr.io/kengbailey/webintel-mcp:latest
```

Or override in Compose:

```bash
SEARXNG_HOST=http://your-searxng:8189 docker compose up webintel-mcp -d
```

See [Advanced: External SearxNG Setup](/doc/setup-searxng-and-mcp-server.md) for standalone SearxNG instructions.

### Option C: With VPN

Route all requests through a VPN using [Gluetun](https://github.com/qdm12/gluetun):

```bash
cp .env.example .env
# Edit .env — set VPN_SERVICE_PROVIDER, OPENVPN_USER, OPENVPN_PASSWORD
# Set PROXY_URL=http://gluetun:8888
# Set SEARXNG_HOST=http://gluetun:8080

# Place your .ovpn config in gluetun/custom/config.ovpn

docker compose --profile vpn up -d
```

When using the VPN profile:
- **SearxNG** shares Gluetun's network stack — all search engine queries route through the VPN
- **Fetcher tools** (fetch_content, fetch_youtube_content, fetch_subreddit, fetch_subreddit_post) use the HTTP proxy at `PROXY_URL`
- Without VPN (`docker compose up -d`), everything connects directly

## Configuration

Copy `.env.example` to `.env` and configure as needed:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `SEARXNG_HOST` | `http://searxng:8080` | SearxNG API endpoint. Use `http://gluetun:8080` with VPN profile. |
| `MCP_TRANSPORT` | `http` | Transport: `http` (Streamable HTTP) or `sse` (Server-Sent Events) |
| `STT_ENDPOINT` | — | Speech-to-text API endpoint (OpenAI-compatible, e.g. faster-whisper) |
| `STT_MODEL` | — | STT model name |
| `STT_API_KEY` | — | STT API key |
| `PROXY_URL` | — | HTTP proxy for outbound requests (e.g. `http://gluetun:8888`) |
| `REDDIT_CLIENT_ID` | — | Client ID for a Reddit personal-use script app (required for Reddit tools) |
| `REDDIT_CLIENT_SECRET` | — | Client secret for the Reddit app (required for Reddit tools) |
| `REDDIT_USER_AGENT` | `python:webintel-mcp:v1.0.0` | Identifying Reddit User-Agent; include your Reddit username |
| `REDDIT_PROXY_URL` | — | Optional Reddit-only proxy; empty means direct access even when `PROXY_URL` is set |
| `VPN_SERVICE_PROVIDER` | — | Gluetun VPN provider (use `custom` for .ovpn files) |
| `VPN_TYPE` | — | VPN type (`openvpn` or `wireguard`) |
| `OPENVPN_USER` | — | VPN username |
| `OPENVPN_PASSWORD` | — | VPN password |

## Local Development

```bash
# Clone and setup
git clone https://github.com/kengbailey/webintel-mcp.git
cd webintel-mcp

# Create venv (Python 3.11+)
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set environment
export SEARXNG_HOST=http://localhost:8080  # or your SearxNG instance

# Run the server
python -m src.server.mcp_server

# Run tests
python -m pytest tests/ -v --ignore=tests/test_searxng_integration.py
```

### JS Rendering (Auto Fallback)

`fetch_content` automatically falls back to headless browser rendering when static fetch returns empty content. This requires **Playwright** with Chromium:

```bash
pip install playwright
playwright install chromium
```

The Docker image includes Playwright and Chromium. For local development, install them separately.

### YouTube Transcription Requirements

The `fetch_youtube_content` tool requires:
- **ffmpeg** — audio extraction and conversion
- **Deno** — required by yt-dlp for YouTube JS challenges (since yt-dlp 2025.11.12)
- **STT endpoint** — OpenAI-compatible speech-to-text API (e.g. [faster-whisper-server](https://github.com/fedirz/faster-whisper-server), [Speaches](https://github.com/speaches-ai/speaches))

The Docker image includes ffmpeg and Deno. For local development, install them separately.

## SearxNG Configuration

The bundled SearxNG instance is configured via `searxng/settings.yml`:

- JSON API format enabled (required for WebIntel MCP)
- Rate limiting disabled (internal service)
- Google, DuckDuckGo, and Bing search engines enabled

See `searxng/README.md` for customization options.

## License

[MIT](LICENSE)
