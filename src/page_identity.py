"""Page identity and the story-named-query rule.

This module is the one place that decides what "the same page" means, and when
a query string stops being incidental.

THE RULE
--------
Page identity is scheme + host + path. The query and fragment are not identity
by default, because the SPA mocks encode state in the query
(``success.html?item=blue-top``) and a red-top page is still the same page.

That default is not always right. A story about one product, one filter, one
search result or one variant DOES mean the query. When the story names the bit
after the ``?``, the query is pinned:

- the generated assertion carries the candidate query, not just the page
  identity, so a different query fails;
- the evidence record says ``query_rule='story-pins-query'`` instead of
  ``query_rule='identity'``.

WHAT A STORY WRITER TYPES
-------------------------
Put the query pair, or the full URL, in the story. Either shape pins it::

    The cart URL must contain item=blue-top.
    Open https://shop.example.com/cart.html?item=blue-top

A story that only says "the cart page" does not pin a query. Values alone
("blue-top") are not enough, because the tool cannot know which parameter the
word belongs to.

The rule lives here so the next change reads it instead of rediscovering it.
``EvidenceTracker._same_page`` delegates here, and the placeholder resolver
imports :func:`story_pins_query`.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlparse

# A key=value pair. The value stops at whitespace, another separator, or a
# quote, so prose after the pair is not swallowed.
_QUERY_PAIR = re.compile(r"(?<![\w.-])([A-Za-z_][\w.-]*)=([^\s&?#\"'<>]+)")
_FULL_URL = re.compile(r"https?://[^\s\"'<>]+")


def page_key(url: str) -> tuple[str, str, str] | None:
    """Return (scheme, host, path) for *url*, or ``None`` when it has no host."""
    parsed = urlparse(str(url))
    host = parsed.netloc.lower()
    if not host:
        return None
    return (parsed.scheme.lower(), host, parsed.path.rstrip("/") or "/")


def same_page(expected: str, actual: str) -> bool:
    """Return True when two URLs address the same page (ignoring query/fragment).

    Trailing slashes are ignored. Anything unparseable counts as a match so a
    parse failure never raises a false mismatch.
    """
    if not expected or not actual:
        return True
    try:
        left, right = page_key(expected), page_key(actual)
    except Exception:
        return True
    if left is None or right is None:
        return True
    return left == right


def query_pairs(url: str) -> set[tuple[str, str]]:
    """Return the decoded key/value pairs in *url*'s query string."""
    try:
        return {(key, value) for key, value in parse_qsl(urlparse(str(url)).query, keep_blank_values=True) if key}
    except Exception:
        return set()


def story_query_pairs(story: str) -> set[tuple[str, str]]:
    """Return the query pairs a story names explicitly.

    Reads both ``key=value`` tokens and full URLs. A bare value (``blue-top``)
    is not a query pair: the writer must name the parameter too.
    """
    pairs: set[tuple[str, str]] = set()
    for match in _QUERY_PAIR.finditer(story or ""):
        value = match.group(2)
        # A query pair in prose is often followed by a comma or a full stop.
        if value and value[-1] in ".,;:!" and (match.end() == len(story or "") or (story or "")[match.end()].isspace()):
            value = value[:-1]
        pairs.add((match.group(1), value))
    for match in _FULL_URL.finditer(story or ""):
        pairs.update(query_pairs(match.group(0).rstrip(".,;:")))
    return pairs


def story_pins_query(story: str, candidate_url: str) -> bool:
    """Return True when the story pins the query of *candidate_url*.

    A candidate with no query can never be pinned. A story pins it by naming
    one of its ``key=value`` pairs, or by containing the candidate's exact
    query string.
    """
    candidate_pairs = query_pairs(candidate_url)
    if not candidate_pairs:
        return False

    story_text = story or ""
    candidate_query = urlparse(str(candidate_url)).query
    if candidate_query and candidate_query in story_text:
        return True

    return bool(candidate_pairs & story_query_pairs(story_text))
