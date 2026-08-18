"""
Result quality post-processing for SearxNG search results.

SearxNG returns its merged result pool in a UI-oriented grouped order
(results re-clustered by category/template/thumbnail after score sorting),
which produces score inversions at group boundaries, and its dedup hash
treats tracking parameters, `www.`/mobile hosts, and thumbnail presence as
identity-relevant, so near-duplicate URLs survive. This module restores the
ordering contract a JSON API caller expects: sort by score, drop low-signal
results, deduplicate canonicalized URLs, and only then apply the caller's
maximum.

Pipeline (order matters — truncation must come last):
1. Drop results with an empty or whitespace-only title.
2. Drop results whose score is missing or <= MIN_RESULT_SCORE (strict:
   only score > MIN_RESULT_SCORE survives).
3. Sort by score descending. The sort is stable, so results with equal
   scores keep their original SearxNG order.
4. Deduplicate by canonical URL, keeping the highest-ranked occurrence.
5. Truncate to max_results. Because filtering happens first, callers can
   receive fewer than max_results — max_results is a maximum, not a
   guarantee.
"""

from typing import List, Optional
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from .models import RawResult

# Results at or below this score are excluded. With all engine weights at
# 1.0, a score of 0.40 or less means a single engine ranked the result 3rd
# or worse with no cross-engine corroboration — the low-signal tail.
MIN_RESULT_SCORE = 0.40

# Query parameters that only track the click, never select content.
# Removing them merges duplicate URLs; all other parameters are preserved
# because they can be semantically meaningful (e.g. ?v=, ?id=, ?q=).
_TRACKING_PARAMS = {
    'gclid', 'fbclid', 'msclkid', 'yclid', 'igshid', 'twclid',
    'mc_cid', 'mc_eid', '_hsenc', '_hsmi', 'ref_src', 'spm',
}
_TRACKING_PREFIXES = ('utm_',)

# Mobile host labels that are safe to fold into the desktop host, either
# leading (m.example.com) or internal (en.m.wikipedia.org).
_MOBILE_LABELS = {'m', 'mobile'}


def _canonical_host(host: str) -> str:
    """Normalize a hostname for dedup: lowercase, strip `www.` and mobile
    labels where the remainder is still a plausible registrable domain."""
    host = host.lower().rstrip('.')
    labels = host.split('.')
    if len(labels) > 2 and labels[0] == 'www':
        labels = labels[1:]
    # Fold a leading or internal mobile label (m.example.com,
    # en.m.wikipedia.org) only when at least two labels remain, so short
    # real domains like m.me are never mangled.
    for i, label in enumerate(labels[:-1]):
        if label in _MOBILE_LABELS and len(labels) > 2:
            labels = labels[:i] + labels[i + 1:]
            break
    return '.'.join(labels)


def canonicalize_url(url: str) -> str:
    """
    Produce a canonical form of a URL for duplicate detection.

    Normalizes: scheme case (with http treated as https), host case,
    `www.` and safe mobile-host variants, default ports, trailing slash,
    and known tracking parameters. Meaningful query parameters and
    fragments are preserved. Falls back to the raw string if parsing
    fails, so an odd URL is never dropped by accident.
    """
    raw = url.strip()
    try:
        parts = urlsplit(raw)

        scheme = parts.scheme.lower()
        if scheme == 'http':
            scheme = 'https'

        host = _canonical_host(parts.hostname or '')
        port = parts.port
        # 80/443 are the defaults for the http/https pair this scheme was
        # normalized from; any other port distinguishes a different server.
        if port and not (scheme == 'https' and port in (80, 443)):
            host = f"{host}:{port}"

        path = parts.path.rstrip('/')

        query_pairs = [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key.lower() not in _TRACKING_PARAMS
            and not key.lower().startswith(_TRACKING_PREFIXES)
        ]
        query = urlencode(sorted(query_pairs))

        return urlunsplit((scheme, host, path, query, parts.fragment))
    except ValueError:
        return raw


def postprocess_results(
    results: List[RawResult],
    max_results: Optional[int] = None
) -> List[RawResult]:
    """
    Apply the quality pipeline to a full SearxNG result list, then
    truncate to max_results. See module docstring for the stages.

    Args:
        results: The complete (unsliced) merged result list from SearxNG
        max_results: Maximum number of results to keep (None = no limit)

    Returns:
        Up to max_results of the best remaining results, scores
        monotonically non-increasing. May be fewer than max_results.
    """
    eligible = [
        result for result in results
        if result.title and result.title.strip()
        and result.score is not None
        and result.score > MIN_RESULT_SCORE
    ]

    eligible.sort(key=lambda result: result.score, reverse=True)

    deduped = []
    seen_urls = set()
    for result in eligible:
        canonical = canonicalize_url(result.url)
        if canonical in seen_urls:
            continue
        seen_urls.add(canonical)
        deduped.append(result)

    if max_results is not None:
        return deduped[:max_results]
    return deduped
