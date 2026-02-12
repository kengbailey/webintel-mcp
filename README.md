# WebIntel MCP

A powerful FastMCP server providing intelligent web search and content retrieval tools for AI assistants. Includes a bundled SearxNG instance — no external dependencies required.

## Tools

- **`search`** - Returns full search results with titles, URLs, snippets, scores
  - `query` (required) - search terms
  - `max_results` (optional) - number of results (default: 10, max: 25)
- **`search_videos`** - Search for YouTube videos
  - `query` (required) - video search terms
  - `max_results` (optional) - number of results (default: 10, max: 20)
  - Returns: url, title, author, content summary, length
- **`fetch_content`** - Returns the content of a URL with pagination support
  - `url` (required) - URL to fetch content from
  - `offset` (optional) - starting position for content retrieval (default: 0)
  - **Pagination**: Content is retrieved in 30K character chunks. When truncated, use the `next_offset` value from the response to fetch the next chunk.
- **`fetch_youtube_content`** - Fetch and transcribe YouTube video audio
  - `video_id` (required) - YouTube video ID or full URL (e.g., 'dQw4w9WgXcQ' or 'https://www.youtube.com/watch?v=dQw4w9WgXcQ')
  - Returns: video_id, transcript, transcript_length, success
  - **Note**: Requires a running STT (Speech-to-Text) service endpoint

## Quick Start

The easiest way to get running — SearxNG is included as a bundled service:

```bash
# Clone the repo
git clone https://github.com/kengbailey/webintel-mcp.git
cd webintel-mcp

# Build and start everything (WebIntel MCP + SearxNG)
docker build -t webintel-mcp .
docker compose up -d
```

That's it! The server will be available at `http://localhost:3090/mcp`

### What starts:
- **WebIntel MCP** — MCP server on port `3090`
- **SearxNG** — Search backend (internal only, not exposed to host)

## Use with Docker

### Option A: Bundled SearxNG (recommended)

Use Docker Compose to run both services together:

```bash
# Build the WebIntel MCP image
docker build -t webintel-mcp .

# Start everything
docker compose up -d
```

### Option B: External SearxNG

If you already have a SearxNG instance, point to it with `SEARXNG_HOST`:

```bash
# Pull latest image
docker pull ghcr.io/kengbailey/webintel-mcp:latest

# Run with your SearxNG instance
docker run -p 3090:3090 -e SEARXNG_HOST=http://your-searxng:8189 ghcr.io/kengbailey/webintel-mcp:latest
```

Or override in Docker Compose:
```bash
SEARXNG_HOST=http://your-searxng:8189 docker compose up webintel-mcp -d
```

See [Advanced: External SearxNG Setup](/doc/setup-searxng-and-mcp-server.md) for full instructions on running a standalone SearxNG instance.

### Option C: With VPN

Route search requests through a VPN using the gluetun profile:

```bash
# Configure VPN credentials in .env
cp .env.example .env
# Edit .env with your VPN details

# Start with VPN
docker compose --profile vpn up -d
```

## Configuration

Copy `.env.example` to `.env` and configure as needed:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `SEARXNG_HOST` | `http://searxng:8080` | SearxNG API endpoint |
| `MCP_TRANSPORT` | `http` | Transport mode: `http` or `sse` |
| `STT_ENDPOINT` | — | Speech-to-text API endpoint |
| `STT_MODEL` | — | STT model name |
| `STT_API_KEY` | — | STT API key |
| `PROXY_URL` | — | HTTP proxy for outbound requests |

## SearxNG Configuration

The bundled SearxNG instance is configured via `searxng/settings.yml`. The default configuration:

- Enables JSON API format (required for WebIntel MCP)
- Disables rate limiting (internal service)
- Configures Google, DuckDuckGo, and Bing search engines

See `searxng/README.md` for customization options.
