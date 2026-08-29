"""Verbatim grounding verification.

The digest is built only from lightly normalised spans of the source PDF, so
grounding is decidable rather than a matter of judgement: every prose sentence
emitted must appear in the extracted source text once both sides are reduced to
their alphanumeric skeleton. A sentence that fails this check is a fabrication
or an extraction artifact, and is reported as a hard error.
"""

from __future__ import annotations

import re

from .text import normalize_prose

SKELETON_RE = re.compile(r"[^a-z0-9 ]+")
SPACE_RE = re.compile(r"\s+")


def skeleton(text: str) -> str:
    """Reduce text to lowercase alphanumerics and single spaces."""
    value = normalize_prose(text).casefold()
    value = SKELETON_RE.sub(" ", value)
    return SPACE_RE.sub(" ", value).strip()


def build_index(source_text: str) -> str:
    return skeleton(source_text)


NGRAM = 5
NGRAM_THRESHOLD = 0.92


def is_grounded(sentence: str, index: str, *, min_words: int = 6) -> bool:
    """True when the sentence is a source span, allowing for marker removal.

    A contiguous match is the normal case. Selection also strips citation
    brackets and "(Table 1)" style references from inside a sentence, which
    breaks contiguity without changing a single word of the author's claim, so
    a sentence whose 5-grams are almost all present in the source counts as
    grounded. A paraphrase or an invented number destroys most of them.
    """
    probe = skeleton(sentence)
    if not probe:
        return False
    if probe in index:
        return True
    words = probe.split()
    if len(words) < min_words:
        return False
    if len(words) < NGRAM:
        return probe in index
    grams = [" ".join(words[start : start + NGRAM]) for start in range(len(words) - NGRAM + 1)]
    present = sum(1 for gram in grams if gram in index)
    return present / len(grams) >= NGRAM_THRESHOLD


def audit(sentences: list[str], source_text: str) -> dict[str, object]:
    index = build_index(source_text)
    ungrounded = [sentence for sentence in sentences if not is_grounded(sentence, index)]
    total = len(sentences)
    return {
        "checked": total,
        "grounded": total - len(ungrounded),
        "ungrounded_count": len(ungrounded),
        "ratio": round((total - len(ungrounded)) / total, 4) if total else 1.0,
        "ungrounded": [sentence[:200] for sentence in ungrounded[:10]],
    }


PROSE_LINE_RE = re.compile(r"^(?:\d+\.\s+|-\s+)?(?P<body>[A-Z0-9“(\[].*)$")


def prose_sentences(markdown: str) -> list[str]:
    """Every claim-bearing sentence in a compiled digest body."""
    from .text import split_sentences

    body = markdown.split("\n---\n", 1)[-1]
    sentences: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "|", "---", "**")):
            continue
        if stripped.startswith("- **") and "—" in stripped:
            continue  # glossary entries are compiled, not quoted
        match = PROSE_LINE_RE.match(stripped)
        if not match:
            continue
        sentences.extend(split_sentences(match.group("body")))
    return [sentence for sentence in sentences if len(sentence.split()) >= 6]
