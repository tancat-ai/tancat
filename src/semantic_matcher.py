"""Token-based semantic similarity for placeholder matching.

Extracted from placeholder_resolver.py to reduce file size and separate
token-expansion logic into its own independently testable module.
"""

from __future__ import annotations

import re

__all__ = ["SemanticMatcher"]


class SemanticMatcher:
    """Token-based semantic similarity for placeholder matching.

    Provides word-expansion, token normalization, and Jaccard-style
    similarity scoring used by PlaceholderResolver to match natural
    language descriptions against scraped DOM metadata.
    """

    STOP_WORDS: set[str] = {
        "a",
        "an",
        "and",
        "be",
        "button",
        "check",
        "correctly",
        "for",
        "have",
        "icon",
        "in",
        "into",
        "items",
        "link",
        "logo",
        "of",
        "or",
        "page",
        "please",
        "product",
        "the",
        "to",
        "url",
        "with",
    }

    # Curated token expansions for placeholder resolution.
    TOKEN_EXPANSIONS: dict[str, set[str]] = {
        # --- E-commerce / shopping vocabulary ---
        "add": {"buy", "basket", "place"},
        "basket": {"cart", "bag", "shopping"},
        "cart": {"basket", "bag", "shopping", "trolley"},
        "checkout": {
            "check",
            "out",
            "order",
            "payment",
            "proceed",
            "complete",
            "finish",
        },
        "ecommerce": {"shop", "store"},
        "finish": {"complete", "done", "submit", "place", "order"},
        "home": {"index", "landing", "start", "main"},
        "product": {"item", "goods", "merchandise"},
        "products": {"catalog", "item", "goods"},
        "shopping": {"cart", "basket", "bag", "continue"},
        # --- Form field names ---
        "password": {"pass", "pw", "passwd"},
        "username": {
            "user",
            "name",
            "login",
            "email",
            "userid",
            "user_id",
            "user-name",
            "input",
        },
        "user": {"username", "user-name", "user_name", "login"},
        "name": {"full name", "first name", "last name", "given name"},
        "first": {"forename", "given"},
        "last": {"surname", "family", "family name"},
        "zip": {"postal", "code", "postcode", "pin"},
        "address": {"addr", "location", "street"},
        "phone": {"tel", "telephone", "mobile", "cell"},
        "email": {"e-mail", "mail"},
        # --- Navigation / action verbs ---
        "verify": {"assert", "check", "confirm", "ensure"},
        "confirm": {"verify", "assert", "check"},
        "continue": {"proceed", "next"},
        "cancel": {"close", "dismiss", "decline"},
        "close": {"dismiss", "exit", "cancel", "x"},
        "back": {"previous", "return", "go back"},
        "next": {"forward", "continue"},
        "submit": {"send", "post", "place", "confirm", "save"},
        "search": {"find", "query", "look", "lookup"},
        "sort": {"order", "arrange", "filter"},
        "filter": {"sort", "narrow", "refine"},
        "clear": {"remove", "delete", "reset"},
        "select": {"choose", "pick"},
        "enter": {"type", "input", "fill", "key"},
        "navigate": {"go", "open", "visit", "load"},
        # --- Confirmation / assertion patterns ---
        "success": {"completed", "done", "ok", "confirmed"},
        # --- UI component types ---
        "popup": {"modal", "dialog", "overlay", "lightbox"},
        "dropdown": {"select", "menu", "list", "combo"},
        "dialog": {"modal", "popup", "overlay"},
        "modal": {"dialog", "popup", "overlay"},
        "overlay": {"modal", "dialog", "popup"},
    }

    # --- Public helpers -------------------------------------------------------

    @staticmethod
    def get_words(text: str, *, expand_aliases: bool = True) -> set[str]:
        """Return expanded, normalised word tokens for *text*.

        Normalises delimiters (``_`` and ``-`` → space), strips punctuation,
        removes stop-words, and optionally applies token expansions.
        """
        normalized = text.replace("_", " ").replace("-", " ")
        clean_text = re.sub(r"[^a-zA-Z0-9\s]", " ", normalized.lower())
        base_words = {word for word in clean_text.split() if word and word not in SemanticMatcher.STOP_WORDS}
        expanded_words = set(base_words)

        for word in list(base_words):
            # Handle common concatenated words
            if word == "username":
                expanded_words.update(["user", "name"])
            if word == "password":
                expanded_words.update(["pass", "word"])

            if word.endswith("s") and len(word) > 3:
                expanded_words.add(word[:-1])

            if expand_aliases:
                expanded_words.update(SemanticMatcher.TOKEN_EXPANSIONS.get(word, set()))

        return expanded_words

    @staticmethod
    def semantic_similarity(description: str, text: str) -> float:
        """Compute a semantic similarity score between *description* and *text*.

        Uses token-level overlap with expansions to handle cases like
        ``"username input"`` → ``"user-name"`` and ``"finish button"`` → ``"Finish"``.

        Returns a score between ``0.0`` and ``1.0`` where ``1.0`` is a perfect match.
        """
        if not text or not description:
            return 0.0

        # Normalize both strings
        norm_desc = description.replace("_", " ").lower().strip()
        norm_text = text.replace("_", " ").lower().strip()

        # Direct containment is highest similarity
        if norm_text in norm_desc or norm_desc in norm_text:
            return 1.0

        # Get expanded tokens for both
        desc_tokens = SemanticMatcher.get_words(norm_desc, expand_aliases=True)
        text_tokens = SemanticMatcher.get_words(norm_text, expand_aliases=True)

        if not desc_tokens or not text_tokens:
            return 0.0

        # Jaccard-like similarity with token expansions
        intersection = desc_tokens & text_tokens
        union = desc_tokens | text_tokens

        if not union:
            return 0.0

        base_similarity = len(intersection) / len(union)

        # Bonus for partial word matches
        desc_words_set = {w for w in norm_desc.split() if len(w) > 2}
        text_words_set = {w for w in norm_text.split() if len(w) > 2}

        if desc_words_set and text_words_set:
            partial_matches = 0
            total_checks = 0
            for dw in desc_words_set:
                for tw in text_words_set:
                    total_checks += 1
                    if dw in tw or tw in dw:
                        partial_matches += 1

            if total_checks > 0:
                partial_score = partial_matches / total_checks
                blended = 0.4 * base_similarity + 0.6 * partial_score
                return min(1.0, blended)

        return base_similarity
