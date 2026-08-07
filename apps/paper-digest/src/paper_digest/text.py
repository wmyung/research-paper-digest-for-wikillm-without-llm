from __future__ import annotations

import html
import re
import unicodedata
from collections.abc import Iterable

SPACE_RE = re.compile(r"[\t\u00a0\u2000-\u200b]+")
MULTISPACE_RE = re.compile(r" {2,}")
TOKEN_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9'’\-]*\b")
ABBREVIATIONS = {
    "e.g.",
    "i.e.",
    "et al.",
    "Fig.",
    "Figs.",
    "Table.",
    "Dr.",
    "Mr.",
    "Ms.",
    "Prof.",
    "vs.",
    "ref.",
    "refs.",
    "approx.",
    "Inc.",
    "No.",
    "St.",
    "U.S.",
    "s.e.",
    "S.E.",
    "a.m.",
    "p.m.",
    "cf.",
    "etc.",
}


def normalize_unicode(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    replacements = {
        "−": "-",
        "–": "-",
        "—": "—",
        "ﬁ": "fi",
        "ﬂ": "fl",
        "\x16": "-",
        "\x01": "",
        "\x02": "",
        "\ufffe": "",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def clean_line(text: str) -> str:
    text = html.unescape(normalize_unicode(text))
    text = SPACE_RE.sub(" ", text)
    text = MULTISPACE_RE.sub(" ", text)
    return text.strip()


def dehyphenate(text: str) -> str:
    text = re.sub(r"([A-Za-z]{2,})-\s*\n\s*([a-z]{2,})", r"\1\2", text)
    return text


def normalize_prose(text: str) -> str:
    text = normalize_unicode(text)
    text = dehyphenate(text)
    text = re.sub(r"\s*\n\s*", " ", text)
    text = re.sub(r"([A-Za-z]{2,})-\s+([a-z]{2,})", r"\1\2", text)
    text = re.sub(r"([A-Za-z0-9])-\s+([A-Z0-9])", r"\1-\2", text)
    text = SPACE_RE.sub(" ", text)
    text = MULTISPACE_RE.sub(" ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([([{])\s+", r"\1", text)
    text = re.sub(r"\s+([)\]}])", r"\1", text)
    return text.strip()


def split_sentences(text: str) -> list[str]:
    text = normalize_prose(text)
    if not text:
        return []
    protected = text
    placeholders: dict[str, str] = {}
    for i, abbreviation in enumerate(sorted(ABBREVIATIONS, key=len, reverse=True)):
        key = f"<ABBR{i}>"
        if abbreviation in protected:
            protected = protected.replace(abbreviation, key)
            placeholders[key] = abbreviation
    protected = re.sub(r"(?<=\d)\.(?=\d)", "<DECIMAL>", protected)
    protected = re.sub(r"(?<=\b[A-Z])\.(?=[A-Z]\.)", "<INITIAL>", protected)
    parts = re.split(r"(?<=[.!?])\s+(?=(?:[A-Z0-9(\[]|\*+[A-Z]))", protected)
    output: list[str] = []
    for part in parts:
        for key, value in placeholders.items():
            part = part.replace(key, value)
        part = part.replace("<DECIMAL>", ".").replace("<INITIAL>", ".").strip()
        if part:
            output.append(part)
    return output


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'’\-]+\b", text, flags=re.UNICODE))


def tokens(text: str, min_len: int = 2) -> list[str]:
    return [m.group(0).lower() for m in TOKEN_RE.finditer(text) if len(m.group(0)) >= min_len]


def unique_preserve(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        value = re.sub(r"\s+", " ", str(item).strip())
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            output.append(value)
    return output


def oxford_join(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def markdown_escape_yaml(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def compact_paragraph(text: str, max_words: int = 170) -> str:
    sentences = split_sentences(text)
    selected: list[str] = []
    count = 0
    for sentence in sentences:
        n = word_count(sentence)
        if selected and count + n > max_words:
            break
        selected.append(sentence)
        count += n
    return " ".join(selected).strip()
