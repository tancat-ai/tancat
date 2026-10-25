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
after the ``?`` in a URL-EYED context, the query is pinned:

- the generated assertion carries the STORY's URL, not the pipeline's guess;
- if the candidate carries a different pair, or none, the emitted assertion
  fails and names both the story's URL and the page the browser reached;
- the evidence record says ``query_rule='story-pins-query'`` instead of
  ``query_rule='identity'``.

WHAT A STORY WRITER TYPES
-------------------------
Put the query pair in a URL or path context, or put the full URL in the story::

    the shopper opens /cart?item=blue-top
    the cart URL must contain item=blue-top
    Open https://shop.example.com/cart.html?item=blue-top

A bare pair in prose does NOT pin. "the receipt shows total=10" is a statement
about page content, not an address, so it leaves page identity in charge. The
same goes for a bare value ("blue-top"): the writer must name the parameter and
put it next to the address.

The rule lives here so the next change reads it instead of rediscovering it.
``EvidenceTracker._same_page`` and the eval golden validator both delegate here,
and the placeholder resolver imports :func:`story_query_url` and
:func:`carries_story_query`.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

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


# A token that names an address rather than page content. The cue words let a
# story say "the cart URL must contain item=blue-top" without a literal path.
_ADDRESS_CUES = frozenset(
    {
        "url",
        "uri",
        "address",
        "path",
        "route",
        "endpoint",
        "link",
        "href",
        "query",
        "querystring",
        "query-string",
        "params",
        "parameters",
        "param",
        "parameter",
    }
)

# A list join only continues the scan when the token before it is another query
# pair. That keeps "the URL is /cart and total=10" from pinning total.
_LIST_CONNECTORS = frozenset({"and", "or", "&"})

# Small words that may sit between an address/cue token and the query pair. A
# prose word that is not here stops the backward scan, so "the receipt shows
# total=10" is not URL-eyed.
_CONNECTORS = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "be",
        "must",
        "should",
        "has",
        "have",
        "contain",
        "contains",
        "include",
        "includes",
        "use",
        "uses",
        "using",
        "with",
        "and",
        "or",
        "to",
        "at",
        "on",
        "for",
        "of",
        "in",
        "from",
    }
)

# A relative file path such as cart.html or success.php.
_PATH_FILE = re.compile(r"^[\w.~-]+\.(?:html?|php|aspx?|jsp|json)$")


def _clean_token(token: str) -> str:
    return token.strip("\"'`()[]{}<>,.;:!").lower()


def _is_address_token(token: str) -> bool:
    """True when a token reads as a URL, a path, or a page-address cue."""
    cleaned = _clean_token(token)
    if not cleaned:
        return False
    if cleaned in _ADDRESS_CUES:
        return True
    if "://" in cleaned:
        return True
    if cleaned.startswith(("/", "./", "../", "?")):
        return True
    if "/" in cleaned or "?" in cleaned:
        return True
    return bool(_PATH_FILE.match(cleaned))


def _token_is_url_eyed(tokens: list[tuple[str, int, int]], cleaned: list[str], index: int) -> bool:
    """True when the pair in *tokens[index]* sits in a URL-eyed context.

    Same-token shapes (``/cart?item=blue-top``) are address tokens by their own
    prefix. Otherwise scan back over connector words only: the first meaningful
    token must be an address/cue, or another query pair that is itself
    URL-eyed. A plain prose word stops the scan.
    """
    raw = tokens[index][0]
    equals = raw.find("=")
    if equals > 0:
        prefix = raw[:equals]
        if "/" in prefix or "?" in prefix:
            return True

    cursor = index - 1
    while cursor >= 0:
        token = cleaned[cursor]
        if not token:
            cursor -= 1
            continue
        if token in _LIST_CONNECTORS:
            peek = cursor - 1
            while peek >= 0 and (not cleaned[peek] or cleaned[peek] in _CONNECTORS):
                peek -= 1
            if peek < 0 or "=" not in tokens[peek][0]:
                return False
            cursor -= 1
            continue
        if token in _CONNECTORS:
            cursor -= 1
            continue
        if _is_address_token(token):
            return True
        if "=" in tokens[cursor][0]:
            return _token_is_url_eyed(tokens, cleaned, cursor)
        return False
    return False


def _story_query_pair_list(story: str) -> list[tuple[str, str]]:
    """Return the query pairs a story names in a URL-eyed context, in order.

    A bare ``key=value`` in prose ("the receipt shows total=10") is not a query
    pin. A pair inside or next to an address is ("/cart?item=blue-top",
    "the cart URL must contain item=blue-top").
    """
    text = story or ""
    tokens = [(match.group(0), match.start(), match.end()) for match in re.finditer(r"\S+", text)]
    cleaned = [_clean_token(token) for token, _start, _end in tokens]

    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for match in _QUERY_PAIR.finditer(text):
        token_index = next(
            (index for index, (_token, start, end) in enumerate(tokens) if start <= match.start() < end),
            None,
        )
        if token_index is None or not _token_is_url_eyed(tokens, cleaned, token_index):
            continue
        key = match.group(1)
        value = match.group(2)
        # A query pair in prose is often followed by a comma or a full stop.
        if value and value[-1] in ".,;:!" and (match.end() == len(text) or text[match.end()].isspace()):
            value = value[:-1]
        pair = (key, value)
        if pair not in seen:
            seen.add(pair)
            pairs.append(pair)
    return pairs


def story_query_pairs(story: str) -> set[tuple[str, str]]:
    """Return the query pairs a story names explicitly.

    Reads both ``key=value`` tokens and full URLs. A bare value (``blue-top``)
    is not a query pair: the writer must name the parameter too.
    """
    pairs = set(_story_query_pair_list(story))
    for match in _FULL_URL.finditer(story or ""):
        pairs.update(query_pairs(match.group(0).rstrip(".,;:")))
    return pairs


def story_query_url(story: str, candidate_url: str) -> str | None:
    """Return the URL the story pins, or ``None`` when the story names no query.

    A full URL with a query in the story is used verbatim. Otherwise the story's
    ``key=value`` pairs are applied to the candidate's scheme, host and path.
    The candidate's own query is deliberately NOT used as the expected side:
    the story is what the assertion must carry.
    """
    story_text = story or ""
    for match in _FULL_URL.finditer(story_text):
        url = match.group(0).rstrip(".,;:")
        if urlparse(url).query:
            return url

    pairs = _story_query_pair_list(story_text)
    if not pairs:
        return None

    parsed = urlparse(str(candidate_url or ""))
    if not parsed.netloc:
        return None
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(pairs), ""))


def carries_story_query(url: str, expected_url: str) -> bool:
    """True when *url* is the story's page and carries every pinned query pair.

    Extra query parameters are allowed: the story pins only the pairs it names,
    so a tracking parameter does not turn a correct page into a failure.
    """
    if not expected_url:
        return True
    if not same_page(expected_url, url):
        return False
    return query_pairs(expected_url) <= query_pairs(url)


def story_pins_query(story: str, candidate_url: str = "") -> bool:
    """Return True when the story names a query, whether or not the candidate has one."""
    return story_query_url(story, candidate_url) is not None
