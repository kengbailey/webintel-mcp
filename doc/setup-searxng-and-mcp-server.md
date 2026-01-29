## Advanced: External SearxNG Setup

> **Note:** WebIntel MCP now includes a bundled SearxNG instance. You only need this guide if you want to run SearxNG as a separate, standalone service.
>
> For the standard setup, just run `docker compose up -d` — see the [main README](/README.md).

---

### Setting up a standalone SearxNG instance

1. Create a directory for your SearxNG data:
```bash
mkdir searxng-data
```

2. Create a [searxng-compose.yml](/doc/searxng-compose.yml) for SearxNG:
```yaml
services:
  searxng:
    container_name: searxng
    image: docker.io/searxng/searxng:latest
    restart: unless-stopped
    ports:
      - "8189:8080"
    volumes:
      - ./searxng-data:/etc/searxng:rw
```

3. Run SearxNG compose:
```bash
docker compose -f searxng-compose.yml up -d
```

4. Stop SearxNG and update settings:
```bash
docker compose -f searxng-compose.yml down
```

The first run creates a `settings.yaml` file in the `searxng-data` directory. Update it to enable JSON API access:

```yaml
use_default_settings: true

server:
  bind_address: "0.0.0.0"
  secret_key: "mySecretKey"  # Generate a random key
  port: 8080

search:
  safe_search: 0
  formats:
    - html
    - json     # Enables API searches

engines:
  - name: google
    engine: google
    shortcut: g

  - name: duckduckgo
    engine: duckduckgo
    shortcut: d

  - name: bing
    engine: bing
    shortcut: b

server.limiter: false
```

5. Start SearxNG again:
```bash
docker compose -f searxng-compose.yml up -d
```

6. Run WebIntel MCP pointing to your external instance:
```bash
docker run -p 3090:3090 -e SEARXNG_HOST=http://localhost:8189 ghcr.io/kengbailey/webintel-mcp:latest
```

Or using Docker Compose:
```bash
SEARXNG_HOST=http://localhost:8189 docker compose up webintel-mcp -d
```

### Verification

- SearxNG: http://localhost:8189/search
- WebIntel MCP: http://localhost:3090/mcp
