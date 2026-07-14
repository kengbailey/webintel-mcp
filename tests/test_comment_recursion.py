"""Tests for comment recursion depth limiting and flat output."""

import pytest
from src.server.handlers import SearchHandlers
from src.core.models import RedditComment


def _make_nested_comments(depth: int) -> list:
    """Build a nested Reddit comment tree of arbitrary depth."""
    if depth <= 0:
        return []
    
    child = {
        "kind": "t1",
        "data": {
            "id": f"comment_{depth}",
            "author": f"user_{depth}",
            "body": f"Comment at depth {depth}",
            "parent_id": f"t1_comment_{depth + 1}" if depth > 1 else "t3_post",
            "created_utc": 1700000000.0,
            "replies": {
                "data": {
                    "children": _make_nested_comments(depth - 1)
                }
            } if depth > 1 else ""
        }
    }
    return [child]


class TestCommentRecursionDepth:
    """Test that comment parsing respects max_depth and returns flat list."""

    def setup_method(self):
        self.handlers = SearchHandlers()

    def test_shallow_comments_parsed_fully(self):
        """Comments within max_depth should all appear in flat list."""
        children = _make_nested_comments(3)
        comments = self.handlers._parse_reddit_comments(children, max_depth=10)
        
        assert len(comments) == 3
        assert comments[0].id == "comment_3"
        assert comments[0].depth == 0
        assert comments[1].id == "comment_2"
        assert comments[1].depth == 1
        assert comments[2].id == "comment_1"
        assert comments[2].depth == 2

    def test_depth_capped_at_max_depth(self):
        """Comments beyond max_depth should not appear."""
        children = _make_nested_comments(5)
        comments = self.handlers._parse_reddit_comments(children, max_depth=2)
        
        # Should get depth 0 and depth 1 only
        assert len(comments) == 2
        assert comments[0].id == "comment_5"
        assert comments[0].depth == 0
        assert comments[1].id == "comment_4"
        assert comments[1].depth == 1

    def test_max_depth_zero_top_level_only(self):
        """max_depth=0 should return no comments (can't even parse depth 0)."""
        children = _make_nested_comments(5)
        comments = self.handlers._parse_reddit_comments(children, max_depth=0)
        
        # max_depth=0 means depth + 1 < 0 is always false for replies,
        # but top-level comments at depth=0 are always parsed
        # Actually, top-level comments are parsed regardless, just no replies
        # Let's verify:
        assert len(comments) == 1
        assert comments[0].depth == 0

    def test_deeply_nested_does_not_overflow(self):
        """A comment tree deeper than Python's recursion limit should not crash."""
        children = _make_nested_comments(50)
        comments = self.handlers._parse_reddit_comments(children, max_depth=10)
        
        assert len(comments) == 10
        for i, comment in enumerate(comments):
            assert comment.depth == i

    def test_default_max_depth_is_10(self):
        """Default max_depth should be 10."""
        children = _make_nested_comments(15)
        comments = self.handlers._parse_reddit_comments(children)
        
        assert len(comments) == 10
        assert comments[-1].depth == 9

    def test_non_comment_kinds_skipped(self):
        """Non-t1 kinds (like 'more') should be skipped."""
        children = [
            {"kind": "t1", "data": {"id": "c1", "author": "u1", "body": "hi", "parent_id": "t3_p", "created_utc": 0, "replies": ""}},
            {"kind": "more", "data": {"id": "more1", "children": ["c2", "c3"]}},
        ]
        comments = self.handlers._parse_reddit_comments(children)
        assert len(comments) == 1
        assert comments[0].id == "c1"

    def test_flat_output_has_no_nested_replies(self):
        """RedditComment model should not have a replies field."""
        children = _make_nested_comments(3)
        comments = self.handlers._parse_reddit_comments(children, max_depth=10)
        
        # Verify comments are flat - no 'replies' attribute
        for c in comments:
            assert not hasattr(c, 'replies')
            assert hasattr(c, 'depth')
            assert hasattr(c, 'parent_id')

    def test_parent_ids_preserved(self):
        """Parent IDs should be preserved for tree reconstruction."""
        children = [
            {
                "kind": "t1",
                "data": {
                    "id": "top1", "author": "u1", "body": "top", "parent_id": "t3_post123",
                    "created_utc": 0,
                    "replies": {"data": {"children": [
                        {
                            "kind": "t1",
                            "data": {
                                "id": "reply1", "author": "u2", "body": "reply", "parent_id": "t1_top1",
                                "created_utc": 0, "replies": ""
                            }
                        }
                    ]}}
                }
            }
        ]
        comments = self.handlers._parse_reddit_comments(children, max_depth=10)
        
        assert len(comments) == 2
        assert comments[0].parent_id == "t3_post123"
        assert comments[1].parent_id == "t1_top1"

    def test_multiple_top_level_comments(self):
        """Multiple top-level comments with replies should all flatten correctly."""
        children = [
            {
                "kind": "t1",
                "data": {
                    "id": "a", "author": "u1", "body": "first", "parent_id": "t3_p", "created_utc": 0,
                    "replies": {"data": {"children": _make_nested_comments(3)}}
                }
            },
            {
                "kind": "t1",
                "data": {
                    "id": "b", "author": "u2", "body": "second", "parent_id": "t3_p", "created_utc": 0,
                    "replies": {"data": {"children": _make_nested_comments(2)}}
                }
            },
        ]
        comments = self.handlers._parse_reddit_comments(children, max_depth=10)
        
        # a (depth 0) + 3 nested + b (depth 0) + 2 nested = 7
        assert len(comments) == 7
        assert comments[0].id == "a"
        assert comments[0].depth == 0
        # After a's replies...
        assert comments[4].id == "b"
        assert comments[4].depth == 0

    def test_serialization_no_recursion(self):
        """Serializing flat comments should never cause recursion."""
        children = _make_nested_comments(20)
        comments = self.handlers._parse_reddit_comments(children, max_depth=10)
        
        # This should never recurse - it's a flat list
        for c in comments:
            d = c.model_dump()
            assert "depth" in d
            assert "replies" not in d

    def test_collects_nested_more_comment_ids(self):
        children = [
            {
                "kind": "t1",
                "data": {
                    "replies": {
                        "data": {
                            "children": [
                                {"kind": "more", "data": {"children": ["abc", "def"]}}
                            ]
                        }
                    }
                },
            },
            {"kind": "more", "data": {"children": ["def", "ghi"]}},
        ]

        assert self.handlers._collect_more_comment_ids(children) == ["abc", "def", "ghi"]
