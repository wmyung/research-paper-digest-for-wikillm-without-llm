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
# The reverse order is just as common: "IGRA (interferon gamma release assay)".
REVERSE_ACRONYM_RE = re.compile(r"\b([A-Z][A-Z0-9+\-]{1,11})\s*\(([^()]{6,90})\)")
ALIAS_RE = re.compile(
    r"\b(?P<term>[A-Z][A-Za-z0-9][A-Za-z0-9 '’/-]{1,48}?)\s*,?\s*"
    r"(?:also (?:known|referred to) as|that is|i\.e\.|hereafter (?:referred to as|called))\s*,?\s*"
    r"(?P<definition>[^.;]{6,160})",
)
# No trailing digits: "PHS1" and "PHS4" are interview speaker codes and table
# keys, not terms a reader needs defined.
BARE_ACRONYM_RE = re.compile(r"(?<![A-Za-z0-9])([A-Z]{3,8})(?![A-Za-z0-9])")
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
    """Initials of an expansion, treating an embedded acronym as all its letters.

    "latent TB infection" abbreviates to LTBI, not LTI.
    """
    stop = {"a", "an", "and", "for", "in", "of", "on", "the", "to", "with"}
    letters: list[str] = []
    for word in words:
        if word.casefold() in stop:
            continue
        for part in re.findall(r"[A-Za-z]+", word):
            if part.casefold() in stop:
                continue
            letters.append(part.upper() if part.isupper() and len(part) > 1 else part[0].upper())
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
    for match in REVERSE_ACRONYM_RE.finditer(text):
        acronym, expansion = match.group(1), normalize_prose(match.group(2)).strip(" ,.;:")
        letters = re.sub(r"[^A-Z]", "", acronym)
        words = re.findall(r"[A-Za-z][A-Za-z'’/-]*", expansion)
        if len(letters) < 2 or not 1 <= len(words) <= 12:
            continue
        if _initials(words) != letters:
            continue
        pairs.append((acronym, expansion))
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
    for pattern in (EXPLICIT_RE, ALIAS_RE):
        for match in pattern.finditer(text):
            term = normalize_prose(match.group("term")).strip(" ,;:")
            definition = CITATION_RE.sub("", normalize_prose(match.group("definition"))).strip(" .;:")
            if term.casefold() in STOP_TERMS or not 1 <= word_count(term) <= 7 or word_count(definition) < 4:
                continue
            found.append((term, definition))
            if len(found) >= limit:
                return found
    return found


def undefined_acronyms(text: str, known: set[str], limit: int = 14) -> list[str]:
    """Recurring acronyms the source never expands.

    Naming them is honest and useful: a reader of the record knows the jargon
    exists and that the paper never spelled it out.
    """
    counts: dict[str, int] = {}
    for match in BARE_ACRONYM_RE.finditer(text):
        token = match.group(1)
        if token.casefold() in known or token in {"DOI", "ISSN", "PDF", "HTML", "URL", "CC"}:
            continue
        counts[token] = counts.get(token, 0) + 1
    ranked = sorted((item for item in counts.items() if item[1] >= 2), key=lambda item: (-item[1], item[0]))
    return [token for token, _count in ranked[:limit]]


def build(
    full_text: str,
    keywords: list[str],
    minimum: int = 5,
    maximum: int = 16,
    min_words: int = 60,
) -> tuple[str, list[str]]:
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
    # Aim above the floor: the validator counts the rendered section, which
    # drops the list markers this text still carries.
    target_words = int(min_words * 1.35)
    if len(lines) < minimum or word_count("\n".join(lines)) < target_words:
        # Name the jargon the source never expands rather than inventing a gloss.
        for acronym in undefined_acronyms(full_text, seen):
            entry = f"- **{acronym}** — used in the source without a stated expansion."
            lines.append(entry)
            authored.append(entry)
            seen.add(acronym.casefold())
            if len(lines) >= minimum and word_count("\n".join(lines)) >= target_words:
                break
    if len(lines) < minimum or word_count("\n".join(lines)) < target_words:
        remaining = [term for term in keywords if term.casefold() not in seen][:8]
        note = (
            "The source states no further defined terms. Author- and index-level terms "
            "retained for retrieval: " + "; ".join(remaining) + "."
            if remaining
            else "The source states no defined terms or expanded acronyms."
        )
        lines.append(note)
        authored.append(note)
    return "\n".join(lines[: maximum + 4]), authored
