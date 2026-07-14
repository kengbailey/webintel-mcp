# WebIntel MCP

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-green.svg)](https://www.python.org)
[![FastMCP](https://img.shields.io/badge/FastMCP-3.0-purple.svg)](https://github.com/jlowin/fastmcp)

A FastMCP server providing web search, content fetching, YouTube transcription, and Reddit browsing tools for AI assistants. Includes a bundled SearxNG instance — no external dependencies required.

## Tools

### Search

- **`search`** — Web search via SearxNG

  <details>
  <summary>Input</summary>

  ```json
  {
    "query": "Python 3.14 release highlights",
    "max_results": 2,
    "categories": "it,news",
    "time_range": "month",
    "language": "en"
  }
  ```

  </details>

  <details>
  <summary>Output</summary>

  ```json
  [
    {
      "title": "What's New In Python 3.14",
      "url": "https://docs.python.org/3.14/whatsnew/3.14.html",
      "content": "Python 3.14 adds new syntax, runtime improvements, and tooling updates.",
      "score": 1.0
    }
  ]
  ```

  </details>

- **`search_videos`** — YouTube video search

  <details>
  <summary>Input</summary>

  ```json
  {
    "query": "asyncio tutorial",
    "max_results": 2
  }
  ```

  </details>

  <details>
  <summary>Output</summary>

  ```json
  [
    {
      "url": "https://www.youtube.com/watch?v=example123",
      "title": "Python Asyncio Explained",
      "author": "Example Developer",
      "content": "A practical introduction to async and await in Python.",
      "length": "12:34"
    }
  ]
  ```

  </details>

### Content Fetching

- **`fetch_content`** — Fetch and extract readable content from any URL

  <details>
  <summary>Input</summary>

  ```json
  {
    "url": "https://example.com/long-article",
    "offset": 0
  }
  ```

  </details>

  <details>
  <summary>Output</summary>

  ```json
  {
    "content": "Example Domain\n\nThis domain is for use in illustrative examples...",
    "content_length": 66,
    "is_truncated": false,
    "offset": 0,
    "next_offset": null,
    "total_length": 66,
    "success": true
  }
  ```

  </details>

- **`fetch_youtube_content`** — Download and transcribe YouTube video audio

  <details>
  <summary>Input</summary>

  ```json
  {
    "video_id": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
  }
  ```

  </details>

  <details>
  <summary>Output</summary>

  ```json
  {
    "video_id": "dQw4w9WgXcQ",
    "transcript": "We're no strangers to love...",
    "transcript_length": 33,
    "success": true
  }
  ```

  </details>

### Reddit

- **`fetch_subreddit`** — Browse subreddit posts

  <details>
  <summary>Input</summary>

  ```json
  {
    "subreddit": "python",
    "sort": "top",
    "time_filter": "week",
    "limit": 2,
    "after": null
  }
  ```

  </details>

  <details>
  <summary>Output</summary>

  ```json
  {
    "subreddit": "python",
    "sort": "top",
    "time_filter": "week",
    "posts": [
      {
        "id": "1abcde",
        "title": "A useful Python project",
        "author": "example_user",
        "subreddit": "python",
        "score": 142,
        "num_comments": 27,
        "created_utc": 1784044800.0,
        "url": "https://example.com/python-project",
        "permalink": "/r/python/comments/1abcde/a_useful_python_project/",
        "is_self": false,
        "selftext": null,
        "thumbnail": "https://example.com/thumbnail.jpg",
        "link_flair_text": "Resource"
      }
    ],
    "after_cursor": "t3_1abcde",
    "success": true
  }
  ```

  </details>

- **`fetch_subreddit_post`** — Fetch a post with full comment tree

  <details>
  <summary>Input</summary>

  ```json
  {
    "subreddit": "python",
    "post_id": "1abcde",
    "sort": "confidence",
    "limit": 100,
    "depth": 5
  }
  ```

  </details>

  <details>
  <summary>Output</summary>

  ```json
  {
    "post": {
      "title": "What are your favorite asyncio patterns?",
      "author": "example_user",
      "num_comments": 48,
      "created_utc": 1784044800.0,
      "url": "https://www.reddit.com/r/python/comments/1abcde/example/",
      "is_self": true,
      "selftext": "Share the patterns that have worked well for you.",
      "media_urls": [],
      "comments": [
        {
          "id": "def456",
          "author": "commenter",
          "body": "Task groups make cancellation much easier to reason about.",
          "parent_id": "t3_1abcde",
          "created_utc": 1784048400.0,
          "depth": 0
        }
      ],
      "id": "1abcde",
      "subreddit": "python",
      "score": 215,
      "permalink": "/r/python/comments/1abcde/example/",
      "more_comment_ids": ["ghi789", "jkl012"]
    },
    "success": true
  }
  ```

  </details>

- **`search_reddit`** — Search public Reddit posts globally or within one subreddit

  <details>
  <summary>Input</summary>

  ```json
  {
    "query": "asyncio patterns",
    "subreddit": "python",
    "sort": "top",
    "time_filter": "year",
    "limit": 10,
    "after": null
  }
  ```

  </details>

  <details>
  <summary>Output</summary>

  ```json
  {
    "query": "asyncio patterns",
    "subreddit": "python",
    "sort": "top",
    "time_filter": "year",
    "posts": [
      {
        "id": "1abcde",
        "title": "Structured concurrency patterns for asyncio",
        "author": "example_user",
        "subreddit": "python",
        "score": 321,
        "num_comments": 42,
        "created_utc": 1784044800.0,
        "url": "https://www.reddit.com/r/python/comments/1abcde/example/",
        "permalink": "/r/python/comments/1abcde/example/",
        "is_self": true,
        "selftext": "A discussion of task groups and cancellation.",
        "thumbnail": null,
        "link_flair_text": "Discussion"
      }
    ],
    "after_cursor": null,
    "success": true
  }
  ```

  </details>

- **`fetch_reddit_post`** — Fetch a post using a URL, permalink, `/s/` share URL, `redd.it` URL, or post ID

  <details>
  <summary>Input</summary>

  ```json
  {
    "reference": "https://www.reddit.com/r/python/comments/1abcde/example/",
    "sort": "top",
    "limit": 50,
    "depth": 3
  }
  ```

  </details>

  <details>
  <summary>Output</summary>

  ```json
  {
    "post": {
      "title": "Structured concurrency patterns for asyncio",
      "author": "example_user",
      "num_comments": 42,
      "created_utc": 1784044800.0,
      "url": "https://www.reddit.com/r/python/comments/1abcde/example/",
      "is_self": true,
      "selftext": "A discussion of task groups and cancellation.",
      "media_urls": [],
      "comments": [
        {
          "id": "def456",
          "author": "commenter",
          "body": "This pattern also makes timeouts easier to manage.",
          "parent_id": "t3_1abcde",
          "created_utc": 1784048400.0,
          "depth": 0
        }
      ],
      "id": "1abcde",
      "subreddit": "python",
      "score": 321,
      "permalink": "/r/python/comments/1abcde/example/",
      "more_comment_ids": ["ghi789"]
    },
    "success": true
  }
  ```

  </details>

- **`fetch_more_comments`** — Expand omitted comment branches

  <details>
  <summary>Input</summary>

  ```json
  {
    "post_id": "1abcde",
    "comment_ids": ["ghi789", "jkl012"],
    "sort": "confidence"
  }
  ```

  </details>

  <details>
  <summary>Output</summary>

  ```json
  {
    "post_id": "1abcde",
    "comments": [
      {
        "id": "ghi789",
        "author": "another_user",
        "body": "Here is an expanded reply.",
        "parent_id": "t1_def456",
        "created_utc": 1784052000.0,
        "depth": 1
      }
    ],
    "more_comment_ids": ["mno345"],
    "success": true
  }
  ```

  </details>

- **`fetch_subreddit_info`** — Fetch public community metadata

  <details>
  <summary>Input</summary>

  ```json
  {
    "subreddit": "python"
  }
  ```

  </details>

  <details>
  <summary>Output</summary>

  ```json
  {
    "display_name": "Python",
    "title": "Python",
    "public_description": "News about the programming language Python.",
    "subscribers": 1496121,
    "active_user_count": null,
    "created_utc": 1201242956.0,
    "over18": false,
    "quarantined": false,
    "subreddit_type": "public",
    "url": "/r/Python/",
    "icon_img": "https://styles.redditmedia.com/example-icon.png",
    "banner_img": "https://styles.redditmedia.com/example-banner.png",
    "success": true
  }
  ```

  </details>

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
mcporter call webintel-mcp.search_reddit query="asyncio patterns" subreddit="python" sort="top" time_filter="year"
mcporter call webintel-mcp.fetch_reddit_post reference="https://www.reddit.com/r/python/comments/POST_ID/title/"
mcporter call webintel-mcp.fetch_subreddit_info subreddit="python"
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
