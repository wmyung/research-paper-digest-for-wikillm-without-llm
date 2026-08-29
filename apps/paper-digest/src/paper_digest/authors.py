"""Byline parsing.

Publisher title pages fuse author names with affiliation superscripts, ORCID
icon glyphs and contribution symbols. This module strips that syntax without
touching the names, splits the byline into an ordered author list, and keeps
the markers so that footnotes such as "☯ These authors contributed equally"
can be attributed to the right people.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .text import normalize_prose, unique_preserve

MARKER_CHARS = "¹²³⁴⁵⁶⁷⁸⁹⁰†‡*☯¤§¶#∗●◊■□▲△✉✝✻&^"
# Lowercase particles that belong to names and must survive marker stripping.
NAME_PARTICLES = {
    "van",
    "von",
    "de",
    "del",
    "della",
    "der",
    "den",
    "di",
    "da",
    "dos",
    "das",
    "du",
    "la",
    "le",
    "el",
    "al",
    "bin",
    "ibn",
    "ter",
    "ten",
    "op",
    "aan",
    "y",
    "mac",
    "mc",
}
CORPORATE_RE = re.compile(
    r"\b(?:group|consortium|network|collaborat|committee|team|society|initiative|"
    r"investigators?|working party|universities|trialists?)\b",
    re.I,
)
NAME_CHAR_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ'’.\-]+")
ORCID_GLYPH_RE = re.compile(r"(?<=[a-zà-öø-ÿ])ID(?=[\s\d,;*†‡☯¤§¶#]|$)")
SUPERSCRIPT_DIGITS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")


@dataclass(slots=True)
class Author:
    name: str
    markers: set[str] = field(default_factory=set)


def _markers_in(part: str) -> set[str]:
    markers: set[str] = set()
    for character in part:
        if character in MARKER_CHARS:
            markers.add(character.translate(SUPERSCRIPT_DIGITS))
    for group in re.findall(r"(?<=[A-Za-zÀ-ÖØ-öø-ÿ.’'\)])\s*(\d+(?:\s*[,;]\s*\d+)*)", part):
        markers.update(re.findall(r"\d+", group))
    for letter in re.findall(r"(?<=[A-Za-zÀ-ÖØ-öø-ÿ])\s+([a-z]{1,2})(?=\s|$)", part.strip()):
        if letter not in NAME_PARTICLES:
            markers.add(letter)
    bare = part.strip()
    if re.fullmatch(r"[a-z]{1,2}|\d{1,3}", bare):
        markers.add(bare)
    return markers


def strip_byline_markup(text: str) -> str:
    """Remove affiliation and contribution syntax, keeping the name intact."""
    value = normalize_prose(text)
    # PLOS renders the ORCID icon as the literal glyph pair "ID" welded to the
    # surname; it is never part of a name.
    value = ORCID_GLYPH_RE.sub("", value)
    value = re.sub(rf"[{re.escape(MARKER_CHARS)}]+", " ", value)
    value = re.sub(r"(?<=[A-Za-zÀ-ÖØ-öø-ÿ.’'\)])\s*\d+(?:\s*[,;]\s*\d+)*", " ", value)
    value = re.sub(r"(?<![A-Za-zÀ-ÖØ-öø-ÿ])\d+(?:\s*[,;]\s*\d+)*(?![A-Za-zÀ-ÖØ-öø-ÿ])", " ", value)
    # Standalone one/two-letter affiliation keys: "Page a", "Loder w x".
    # A short lowercase token is a name particle only when another capitalised
    # name follows it ("Jan de Vries"); at the end of a byline it is a marker.
    previous = None
    while previous != value:
        previous = value
        value = re.sub(
            r"(?<=[A-Za-zÀ-ÖØ-öø-ÿ])\s+([a-z]{1,2})(?=\s+[A-ZÀ-ÖØ-Þ])",
            lambda match: match.group(0) if match.group(1) in NAME_PARTICLES else "",
            value.strip(),
        )
        value = re.sub(r"(?<=[A-Za-zÀ-ÖØ-öø-ÿ])(?:\s+[a-z]{1,2})+\s*$", "", value.strip())
    return re.sub(r"\s{2,}", " ", value).strip(" ,;.")


def looks_like_person(value: str) -> bool:
    value = value.strip(" ,.;")
    tokens = NAME_CHAR_RE.findall(value)
    if not 2 <= len(tokens) <= 8:
        return False
    if re.search(r"\d|@|https?://", value):
        return False
    if CORPORATE_RE.search(value):
        return False
    return sum(1 for token in tokens if token[:1].isupper()) >= 2


def parse_byline(text: str) -> tuple[list[Author], list[str], bool]:
    """Return (ordered authors with markers, group authors, truncated flag)."""
    value = normalize_prose(text)
    truncated = bool(re.search(r"\bet\s+al\b", value, re.I))
    value = re.sub(r"\bet\s+al\.?", "", value, flags=re.I)
    value = re.sub(r"\s*&\s*|\s+\band\b\s+", ", ", value)
    authors: list[Author] = []
    groups: list[str] = []
    for part in value.split(","):
        raw = part.strip()
        if not raw:
            continue
        markers = _markers_in(raw)
        name = strip_byline_markup(raw)
        if name and looks_like_person(name):
            authors.append(Author(name=name, markers=markers))
        elif name and CORPORATE_RE.search(name) and 2 <= len(name.split()) <= 12:
            groups.append(name)
        elif markers and authors:
            # A bare continuation such as ", g" carries the previous author's
            # second affiliation key.
            authors[-1].markers |= markers
    seen: set[str] = set()
    unique: list[Author] = []
    for author in authors:
        key = author.name.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(author)
    return unique, unique_preserve(groups), truncated


def split_byline(text: str) -> tuple[list[str], list[str], bool]:
    authors, groups, truncated = parse_byline(text)
    return [author.name for author in authors], groups, truncated


ROLE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"contributed\s+equally|equal contribution|joint first author", re.I), "equal"),
    (re.compile(r"jointly\s+supervised|joint (?:senior|last) author", re.I), "supervisor"),
    (re.compile(r"corresponding author|correspondence", re.I), "corresponding"),
]


def roles_from_notes(authors: list[Author], notes: str) -> dict[str, list[str]]:
    """Attribute footnote roles to authors through their byline markers."""
    assigned: dict[str, list[str]] = {"equal": [], "supervisor": [], "corresponding": []}
    for line in notes.splitlines():
        value = normalize_prose(line)
        if not value:
            continue
        role = next((name for pattern, name in ROLE_PATTERNS if pattern.search(value)), None)
        if role is None:
            continue
        head = value[:6]
        markers = {character.translate(SUPERSCRIPT_DIGITS) for character in head if character in MARKER_CHARS}
        if not markers:
            continue
        matched = [author.name for author in authors if author.markers & markers]
        if matched:
            assigned[role] = unique_preserve(assigned[role] + matched)
    return assigned
