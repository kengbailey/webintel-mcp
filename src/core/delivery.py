"""Bounded, caller-scoped, in-memory delivery snapshots (no provider I/O)."""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from collections import OrderedDict
from typing import Any, Generic, Literal, TypeVar

import tiktoken
from pydantic import BaseModel, Field

MAX_CHARS = 20_000
MAX_TOKENS = 5_000
MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
_ENCODING = tiktoken.get_encoding("o200k_base")


class DeliveryError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class Page(BaseModel):
    returned: int = 0
    has_more: bool = False
    next_cursor: str | None = None


class Meta(BaseModel):
    source: str
    truncated: bool = False
    fetched_at: float = Field(default_factory=time.time)
    warnings: list[str] = Field(default_factory=list)


T = TypeVar("T")


class Result(BaseModel, Generic[T]):
    schema_version: Literal[2] = 2
    status: Literal["ok", "partial"] = "ok"
    data: T
    page: Page = Field(default_factory=Page)
    meta: Meta


class Content(BaseModel):
    url: str
    content: str
    offset: int
    total_chars: int
    content_id: str
    view: str = "content"
    estimated_tokens: int


class Item(BaseModel):
    id: str
    title: str | None = None
    url: str | None = None
    author: str | None = None
    subreddit: str | None = None
    body: str = ""
    body_cursor: str | None = None
    body_truncated: bool = False
    score: int | None = None
    num_comments: int | None = None
    parent_id: str | None = None
    reply_count: int | None = None
    created_utc: float | None = None


class Listing(BaseModel):
    items: list[Item]


class Video(BaseModel):
    id: str
    title: str | None = None
    channel: str | None = None
    description: str = ""
    description_cursor: str | None = None
    duration: float | None = None
    published_at: str | None = None
    view_count: int | None = None
    like_count: int | None = None
    dislike_count: int | None = None
    comment_count: int | None = None
    url: str


def tokens(text: str) -> int:
    return len(_ENCODING.encode(text, disallowed_special=()))


def clip(text: str, max_chars: int = MAX_CHARS, max_tokens: int = MAX_TOKENS) -> str:
    """Return an exact Unicode prefix, never token-decoding partial UTF-8."""
    if not 1 <= max_chars <= MAX_CHARS or not 1 <= max_tokens <= MAX_TOKENS:
        raise DeliveryError("INVALID_ARGUMENT", "Invalid output budget")
    prefix = text[:max_chars]
    if tokens(prefix) <= max_tokens:
        return prefix
    lo, hi = 0, len(prefix)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if tokens(prefix[:mid]) <= max_tokens:
            lo = mid
        else:
            hi = mid - 1
    return prefix[:lo]


class SnapshotStore:
    """Immutable JSON snapshots. Cursors are random capabilities scoped to caller.

    Anonymous LAN callers share a principal; authentication is needed for isolation.
    Size/TTL limits bound memory, including paging state, not just document bodies.
    """

    def __init__(self, ttl: float = 900, max_bytes: int = 128 * 1024 * 1024):
        self.ttl, self.max_bytes = ttl, max_bytes
        self._entries: OrderedDict[str, tuple[float, str, bytes]] = OrderedDict()
        self._bytes = 0
        self._lock = threading.RLock()

    def _purge(self) -> None:
        now = time.monotonic()
        for key, (expiry, _, raw) in list(self._entries.items()):
            if expiry <= now:
                self._bytes -= len(raw)
                del self._entries[key]

    def put(self, owner: str, kind: str, data: dict[str, Any]) -> str:
        raw = json.dumps({"kind": kind, "data": data}, ensure_ascii=False).encode()
        if len(raw) > min(MAX_DOCUMENT_BYTES, self.max_bytes):
            raise DeliveryError("DOCUMENT_TOO_LARGE", "Snapshot exceeds storage limit")
        with self._lock:
            self._purge()
            while self._bytes + len(raw) > self.max_bytes:
                _, (_, _, old) = self._entries.popitem(last=False)
                self._bytes -= len(old)
            key = secrets.token_urlsafe(32)
            self._entries[key] = (time.monotonic() + self.ttl, owner, raw)
            self._bytes += len(raw)
            return key

    def get(self, owner: str, cursor: str, kind: str) -> dict[str, Any]:
        with self._lock:
            self._purge()
            entry = self._entries.get(cursor)
            if not entry or not secrets.compare_digest(entry[1], owner):
                raise DeliveryError(
                    "CURSOR_EXPIRED",
                    "Cursor expired, evicted, or unavailable to this caller",
                )
            payload = json.loads(entry[2])
            if payload["kind"] != kind:
                raise DeliveryError("INVALID_CURSOR", "Cursor belongs to another tool")
            self._entries.move_to_end(cursor)
            return payload["data"]

    def content(
        self,
        owner: str,
        text: str,
        url: str,
        source: str,
        max_chars: int = MAX_CHARS,
        offset: int = 0,
        view: str = "content",
        fetched_at: float | None = None,
    ) -> Result[Content]:
        if offset < 0 or offset > len(text):
            raise DeliveryError("INVALID_ARGUMENT", "Offset is outside this snapshot")
        part = clip(text[offset:], max_chars)
        end = offset + len(part)
        fetched_at = fetched_at or time.time()
        cursor = (
            self.put(
                owner,
                "content",
                dict(
                    text=text,
                    url=url,
                    source=source,
                    offset=end,
                    view=view,
                    fetched_at=fetched_at,
                ),
            )
            if end < len(text)
            else None
        )
        return Result(
            data=Content(
                url=url,
                content=part,
                offset=offset,
                total_chars=len(text),
                content_id=hashlib.sha256(text.encode()).hexdigest(),
                view=view,
                estimated_tokens=tokens(part),
            ),
            page=Page(returned=len(part), has_more=bool(cursor), next_cursor=cursor),
            meta=Meta(source=source, truncated=bool(cursor), fetched_at=fetched_at),
        )

    def read(
        self, owner: str, cursor: str, max_chars: int = MAX_CHARS
    ) -> Result[Content]:
        return self.content(
            owner=owner, max_chars=max_chars, **self.get(owner, cursor, "content")
        )

    def body(
        self, owner: str, text: str, url: str, source: str, max_chars: int = 1200
    ) -> tuple[str, str | None]:
        result = self.content(owner, text, url, source, max_chars)
        return result.data.content, result.page.next_cursor


class Community(BaseModel):
    name: str
    title: str
    description: str
    description_cursor: str | None = None
    subscribers: int | None = None
    active_user_count: int | None = None
    over18: bool = False
    url: str
