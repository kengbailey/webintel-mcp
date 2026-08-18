"""
Regression tests for SearxNG result quality post-processing.

Fixtures reproduce the behavior documented in the searxng-quality-eval
investigation: SearxNG's grouped ordering causes score inversions at the
truncation boundary (most often rank 10), near-duplicate URLs survive its
dedup hash, and untitled dead pages and a low-score single-engine tail
reach the caller. The post-processing pipeline must eliminate all of them
before max_results is applied.
"""

from unittest.mock import patch

from src.core.models import RawResult, RawSearxngResponse
from src.core.result_quality import (
    MIN_RESULT_SCORE,
    canonicalize_url,
    postprocess_results,
)
from src.core.search import SearxngClient


def make_result(url: str, title: str = "A title", score: float = 1.0, **kwargs) -> RawResult:
    return RawResult(url=url, title=title, engine="test", score=score, **kwargs)


class TestCanonicalizeUrl:
    """URL canonicalization for duplicate detection."""

    def test_scheme_and_host_case_and_http_https(self):
        assert canonicalize_url("HTTP://Example.COM/Page") == \
            canonicalize_url("https://example.com/Page")

    def test_www_folded(self):
        assert canonicalize_url("https://www.example.com/a") == \
            canonicalize_url("https://example.com/a")

    def test_trailing_slash_equivalence(self):
        assert canonicalize_url("https://example.com/docs/") == \
            canonicalize_url("https://example.com/docs")
        assert canonicalize_url("https://example.com/") == \
            canonicalize_url("https://example.com")

    def test_mobile_host_variants(self):
        assert canonicalize_url("https://m.youtube.com/watch?v=x") == \
            canonicalize_url("https://youtube.com/watch?v=x")
        assert canonicalize_url("https://en.m.wikipedia.org/wiki/Jaguar") == \
            canonicalize_url("https://en.wikipedia.org/wiki/Jaguar")

    def test_short_mobile_like_domain_not_mangled(self):
        # m.me is a real registrable domain, not a mobile variant of "me"
        assert "m.me" in canonicalize_url("https://m.me/somepage")

    def test_tracking_params_removed_meaningful_kept(self):
        with_tracking = canonicalize_url(
            "https://example.com/item?id=42&utm_source=news&utm_campaign=x&fbclid=abc"
        )
        without_tracking = canonicalize_url("https://example.com/item?id=42")
        assert with_tracking == without_tracking
        assert "id=42" in with_tracking

    def test_meaningful_params_distinguish_urls(self):
        assert canonicalize_url("https://youtube.com/watch?v=aaa") != \
            canonicalize_url("https://youtube.com/watch?v=bbb")
        assert canonicalize_url("https://example.com/list?page=2") != \
            canonicalize_url("https://example.com/list?page=3")

    def test_param_order_insensitive(self):
        assert canonicalize_url("https://example.com/?a=1&b=2") == \
            canonicalize_url("https://example.com/?b=2&a=1")

    def test_non_default_port_preserved(self):
        assert canonicalize_url("https://example.com:8443/a") != \
            canonicalize_url("https://example.com/a")

    def test_default_ports_dropped(self):
        assert canonicalize_url("https://example.com:443/a") == \
            canonicalize_url("http://example.com:80/a")

    def test_malformed_port_falls_back_to_raw_string(self):
        # urlsplit only raises on the malformed port when .port is
        # accessed; the fallback must cover that lazy ValueError too.
        assert canonicalize_url("https://example.com:notaport/x") == \
            "https://example.com:notaport/x"
        assert canonicalize_url("  https://example.com:99999/x  ") == \
            "https://example.com:99999/x"


