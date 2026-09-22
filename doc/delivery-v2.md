# Bounded delivery v2

Opt-in interface for WebIntel. The existing `src.server.mcp_server` entry point and
its schemas remain available. **Do not point existing clients at v2 without
refreshing their tool catalogs.** V2 web/video search uses Exa. The legacy entry point and current Compose stack
still use SearxNG until a separately approved production migration.

## Run

Install `requirements.txt` in a Python 3.11+ virtual environment, then:

```sh
python -m src.server.delivery_server --host 127.0.0.1 --port 3091
# Legacy clients that need SSE:
python -m src.server.delivery_server --port 3091 --transport sse
```

HTTP endpoint `/mcp`; SSE endpoint `/sse`. No deployment/Compose edits are needed
to try v2 on a separate port. Existing AuthKit and machine JWT configuration is
reused, with the new endpoint's correct public resource URL when authentication
is enabled. Bind to a LAN address explicitly if needed; default is loopback.

## Contract

Every successful tool returns typed `Result[T]`:

```json
{
  "schema_version": 2,
  "status": "ok",
  "data": {"items": []},
  "page": {"returned": 0, "has_more": false, "next_cursor": null},
  "meta": {"source": "reddit", "truncated": false, "fetched_at": 1790000000.0, "warnings": []}
}
```

`returned` means items for listings, characters for content chunks. Errors use MCP
`isError` and a JSON text object containing stable `code` and safe `message`.
Invalid MCP arguments use framework validation errors. Empty results are success.
Unavailable values are null rather than fabricated zeros.

Both the text fallback and structured result carry the same bounded payload.
Clients should consume one representation, not concatenate both. JSON alone does
not reduce model context consumption.

### Tools

| Tool | Default delivery | Continuation |
| --- | --- | --- |
| `search` | 5 Exa web previews | Same tool + `cursor` if budget overflow |
| `search_videos` | 5 Exa video previews | Same tool + `cursor` |
| `fetch_content` | Up to 20,000 chars / 5,000 estimated body tokens | `read_content(cursor)` |
| `read_content` | Next stored text chunk | Same tool + next cursor |
| `search_reddit` | 5 previews, optional subreddit/title matching | Same tool + cursor |
| `fetch_subreddit` | 5 post previews | Same tool + cursor |
| `fetch_subreddit_info` | Public community metadata | `read_content` for long descriptions |
| `fetch_reddit_post` | Metadata and bounded post body, **no comments** | `read_content(body_cursor)` |
| `fetch_reddit_comments` | 10 bounded comments; optional parent/thread focus | Same tool + cursor; `read_content` for long bodies |
| `fetch_youtube_content` | Metadata and up to 4,000 description chars | `read_content(description_cursor)` |
| `fetch_youtube_transcript` | Captions first, STT fallback; `source="stt"` bypasses captions | `read_content` |
| `fetch_youtube_comments` | 10 top-level comments; `parent_id` explicitly requests replies | Same tool + cursor; `read_content` for long bodies |

Listing `limit` is 1–10. Search previews are at most 300 characters / 150 estimated
tokens. Individual comment bodies initially return up to 1,200 characters, with
lossless continuation. Entire listing data is capped at 16,000 serialized chars /
4,000 estimated tokens; envelope overhead is additional. Shorter-than-requested
pages are normal. An empty comment page can still have a continuation if Reddit
expansion returned only additional placeholders or unavailable comments.

On listing continuation, **saved original filters are used**. Omit the original
query/filter arguments, supply only cursor and desired limit. A cursor from a
different tool is rejected. `has_more` means more server/provider state is available,
not that every remaining comment is guaranteed readable.

`fetch_content(mode="outline")` returns Markdown headings. `mode="excerpts"`
requires `query` and selects matching paragraphs with their original paragraph
indices. These are explicitly selected views, not summaries or complete coverage.
For comment/post/description body cursors, only `read_content` is appropriate.

### Storage and budgets

- `o200k_base` token estimate, not a guarantee for every model tokenizer. Special
  token spellings in source text are treated as ordinary untrusted text.
- Immutable snapshots: paging text does not refetch the URL or rerun extraction.
- 15-minute TTL from cursor creation, 128 MiB aggregate cache, 8 MiB individual
  serialized snapshot limit. LRU eviction can expire a cursor early.
- Cursors are random opaque capabilities, not encoded upstream comment IDs.
- Authenticated cursors are scoped to the bearer-token hash. Token rotation may
  invalidate access to existing cursors; no raw tokens are stored in snapshots.
- Anonymous LAN callers share a principal. Random cursors are unguessable, but
  authentication is required for caller isolation. Do not share cursor values.
- Cache is process-local and lost on restart. Multi-worker deployments need shared
  storage or sticky routing before adoption; v2 currently targets one process.
- Overflow items from an upstream page are retained before following its next-page
  token. Long comment bodies retain full bounded text behind body cursors.

## Fetch behavior

The v2 fetcher reuses a lifecycle-managed HTTP client, understands native Markdown
and plain text, offloads HTML extraction, and bounds decompressed downloads.
Browser rendering has a two-page concurrency limit and uses DOM load plus bounded
text stability rather than requiring network idle. The complete web operation has
a 35-second deadline, inside a 45-second tool deadline. Browser pages and metadata
subprocesses are cleaned up on cancellation.

