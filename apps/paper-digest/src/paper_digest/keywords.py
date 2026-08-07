from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

from .text import unique_preserve

STOP = {
    "study",
    "paper",
    "result",
    "results",
    "method",
    "methods",
    "analysis",
    "analyses",
    "data",
    "using",
    "used",
    "based",
    "population",
    "populations",
    "sample",
    "samples",
    "association",
    "associations",
    "effect",
    "effects",
    "figure",
    "table",
    "supplementary",
    "significant",
    "significantly",
    "value",
    "values",
    "model",
    "models",
    "cohort",
    "cohorts",
    "participants",
    "individuals",
    "research",
    "findings",
    "identified",
    "performed",
    "showed",
    "including",
    "between",
    "within",
    "across",
    "compared",
    "however",
    "therefore",
    "current",
    "previous",
    "previously",
    "also",
    "first",
    "two",
    "one",
    "three",
    "four",
    "total",
    "this",
    "that",
    "these",
    "those",
    "from",
    "with",
    "were",
    "was",
    "are",
    "and",
    "the",
    "for",
    "into",
    "through",
    "than",
    "their",
    "which",
    "have",
    "has",
    "had",
    "not",
}
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+\-]{2,}")
ALL_CAPS_RE = re.compile(r"\b[A-Z][A-Z0-9+\-]{2,12}\b")
SECTION_MARKER_RE = re.compile(r"\b(?:Fig|Table|Supplementary|Methods?|Results?)\.?\s*\d*[A-Za-z]?\b", re.I)


def _candidate_ngrams(text: str) -> Counter[str]:
    """Return deterministic frequency scores for content-bearing 1-3 grams.

    The previous implementation used scikit-learn for a one-document TF-IDF
    calculation. With one document, inverse-document frequency adds no useful
    information and also introduced an undeclared heavyweight runtime
    dependency. This implementation is equivalent in purpose, deterministic,
    and uses only the standard library.
    """
    tokens = TOKEN_RE.findall(SECTION_MARKER_RE.sub(" ", text))
    lowered = [token.casefold() for token in tokens]
    counts: Counter[str] = Counter()
    for size in (1, 2, 3):
        for index in range(0, len(tokens) - size + 1):
            raw = tokens[index : index + size]
            norm = lowered[index : index + size]
            if any(token in STOP for token in norm):
                continue
            if size == 1 and len(raw[0]) < 4:
                continue
            # Reject phrases dominated by bare numbers or repeated words.
            if len(set(norm)) != len(norm):
                continue
            phrase = " ".join(raw)
            counts[phrase] += 1
    return counts


def extract_keyphrases(text: str, limit: int = 12, preferred: Iterable[str] = ()) -> list[str]:
    preferred_list = [str(value).strip() for value in preferred if str(value).strip()]
    cleaned = re.sub(r"\s+", " ", text)
    counts = _candidate_ngrams(cleaned)

    # Longer phrases receive a modest specificity bonus, while frequency
    # remains the primary signal. Lexical tie-breaking makes runs reproducible.
    ranked = sorted(
        counts,
        key=lambda phrase: (
            -(counts[phrase] * (1.0 + 0.35 * (len(phrase.split()) - 1))),
            -len(phrase.split()),
            phrase.casefold(),
        ),
    )
    phrases = [phrase for phrase in ranked[: max(limit * 5, limit)]]
    acronyms = [item for item, count in Counter(ALL_CAPS_RE.findall(text)).most_common() if count >= 2]
    return unique_preserve(preferred_list + acronyms + phrases)[:limit]