class TestScoreThreshold:
    """Strict score > 0.40 boundary."""

    def test_exactly_040_excluded(self):
        results = [make_result("https://a.com", score=0.40)]
        assert postprocess_results(results) == []

    def test_just_above_040_included(self):
        results = [make_result("https://a.com", score=0.41)]
        assert len(postprocess_results(results)) == 1

    def test_below_040_excluded(self):
        results = [
            make_result("https://a.com", score=0.25),
            make_result("https://b.com", score=0.33),
            make_result("https://c.com", score=0.1),
        ]
        assert postprocess_results(results) == []

    def test_missing_score_excluded(self):
        results = [RawResult(url="https://a.com", title="t", engine="test")]
        assert postprocess_results(results) == []

    def test_threshold_constant(self):
        assert MIN_RESULT_SCORE == 0.40


class TestOrdering:
    """Sorted by score descending; stable for ties."""

    def test_rank10_inversion_from_deployed_sample(self):
        # Reproduces §4.1 of the investigation: "speed of light" rep1 —
        # a 9-result grouped block descending in score, then rank 10 opens
        # the next group with a fresh high score (0.25 -> 0.73 inversion).
        raw = [
            make_result("https://en.wikipedia.org/wiki/Speed_of_light", "Speed of light - Wikipedia", 4.00),
            make_result("https://www.amazon.ca", "Amazon.ca: Petits prix", 1.00),
            make_result("https://math.ucr.edu/home/baez/physics/Relativity/SpeedOfLight/speed_of_light.html", "Is The Speed of Light Everywhere the Same?", 0.70),
            make_result("https://www.amazon.ca/gp/browse.html", "Amazon.ca", 0.50),
            make_result("https://www.reddit.com/r/askscience/comments/x", "Why is the speed of light 299,792,458 m/s?", 0.50),
            make_result("https://en.wikipedia.org/wiki/Fizeau_experiment", "Fizeau's measurement", 0.50),
            make_result("https://sellercentral.amazon.ca", "Welcome to Amazon Seller Central", 0.33),
            make_result("https://www.wikidata.org/wiki/Q2111", "speed of light in vacuum - Wikidata", 0.33),
            make_result("https://music.amazon.ca", "Amazon Music", 0.25),
            make_result("https://www.britannica.com/science/speed-of-light", "Speed of light | Definition", 0.73),
        ]
        processed = postprocess_results(raw, max_results=10)
        scores = [r.score for r in processed]
        # Monotonically non-increasing — the inversion is gone
        assert scores == sorted(scores, reverse=True)
        # Britannica (0.73) sorts into third place, above the 0.50 block
        assert processed[2].url == "https://www.britannica.com/science/speed-of-light"
        # The <= 0.40 tail (0.33, 0.33, 0.25) is filtered out
        assert all(score > MIN_RESULT_SCORE for score in scores)

    def test_stable_order_for_equal_scores(self):
        raw = [
            make_result("https://first.com", "First", 0.50),
            make_result("https://second.com", "Second", 0.50),
            make_result("https://third.com", "Third", 0.50),
        ]
        processed = postprocess_results(raw)
        assert [r.url for r in processed] == [
            "https://first.com", "https://second.com", "https://third.com"
        ]

    def test_no_adjacent_inversions_generic(self):
        raw = [make_result(f"https://site{i}.com", score=s) for i, s in
               enumerate([2.5, 1.0, 0.5, 0.45, 2.12, 1.0, 0.99])]
        scores = [r.score for r in postprocess_results(raw)]
        assert all(a >= b for a, b in zip(scores, scores[1:]))


class TestTitleFilter:
    def test_empty_and_whitespace_titles_excluded(self):
        raw = [
            make_result("https://app.circleci.com", title="", score=1.0),
            make_result("https://codecov.io", title="   ", score=0.9),
            make_result("https://real.com", title="Real result", score=0.8),
        ]
        processed = postprocess_results(raw)
        assert [r.url for r in processed] == ["https://real.com"]


