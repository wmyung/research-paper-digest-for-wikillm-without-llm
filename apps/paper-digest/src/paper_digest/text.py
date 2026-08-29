from __future__ import annotations

import html
import re
import unicodedata
from collections.abc import Iterable

SPACE_RE = re.compile(r"[\t\u00a0\u2000-\u200b]+")
MULTISPACE_RE = re.compile(r" {2,}")
TOKEN_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9'’\-]*\b")
SOFT_HYPHEN_MARKER = "\ue000"
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
    text = re.sub(r"(?<=[A-Za-z])\u00ad\s*(?=[a-z])", "", text)
    replacements = {
        "\u00ad": "",
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
    # Preserve a discretionary hyphen at a line end until adjacent PDF lines
    # are rejoined by normalize_prose().
    text = text.replace("\u00ad", SOFT_HYPHEN_MARKER)
    text = html.unescape(normalize_unicode(text))
    text = SPACE_RE.sub(" ", text)
    text = MULTISPACE_RE.sub(" ", text)
    return text.strip()


def dehyphenate(text: str) -> str:
    text = re.sub(r"([A-Za-z]{2,})-\s*\n\s*([a-z]{2,})", r"\1\2", text)
    return text


def normalize_prose(text: str) -> str:
    text = re.sub(rf"(?<=[A-Za-z]){SOFT_HYPHEN_MARKER}\s*(?=[a-z])", "", text)
    text = text.replace(SOFT_HYPHEN_MARKER, "")
    text = normalize_unicode(text)
    text = dehyphenate(text)
    text = re.sub(r"\s*\n\s*", " ", text)
    text = re.sub(r"\b(low|high|mid|short|long|moderate)-to\s*([a-z])", r"\1-to-\2", text, flags=re.I)
    # "author- and index-level" is a suspended hyphen, not a line break.
    text = re.sub(r"([A-Za-z]{2,})-\s+(?!(?:and|or|to|in|of|for|nor|but)\b)([a-z]{2,})", r"\1\2", text)
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


# Auxiliaries plus the finite research verbs that carry a claim. The probe is
# deliberately lexical: it separates clauses from table cells and checklist
# rows, which is all the selection layer needs from it.
_AUXILIARY = (
    r"is|are|was|were|be|been|being|am|has|have|had|do|does|did|can|could|may|might|must|shall|"
    r"should|will|would|we|it|they|there"
)
_FINITE_VERBS = (
    r"identified|showed|shows|found|finds|reported|reports|observed|observes|estimated|estimates|"
    r"measured|measures|increased|increases|decreased|decreases|revealed|reveals|demonstrated|"
    r"demonstrates|included|includes|examined|examines|evaluated|evaluates|assessed|assesses|"
    r"compared|compares|associated|associates|yielded|yields|achieved|achieves|exceeded|exceeds|"
    r"remained|remains|occurred|occurs|contributed|contributes|explained|explains|predicted|"
    r"predicts|detected|detects|confirmed|confirms|replicated|replicates|validated|validates|"
    r"developed|develops|applied|applies|performed|performs|conducted|conducts|analysed|analyzed|"
    r"analyses|calculated|calculates|derived|derives|ranged|ranges|differed|differs|varied|varies|"
    r"consisted|consists|comprised|comprises|accounted|accounts|enabled|enables|allowed|allows|"
    r"required|requires|provided|provides|suggested|suggests|indicated|indicates|used|uses|"
    r"led|gave|gives|made|makes|took|takes|saw|sees|became|becomes|appeared|appears|emerged|"
    r"emerges|declined|declines|rose|rises|fell|falls|recruited|recruits|screened|screens|"
    r"selected|selects|retained|retains|replaced|replaces|updated|updates|recommend|recommends"
)
_AUXILIARY_RE = re.compile(rf"\b(?:{_AUXILIARY})\b", re.I)
_FINITE_VERB_RE = re.compile(rf"\b(?:{_FINITE_VERBS})\b", re.I)
# A regular past-tense form followed by an argument is finite enough.
_INFLECTED_RE = re.compile(
    r"\b[a-z]{3,}(?:ed|ied)\b\s+(?:\d|the|a|an|that|to|in|with|by|from|for|on|at|as|no|its|"
    r"their|this|these|significant|substantial|only|more|less|higher|lower)\b",
    re.I,
)
_INFLECTED_TAIL_RE = re.compile(r"\b[a-z]{3,}(?:ed|es|s)\b\s+(?:by|in|to|with|from|that|the|a|an|as|for|on)\b", re.I)


def has_finite_verb(text: str) -> bool:
    """Cheap finite-verb probe; table cells and checklist rows rarely have one."""
    return bool(
        _AUXILIARY_RE.search(text)
        or _FINITE_VERB_RE.search(text)
        or _INFLECTED_RE.search(text)
        or _INFLECTED_TAIL_RE.search(text)
    )


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
