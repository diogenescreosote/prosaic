"""Where in the docset the speaker is.

Two signals, tried in order. An explicit cue in the utterance ("page
seventeen", "Acme seventeen", "next page", "back one", "the intake
note") moves the pointer at once, no model needed. Failing that, the
words of a substantive utterance are matched against every page's
text: when a page other than the current one clearly owns the
distinctive words the speaker just used, the pointer moves there. The
model may also move it, from context the heuristics cannot see, and
the speaker can always say the page.
"""

from __future__ import annotations

import re

from .docset import Docset

_WORD_NUM = {
    "zero": 0,
    "oh": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
    "hundred": 100,
}
_STOP = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "of",
    "to",
    "in",
    "on",
    "at",
    "for",
    "with",
    "by",
    "from",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "this",
    "that",
    "these",
    "those",
    "it",
    "its",
    "i",
    "me",
    "my",
    "we",
    "our",
    "you",
    "your",
    "he",
    "she",
    "they",
    "them",
    "his",
    "her",
    "their",
    "what",
    "which",
    "who",
    "how",
    "when",
    "where",
    "why",
    "about",
    "into",
    "over",
    "under",
    "than",
    "then",
    "there",
    "here",
    "just",
    "also",
    "very",
    "really",
    "kind",
    "sort",
    "like",
    "say",
    "says",
    "said",
    "saying",
    "ask",
    "asking",
    "question",
    "questions",
    "one",
    "two",
    "page",
    "pages",
    "bates",
    "number",
    "next",
    "back",
    "go",
    "going",
    "look",
    "looking",
    "see",
    "seeing",
    "think",
    "thinks",
    "thought",
    "want",
    "wants",
    "would",
    "could",
    "should",
    "might",
    "maybe",
    "let",
    "lets",
    "okay",
    "ok",
    "so",
    "yeah",
    "yes",
    "no",
    "not",
    "don't",
    "didn't",
    "doesn't",
    "isn't",
    "wasn't",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
}

_NEXT_RE = re.compile(
    r"\b(next (?:page|one|record|document)|turn(?:ing)? the page|page forward)\b", re.I
)
_PREV_RE = re.compile(
    r"\b((?:previous|prior|last) page|(?:go |flip )?back (?:a |one )?page|page back)\b", re.I
)


def _spoken_number(text: str) -> int | None:
    """'seventeen' -> 17, 'twenty three' -> 23, 'zero zero one seven' -> 17."""
    words = [w for w in re.split(r"[\s-]+", text.lower()) if w]
    if not words or any(w not in _WORD_NUM for w in words):
        return None
    if all(_WORD_NUM[w] <= 9 for w in words) and len(words) > 1:
        return int("".join(str(_WORD_NUM[w]) for w in words))  # digit by digit
    total = 0
    for w in words:
        v = _WORD_NUM[w]
        total = total * 100 if v == 100 else total + v
    return total


def explicit_cue(utterance: str, ds: Docset, current: int) -> int | None:
    """A page number the utterance names outright, or None."""
    u = utterance.strip()
    if _NEXT_RE.search(u):
        return min(current + 1, len(ds.pages))
    if _PREV_RE.search(u):
        return max(current - 1, 1)
    prefix = re.escape(ds.prefix.rstrip("-_ ").lower())
    pat = re.compile(
        rf"\b(?:page|bates|{prefix})\s*(?:number\s*)?(?:(\d{{1,7}})|((?:[a-z]+[\s-]?){{1,6}}))",
        re.I,
    )
    for m in pat.finditer(u):
        n = int(m.group(1)) if m.group(1) else _spoken_number(m.group(2) or "")
        if n is None:
            continue
        # A bare number is a Bates number when it is in range as one,
        # else a page number of the file.
        page = ds.number_for(str(n))
        if page is None and 1 <= n <= len(ds.pages):
            page = n
        if page:
            return page
    return title_cue(u, ds)


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z'\-]{3,}", text.lower()) if w not in _STOP}


def title_cue(utterance: str, ds: Docset) -> int | None:
    """'the psychiatrist call', 'her termination email': a page whose title owns
    at least two distinctive words of the utterance, when the utterance
    reads as navigation."""
    nav = r"\b(go to|looking at|on the|the one|let's look|open|turn to|now the|next is|move to)\b"
    if not re.search(nav, utterance, re.I):
        return None
    toks = _tokens(utterance)
    best, best_n = 0, None
    for p in ds.pages:
        if not p.label:
            continue
        hit = len(toks & _tokens(p.label))
        if hit > best:
            best, best_n = hit, p.number
    return best_n if best >= 2 else None


def content_match(
    utterance: str,
    ds: Docset,
    current: int,
    min_tokens: int = 4,
    threshold: float = 0.6,
    margin: float = 0.25,
) -> int | None:
    """The page whose text owns the utterance's distinctive words, when
    it is not the current page and clearly beats it."""
    toks = _tokens(utterance)
    if len(toks) < min_tokens:
        return None
    lowered = [(p.number, p.text.lower()) for p in ds.pages]

    def score(text: str) -> float:
        return sum(1 for t in toks if t in text) / len(toks)

    cur = score(lowered[current - 1][1]) if 1 <= current <= len(lowered) else 0.0
    best_n, best = None, 0.0
    for n, text in lowered:
        s = score(text)
        if s > best:
            best_n, best = n, s
    if best_n and best_n != current and best >= threshold and best - cur >= margin:
        return best_n
    return None
