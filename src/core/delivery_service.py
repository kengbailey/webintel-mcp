"""Provider-independent v2 orchestration. Legacy handlers remain an internal adapter."""

from __future__ import annotations

import asyncio
import re
import time

from .delivery import (
    Content,
    DeliveryError,
    Item,
    Listing,
    Meta,
    Page,
    Result,
    SnapshotStore,
    Video,
    clip,
    tokens,
)
from .reddit_fetcher import RedditFetcher
from .public_fetch import PublicWebFetcher
from .youtube_data import YouTubeData, video_id


class DeliveryService:
    def __init__(self) -> None:
        self.store = SnapshotStore()
        self.reddit = RedditFetcher()
        self.web = PublicWebFetcher()
        self.youtube = YouTubeData()

    async def fetch(
        self,
        owner: str,
        url: str,
        max_chars: int = 20000,
        mode: str = "content",
        query: str | None = None,
    ) -> Result[Content]:
        from .public_fetch import validate_url

        await validate_url(url)
        async with asyncio.timeout(35):
            text, truncated, _, _ = await self.web.fetch_and_parse(
                url, max_length=8 * 1024 * 1024
            )
        if truncated:
            raise DeliveryError(
                "DOCUMENT_TOO_LARGE", "Extracted document exceeds snapshot limit"
            )
        if mode == "outline":
            text = "\n".join(line for line in text.splitlines() if line.startswith("#"))
        elif mode == "excerpts":
            if not query or not query.strip():
                raise DeliveryError("INVALID_ARGUMENT", "Excerpts require a query")
            terms = query.casefold().split()
            text = "\n\n".join(
                f"[paragraph {i}] {part}"
                for i, part in enumerate(text.split("\n\n"))
                if any(term in part.casefold() for term in terms)
            )
        elif mode != "content":
            raise DeliveryError("INVALID_ARGUMENT", "Unknown content view")
        return self.store.content(owner, text, url, "web", max_chars, view=mode)

    def item(
        self,
        owner: str,
        x: dict,
        source: str,
        preview: bool = False,
        body_chars: int = 1200,
    ) -> Item:
        raw = x.get("body", x.get("selftext", x.get("text", ""))) or ""
        url = x.get("permalink") or x.get("url") or ""
        if url.startswith("/"):
            url = "https://www.reddit.com" + url
        if preview:
            body = clip(raw, 300, 150)
            cursor = None
        else:
            body, cursor = self.store.body(owner, raw, url, source, body_chars)
        return Item(
            id=str(x.get("id", ""))[:100],
            title=(x.get("title") or "")[:300] or None,
            url=url[:2000] or None,
            author=(x.get("author") or "")[:100] or None,
            subreddit=(x.get("subreddit") or "")[:100] or None,
            body=body,
            body_cursor=cursor,
            body_truncated=len(body) < len(raw),
            score=x.get("score", x.get("like_count")),
            num_comments=x.get("num_comments"),
            parent_id=(x.get("parent_id") or "")[:100] or None,
            reply_count=x.get("reply_count"),
            created_utc=x.get("created_utc"),
        )

    def listing(
        self,
        owner: str,
        kind: str,
        state: dict,
        limit: int,
        source: str,
        preview: bool = False,
    ) -> Result[Listing]:
        if not 1 <= limit <= 10:
            raise DeliveryError("INVALID_ARGUMENT", "Limit must be between 1 and 10")
        pending = state["pending"]
        items = []
        while pending and len(items) < limit:
            candidate = self.item(owner, pending[0], source, preview)
            trial = Listing(items=items + [candidate]).model_dump_json()
            if len(trial) > 16000 or tokens(trial) > 4000:
                break
            items.append(candidate)
            pending.pop(0)
        if pending and not items:
            raise DeliveryError(
                "DOCUMENT_TOO_LARGE", "An item cannot fit the delivery budget"
            )
        more = bool(pending or state.get("upstream") or state.get("more"))
        cursor = self.store.put(owner, kind, state) if more else None
        return Result(
            data=Listing(items=items),
            page=Page(returned=len(items), has_more=more, next_cursor=cursor),
            meta=Meta(
                source=source,
                truncated=more or any(x.body_truncated for x in items),
                fetched_at=state.get("fetched_at", time.time()),
            ),
        )

    async def reddit_search(
        self,
        owner: str,
        query: str | None,
        subreddit: str | None,
        limit: int,
        cursor: str | None,
        match: str,
        sort: str,
        time_filter: str | None,
    ) -> Result[Listing]:
        kind = "reddit_search"
        if cursor:
            state = self.store.get(owner, cursor, kind)
        else:
            if not query or not query.strip():
                raise DeliveryError("INVALID_ARGUMENT", "A search query is required")
            q = query
            if match == "title":
                q = 'title:"' + query.replace('"', "") + '"'
            elif match != "all":
                raise DeliveryError("INVALID_ARGUMENT", "match must be all or title")
            state = dict(
                pending=[],
                upstream=None,
                params=dict(
                    query=q, subreddit=subreddit, sort=sort, time_filter=time_filter
                ),
                fetched_at=time.time(),
            )
        if not state["pending"]:
            data = await self.reddit.search_posts(
                **state["params"], limit=10, after=state["upstream"]
            )
            listing = data.get("data", {})
            state["pending"] = [
                x["data"] for x in listing.get("children", []) if x.get("kind") == "t3"
            ]
            after = listing.get("after")
            state["upstream"] = after if after != state["upstream"] else None
        return self.listing(owner, kind, state, limit, "reddit", preview=True)

    async def subreddit(
        self,
        owner: str,
        subreddit: str | None,
        sort: str,
        time_filter: str | None,
        limit: int,
        cursor: str | None,
    ) -> Result[Listing]:
        kind = "subreddit"
        if cursor:
            state = self.store.get(owner, cursor, kind)
        else:
            if not subreddit:
                raise DeliveryError("INVALID_ARGUMENT", "A subreddit is required")
            state = dict(
                pending=[],
                upstream=None,
                params=dict(subreddit=subreddit, sort=sort, time_filter=time_filter),
                fetched_at=time.time(),
            )
        if not state["pending"]:
            data = await self.reddit.fetch_subreddit_posts(
                **state["params"], limit=10, after=state["upstream"]
            )
            listing = data.get("data", {})
            state["pending"] = [
                x["data"] for x in listing.get("children", []) if x.get("kind") == "t3"
            ]
            after = listing.get("after")
            state["upstream"] = after if after != state["upstream"] else None
        return self.listing(owner, kind, state, limit, "reddit", preview=True)

    async def post(self, owner: str, reference: str) -> Result[Item]:
        ident, sub = await self.reddit.resolve_post_reference(reference)
        # /api/info avoids downloading the comment tree entirely.
        r = await self.reddit._get(
            self.reddit.BASE_URL + "/api/info", {"id": "t3_" + ident, "raw_json": 1}
        )
        children = r.json().get("data", {}).get("children", [])
        if not children:
            raise DeliveryError("NOT_FOUND", "Reddit post is unavailable")
        item = self.item(owner, children[0]["data"], "reddit", body_chars=20000)
        return Result(
            data=item, meta=Meta(source="reddit", truncated=item.body_truncated)
        )

    @staticmethod
    def flatten(children: list[dict], seen: list[str]) -> tuple[list[dict], list[str]]:
        pending, more = [], []
        visited = set(seen)
        stack = list(reversed(children))
        while stack:
            child = stack.pop()
            x = child.get("data", {})
            if child.get("kind") == "more":
                more.extend(i for i in x.get("children", []) if i not in visited)
            elif child.get("kind") == "t1":
                if x.get("id") not in visited:
                    visited.add(x.get("id"))
                    seen.append(x.get("id"))
                    pending.append({k: v for k, v in x.items() if k != "replies"})
                replies = x.get("replies")
                if isinstance(replies, dict):
                    stack.extend(reversed(replies.get("data", {}).get("children", [])))
        return pending, list(dict.fromkeys(more))

    async def comments(
        self,
        owner: str,
        reference: str | None,
        limit: int,
        cursor: str | None,
        sort: str,
        parent_id: str | None,
    ) -> Result[Listing]:
        kind = "reddit_comments"
        if cursor:
            state = self.store.get(owner, cursor, kind)
        else:
            if not reference:
                raise DeliveryError("INVALID_ARGUMENT", "Post reference is required")
            ident, sub = await self.reddit.resolve_post_reference(reference)
            if parent_id and not re.fullmatch(r"(?:t1_)?[A-Za-z0-9]{1,12}", parent_id):
                raise DeliveryError("INVALID_ARGUMENT", "Invalid parent comment ID")
            raw = await self.reddit.fetch_post_with_comments(
                sub,
                ident,
                sort=sort,
                limit=100,
                depth=1,
                comment_id=parent_id.removeprefix("t1_") if parent_id else None,
            )
            state = dict(
                post_id=ident,
                sort=sort,
                seen=[],
                pending=[],
                more=[],
                fetched_at=time.time(),
            )
            state["pending"], state["more"] = self.flatten(
                raw[1].get("data", {}).get("children", []), state["seen"]
            )
        if not state["pending"] and state["more"]:
            batch, state["more"] = state["more"][:20], state["more"][20:]
            raw = await self.reddit.fetch_more_comments(
                state["post_id"], batch, state["sort"]
            )
            if raw.get("json", {}).get("errors"):
                raise DeliveryError(
                    "UPSTREAM_ERROR", "Reddit rejected comment expansion"
                )
            things = raw.get("json", {}).get("data", {}).get("things", [])
            state["pending"], more = self.flatten(things, state["seen"])
            state["more"] = list(
                dict.fromkeys(state["more"] + [i for i in more if i not in batch])
            )
        return self.listing(owner, kind, state, limit, "reddit")

    async def video(self, owner: str, reference: str) -> Result[Video]:
        data = await self.youtube.metadata(reference)
        url = "https://www.youtube.com/watch?v=" + data["id"]
        body, cursor = self.store.body(
            owner, data.get("description") or "", url, data["source"], 4000
        )
        fields = {
            k: data.get(k)
            for k in (
                "id",
                "title",
                "channel",
                "duration",
                "published_at",
                "view_count",
                "like_count",
                "comment_count",
            )
        }
        fields["title"] = (fields["title"] or "")[:500] or None
        fields["channel"] = (fields["channel"] or "")[:200] or None
        return Result(
            data=Video(**fields, url=url, description=body, description_cursor=cursor),
            meta=Meta(
                source=data["source"],
                truncated=bool(cursor),
                warnings=["Public dislike counts are unavailable"],
            ),
        )

    async def video_comments(
        self,
        owner: str,
        reference: str | None,
        limit: int,
        cursor: str | None,
        order: str,
        parent_id: str | None,
        query: str | None,
    ) -> Result[Listing]:
        kind = "youtube_comments"
        if cursor:
            state = self.store.get(owner, cursor, kind)
        else:
            if not reference:
                raise DeliveryError("INVALID_ARGUMENT", "Video reference is required")
            ident = video_id(reference)
            if order not in ("relevance", "time"):
                raise DeliveryError(
                    "INVALID_ARGUMENT", "order must be relevance or time"
                )
            params = dict(part="snippet", maxResults=10, textFormat="plainText")
            if parent_id:
                params["parentId"] = parent_id
            else:
                params.update(videoId=ident, order=order)
                if query:
                    params["searchTerms"] = query
            state = dict(
                pending=[],
                upstream=None,
                params=params,
                endpoint="comments" if parent_id else "commentThreads",
                fetched_at=time.time(),
            )
        if not state["pending"]:
            params = dict(state["params"])
            if state["upstream"]:
                params["pageToken"] = state["upstream"]
            raw = await self.youtube.api(state["endpoint"], params)
            for entry in raw.get("items", []):
                top = entry.get("snippet", {}).get("topLevelComment", entry)
                s = top["snippet"]
                state["pending"].append(
                    dict(
                        id=top["id"],
                        body=s.get("textDisplay", ""),
                        author=s.get("authorDisplayName"),
                        like_count=s.get("likeCount"),
                        parent_id=s.get("parentId"),
                        reply_count=entry.get("snippet", {}).get("totalReplyCount"),
                    )
                )
            after = raw.get("nextPageToken")
            state["upstream"] = after if after != state["upstream"] else None
        return self.listing(owner, kind, state, limit, "youtube_api")