class TestDedup:
    """Canonical-URL dedup keeps the highest-ranked occurrence."""

    def test_duplicate_variants_collapse_to_best(self):
        raw = [
            make_result("https://tubitv.com/home", "Tubi", 1.2),
            make_result("http://www.tubitv.com/home/", "Tubi - Watch Free", 0.8),
            make_result("https://tubitv.com/home?utm_source=bing", "Tubi", 0.5),
        ]
        processed = postprocess_results(raw)
        assert len(processed) == 1
        assert processed[0].score == 1.2
        assert processed[0].url == "https://tubitv.com/home"

    def test_mobile_desktop_pair_collapses(self):
        raw = [
            make_result("https://en.wikipedia.org/wiki/Jaguar", "Jaguar", 2.0),
            make_result("https://en.m.wikipedia.org/wiki/Jaguar", "Jaguar", 0.9),
        ]
        processed = postprocess_results(raw)
        assert [r.url for r in processed] == ["https://en.wikipedia.org/wiki/Jaguar"]

    def test_distinct_urls_not_collapsed(self):
        raw = [
            make_result("https://youtube.com/watch?v=aaa", "Video A", 1.0),
            make_result("https://youtube.com/watch?v=bbb", "Video B", 0.9),
        ]
        assert len(postprocess_results(raw)) == 2

    def test_equal_score_duplicates_keep_first_seen(self):
        raw = [
            make_result("https://www.example.com/page", "From engine A", 0.5),
            make_result("https://example.com/page", "From engine B", 0.5),
        ]
        processed = postprocess_results(raw)
        assert len(processed) == 1
        assert processed[0].title == "From engine A"

    def test_malformed_url_result_does_not_abort_pipeline(self):
        raw = [
            make_result("https://good.com/page", "Good", 1.0),
            make_result("https://example.com:notaport/x", "Junk port", 0.8),
        ]
        processed = postprocess_results(raw, max_results=10)
        assert [r.url for r in processed] == [
            "https://good.com/page", "https://example.com:notaport/x"
        ]


class TestMaxResults:
    def test_fewer_than_max_after_filtering(self):
        raw = [
            make_result("https://a.com", score=1.0),
            make_result("https://b.com", score=0.40),  # filtered
            make_result("https://c.com", score=0.2),   # filtered
            make_result("https://d.com", title="", score=1.0),  # filtered
        ]
        processed = postprocess_results(raw, max_results=10)
        assert len(processed) == 1

    def test_truncation_after_sorting_keeps_best(self):
        # The best-scored result appears last in the raw grouped order;
        # slicing before sorting would drop it.
        raw = [make_result(f"https://site{i}.com", score=0.5) for i in range(10)]
        raw.append(make_result("https://best.com", score=3.0))
        processed = postprocess_results(raw, max_results=5)
        assert len(processed) == 5
        assert processed[0].url == "https://best.com"

    def test_no_limit_returns_all_eligible(self):
        raw = [make_result(f"https://site{i}.com", score=1.0) for i in range(30)]
        assert len(postprocess_results(raw, max_results=None)) == 30


class TestSearchGeneralIntegration:
    """The pipeline runs on the full pool inside search_general."""

    @patch.object(SearxngClient, '_search_raw')
    def test_full_pool_fetched_and_processed(self, mock_search_raw):
        # 12 raw results in grouped (inverted) order; caller asks for 5.
        raw = [make_result(f"https://site{i}.com", score=0.45 + 0.01 * i)
               for i in range(11)]
        raw.append(make_result("https://late-high-scorer.com", score=2.0))
        mock_search_raw.return_value = RawSearxngResponse(
            query="q", results=raw
        )

        client = SearxngClient(host="http://localhost")
        results = client.search_general("q", max_results=5)

        # _search_raw is called without max_results — no pre-slicing
        assert mock_search_raw.call_args.kwargs.get('max_results') is None
        assert len(results) == 5
        assert results[0].url == "https://late-high-scorer.com"
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    @patch.object(SearxngClient, '_search_raw')
    def test_can_return_fewer_than_requested(self, mock_search_raw):
        mock_search_raw.return_value = RawSearxngResponse(
            query="q",
            results=[
                make_result("https://only.com", score=1.0),
                make_result("https://tail.com", score=0.1),
            ],
        )
        client = SearxngClient(host="http://localhost")
        results = client.search_general("q", max_results=10)
        assert len(results) == 1
