"""Glossary construction.

Only definitions the source actually states are emitted: an acronym whose
expansion is present in the surrounding words, or an explicit "Term — meaning"
/ "Term is defined as" statement. Terms without a stated definition are left
out rather than padded with a filler gloss.
"""

from __future__ import annotations

import re

from .text import normalize_prose, unique_preserve, word_count

ACRONYM_RE = re.compile(r"\(([A-Z][A-Za-z0-9+\-]{1,11})\)")
# Glossary boxes chain definitions without a full stop between them, so the
# terms are located first and each definition is the span up to the next term.
TERM_DASH_RE = re.compile(
    r"(?:^|(?<=[.;:)\]]\s)|(?<=\n))(?P<term>[A-Z][A-Za-z0-9][A-Za-z0-9 ,'’/()+-]{1,58}?)\s*[—–]\s*",
    re.M,
)
EXPLICIT_RE = re.compile(
    r"\b(?P<term>[A-Z][A-Za-z0-9][A-Za-z0-9 '’/-]{1,48}?)\s+(?:is|are)\s+defined as\s+(?P<definition>[^.]{10,280}\.)",
    re.M,
)
CITATION_RE = re.compile(r"\s*\[[0-9][0-9,\s–-]*\]")
STOP_TERMS = {
    "the",
    "this",
    "these",
    "results",
    "methods",
    "discussion",
    "table",
    "figure",
    "box",
    "abstract",
    "introduction",
    "conclusion",
    "supplementary",
    "however",
    "therefore",
}


def _initials(words: list[str]) -> str:
    stop = {"a", "an", "and", "for", "in", "of", "on", "the", "to", "with"}
    letters: list[str] = []
    for word in words:
        if word.casefold() in stop:
            continue
        for part in re.findall(r"[A-Za-z]+", word):
            if part.casefold() not in stop:
                letters.append(part[0].upper())
    return "".join(letters)


def acronym_pairs(text: str, limit: int = 24) -> list[tuple[str, str]]:
    """Acronyms whose expansion immediately precedes the parenthesis."""
    pairs: list[tuple[str, str]] = []
    for match in ACRONYM_RE.finditer(text):
        acronym = match.group(1)
        letters = re.sub(r"[^A-Z]", "", acronym)
        if len(letters) < 2 or len(letters) / len(acronym) < 0.6:
            continue
        prefix = normalize_prose(text[max(0, match.start() - 170) : match.start()]).strip(" ,.;:")
        prefix = re.split(r"[.;:]", prefix)[-1].strip()
        words = re.findall(r"[A-Za-z][A-Za-z'’/-]*", prefix)[-16:]
        for size in range(2, min(14, len(words)) + 1):
            candidate = words[-size:]
            if _initials(candidate) == letters:
                pairs.append((acronym, " ".join(candidate)))
                break
        if len(pairs) >= limit:
            break
    return pairs


def stated_definitions(text: str, limit: int = 24) -> list[tuple[str, str]]:
    """Definitions the source spells out, as in a glossary box."""
    found: list[tuple[str, str]] = []
    anchors = list(TERM_DASH_RE.finditer(text))
    for index, match in enumerate(anchors):
        stop = anchors[index + 1].start() if index + 1 < len(anchors) else len(text)
        chunk = text[match.end() : stop]
        sentence_end = chunk.find(". ")
        if sentence_end > 15:
            chunk = chunk[: sentence_end + 1]
        term = normalize_prose(match.group("term")).strip(" ,;:")
        definition = CITATION_RE.sub("", normalize_prose(chunk)).strip(" .;:")
        if not term or term.casefold() in STOP_TERMS:
            continue
        if not 1 <= word_count(term) <= 7 or not 4 <= word_count(definition) <= 60:
            continue
        found.append((term, definition))
        if len(found) >= limit:
            return found
    for match in EXPLICIT_RE.finditer(text):
        term = normalize_prose(match.group("term")).strip(" ,;:")
        definition = CITATION_RE.sub("", normalize_prose(match.group("definition"))).strip(" .;:")
        if term.casefold() in STOP_TERMS or not 1 <= word_count(term) <= 7 or word_count(definition) < 4:
            continue
        found.append((term, definition))
        if len(found) >= limit:
            break
    return found


def build(full_text: str, keywords: list[str], minimum: int = 3, maximum: int = 14) -> tuple[str, list[str]]:
    lines: list[str] = []
    seen: set[str] = set()
    for term, definition in stated_definitions(full_text):
        key = term.casefold()
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"- **{term}** — {definition.rstrip('.')}.")
    for acronym, expansion in acronym_pairs(full_text):
        key = acronym.casefold()
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"- **{acronym}** — {expansion}.")
    lines = unique_preserve(lines)[:maximum]
    authored: list[str] = []
    if len(lines) < minimum:
        # Say so rather than padding the section with unsourced entries.
        remaining = [term for term in keywords if term.casefold() not in seen][:6]
        note = (
            "The source states no further defined terms. Author- and index-level terms "
            "retained for retrieval: " + "; ".join(remaining) + "."
            if remaining
            else "The source states no defined terms or expanded acronyms."
        )
        lines.append(note)
        authored.append(note)
    return "\n".join(lines), authored
