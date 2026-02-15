"""Tests for comment recursion depth limiting."""

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
    """Test that comment parsing respects max_depth to prevent recursion overflow."""

    def setup_method(self):
        self.handlers = SearchHandlers()

    def test_shallow_comments_parsed_fully(self):
        """Comments within max_depth should be fully parsed."""
        children = _make_nested_comments(3)
        comments = self.handlers._parse_reddit_comments(children, max_depth=10)
        
        assert len(comments) == 1
        assert comments[0].id == "comment_3"
        
        # Should have nested replies
        assert len(comments[0].replies) == 1
        assert comments[0].replies[0].id == "comment_2"
        assert len(comments[0].replies[0].replies) == 1
        assert comments[0].replies[0].replies[0].id == "comment_1"

    def test_depth_capped_at_max_depth(self):
        """Comments beyond max_depth should have empty replies."""
        children = _make_nested_comments(5)
        comments = self.handlers._parse_reddit_comments(children, max_depth=2)
        
        assert len(comments) == 1
        # Depth 0 -> depth 1 -> depth 2 (stop)
        level1 = comments[0]
        assert level1.id == "comment_5"
        assert len(level1.replies) == 1
        
        level2 = level1.replies[0]
        assert level2.id == "comment_4"
        # max_depth=2, so depth 2 should NOT recurse further
        assert len(level2.replies) == 0

    def test_max_depth_zero_no_replies(self):
        """max_depth=0 should return top-level comments with no replies."""
        children = _make_nested_comments(5)
        comments = self.handlers._parse_reddit_comments(children, max_depth=0)
        
        assert len(comments) == 1
        assert comments[0].replies == []

    def test_deeply_nested_does_not_overflow(self):
        """A comment tree deeper than Python's recursion limit should not crash."""
        # Build a tree 50 levels deep — would overflow without the cap
        children = _make_nested_comments(50)
        comments = self.handlers._parse_reddit_comments(children, max_depth=10)
        
        # Should parse 10 levels and stop
        current = comments[0]
        parsed_depth = 1
        while current.replies:
            current = current.replies[0]
            parsed_depth += 1
        
        assert parsed_depth == 10

    def test_default_max_depth_is_10(self):
        """Default max_depth should be 10."""
        children = _make_nested_comments(15)
        comments = self.handlers._parse_reddit_comments(children)
        
        current = comments[0]
        parsed_depth = 1
        while current.replies:
            current = current.replies[0]
            parsed_depth += 1
        
        assert parsed_depth == 10

    def test_non_comment_kinds_skipped(self):
        """Non-t1 kinds (like 'more') should be skipped."""
        children = [
            {"kind": "t1", "data": {"id": "c1", "author": "u1", "body": "hi", "parent_id": "t3_p", "created_utc": 0, "replies": ""}},
            {"kind": "more", "data": {"id": "more1", "children": ["c2", "c3"]}},
        ]
        comments = self.handlers._parse_reddit_comments(children)
        assert len(comments) == 1
        assert comments[0].id == "c1"

    def test_multiple_top_level_with_depth(self):
        """Multiple top-level comments each respect max_depth independently."""
        children = [
            {
                "kind": "t1",
                "data": {
                    "id": "a", "author": "u1", "body": "first", "parent_id": "t3_p", "created_utc": 0,
                    "replies": {"data": {"children": _make_nested_comments(5)}}
                }
            },
            {
                "kind": "t1",
                "data": {
                    "id": "b", "author": "u2", "body": "second", "parent_id": "t3_p", "created_utc": 0,
                    "replies": {"data": {"children": _make_nested_comments(5)}}
                }
            },
        ]
        comments = self.handlers._parse_reddit_comments(children, max_depth=2)
        
        assert len(comments) == 2
        for c in comments:
            # Each top-level has 1 reply, and that reply's replies are capped
            assert len(c.replies) == 1
            assert len(c.replies[0].replies) == 0