Only public HTTP(S) targets without URL credentials are supported. Initial URLs,
static redirects and browser requests undergo address checks; private/loopback/
reserved targets are rejected. This is not a DNS-rebinding-proof network sandbox;
untrusted/public deployments should additionally enforce network egress policy.
Existing proxy controls remain in use. Jina fallback is still public-URL-only.

The legacy Jina/PDF path is fixed too: it no longer destroys the rest of the
content before offset pagination. Legacy chunk size/schema otherwise remains
unchanged. v2 is where the new 20k + token-budget defaults apply.

## Credentials and limitations

- Reddit: existing `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT`
  and optional `REDDIT_PROXY_URL`.
- YouTube: optional **`YOUTUBE_API_KEY`** for official metadata; **required** for
  stable comments/replies pagination. Missing key returns `NOT_CONFIGURED` for
  comments. No account or key is needed for best-effort yt-dlp metadata/captions.
- `YOUTUBE_PROXY_URL` retains the existing per-provider routing behavior.
- `fetch_youtube_transcript` defaults to `source="captions"` (manual preferred,
  automatic captions preferred after manual). Caption retrieval failures fall back
  to STT by default. Set `fallback_to_stt=false` for captions-only errors without
  audio work. Invalid references and cancellation never trigger fallback.
  Set `source="stt"` to explicitly download audio and transcribe using existing
  `STT_ENDPOINT`, `STT_MODEL`, and `STT_API_KEY`. `language` hints transcription;
  STT returns plain text, without guaranteed timestamps. Continuation uses
  `read_content` without downloading/transcribing again.
- Explicit STT limits: non-live video, 25 MiB audio upload,
  64 MiB monitored temporary storage, 120-second download deadline and 300-second
  tool deadline. Clients should allow at least 300 seconds when STT is enabled (including default
  caption fallback). Caption attempts have a 45-second deadline.
  Audio/ffmpeg process group is killed on cancellation; temporary files are removed
  on success/failure/cancellation. No automatic retries. Other tools and captions-only requests retain 45 seconds.
- Public dislike count is null. Owner-authorized dislikes and third-party estimates
  are not implemented; descriptions never imply otherwise.
- Native Reddit search remains the Reddit discovery source. Subreddit scope and
  optional title matching reduce noise; compact output alone is not a relevance
  guarantee. Authenticated Exa smoke tests returned zero Reddit hits with bare
  domain, subreddit paths, wildcard paths, and `site:` queries, including with
  content extraction disabled. Do not recommend Exa as the Reddit replacement
  based on the earlier anonymous hosted-MCP pilot. Root cause is not established.
- `fetch_more_comments` is superseded in v2 by cursor-based
  `fetch_reddit_comments`; no exposed arrays of expansion IDs are required.
- FastMCP is pinned to 4.0.5; tiktoken to 0.14.0. This is not a full transitive lock.
  Dockerfile/Compose are unchanged; the existing Dockerfile's yt-dlp prerelease
  override must be addressed separately before a reproducibly pinned image rollout.

## Verification

```sh
python -m pytest tests/ -q -m 'not integration' \
  --ignore=tests/test_searxng_integration.py \
  --ignore=tests/test_youtube_integration.py
```

`test_delivery.py` covers Unicode/special-token losslessness, cursor scope/expiry/
eviction, immutable snapshots, Jina recovery, overflow retention, comments without
duplicates, post-only retrieval, metadata without implicit work, API errors, URL
checks and native Markdown. `test_delivery_transport.py` launches real loopback
HTTP and SSE servers and verifies schemas and tool errors. These do not claim
full OAuth browser-flow or all-platform client acceptance.

## Exa search configuration

Set `EXA_API_KEY` in the v2 server environment. Keep it in an owner-only runtime
secret/env file, never in the repository. Missing credentials fail explicitly;
there is no silent SearxNG fallback. The existing production stack is unchanged.

Each new `search` or `search_videos` call makes one Exa `type=auto` request,
requesting at most 10 results and 350 text characters per result; delivery further
clips previews to 300 characters / 150 estimated tokens. No full page, generated
summary, deep search, automatic retry, or hidden query fan-out is requested.
Provider result order is preserved, duplicate URLs are removed, and no provider
score is treated as a cross-provider relevance threshold.

`search` supports `include_domains`, `exclude_domains` (up to 20 domain/path
filters each), `start_published_date` and `end_published_date` (ISO-8601 timestamps
with timezone). Prefer domain filters over inserting `site:` into the query.
`search_videos` restricts discovery to YouTube video paths and validates returned
video URLs; filtering can produce fewer results, without another paid request.

Exa has no offset pagination here. A cursor only drains already-retrieved results
that overflowed the response budget; `has_more=false` is not an assertion that the
web contains no other matches. To discover more, explicitly submit a new query.
Provider errors return safe codes, never upstream response bodies or credentials.
Authenticated relevance/latency evaluation is a separate check from mock tests.

### Authenticated Oak smoke results (2026-09-22)

Six initial MCP searches completed with a median 1.054 seconds. Nonempty five-item
responses used 1,040–1,227 estimated tokens. Domain allow/exclude checks and bounded
preview assertions passed; the publication-date request was accepted, but result
dates were not independently verified. YouTube returned valid video URLs, though
only the first result was a direct backup tutorial; ranking still needs judgment.
Reddit returned zero hits in the initial case and five follow-up variants. Keep
native Reddit discovery. These are small live smoke tests, not reliability or
cross-provider superiority measurements. No deployment was performed.
